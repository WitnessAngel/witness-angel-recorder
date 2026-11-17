#!/usr/bin/env python3
"""
Fake RTSP camera streaming a test pattern, for local testing of the Witness Angel recorder.

Two modes, one CLI:

  native    Pure-Python asyncio RTSP server; ffmpeg only encodes the test pattern. The URL path
            selects a preset and query parameters override its fields, to reproduce quirks of
            real IP cameras: auth, transports, SDP oddities, timestamp anomalies, stalls, resets...
  mediamtx  Reference mode: a standards-compliant MediaMTX server fed by ffmpeg publishers.
            Only the encoder fields (codec, size, GOP, B-frames, audio...) apply.

Examples:

  python tools/fake_rtsp_camera.py list
  python tools/fake_rtsp_camera.py native
      rtsp://127.0.0.1:8554/default
      rtsp://127.0.0.1:8554/pcmu?gop=60&stall_after=30
      rtsp://admin:admin@127.0.0.1:8554/onvif
  python tools/fake_rtsp_camera.py mediamtx --download --preset default --preset h265
      rtsp://127.0.0.1:8554/default, rtsp://127.0.0.1:8554/h265

The video shows the wall-clock time and frame number, so gaps and drifts are visible in recordings.
Requires Python >= 3.8 and an ffmpeg with libx264 (libx265 for H.265) on the PATH.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import collections
import hashlib
import io
import logging
import os
import platform
import random
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from email.utils import formatdate
from pathlib import Path

logger = logging.getLogger("fakecam")

NTP_UNIX_DELTA = 2208988800  # Seconds between 1900-01-01 and 1970-01-01
MASK32 = 0xFFFFFFFF
REALM = "fakecam"
SERVER_NAME = "fake-rtsp-camera"
FOREIGN_CONTENT_BASE = "rtsp://192.168.1.64:554/Streaming/Channels/101/"
SOURCE_LINGER_S = 15  # Keep an idle encoder alive this long, to absorb recorder reconnections
MAX_TCP_BACKLOG = 4 * 1024 * 1024
STARTUP_MONOTONIC = time.monotonic()

MEDIAMTX_VERSION = "v1.21.4"


# ---------------------------------------------------------------------------------------------
# Fields, presets and configuration
# ---------------------------------------------------------------------------------------------

ENCODER = "encoder"  # Encoded stream; honored by both modes
ENCODER_NATIVE = "encoder-native"  # Encoded stream; native mode only
SERVER = "server"  # RTSP/RTP server behaviour; native mode only


class Field:
    __slots__ = ("name", "kind", "default", "scope", "help", "choices")

    def __init__(self, name, kind, default, scope, help, choices=()):
        self.name = name
        self.kind = kind
        self.default = default
        self.scope = scope
        self.help = help
        self.choices = choices


FIELDS = [
    # Encoder
    Field("codec", str, "h264", ENCODER, "Video codec", ("h264", "h265", "mjpeg")),
    Field("size", str, "640x360", ENCODER, "Frame size, WIDTHxHEIGHT (even numbers)"),
    Field("fps", int, 15, ENCODER, "Frame rate"),
    Field("gop", int, 30, ENCODER, "Keyframe interval, in frames"),
    Field("bframes", int, 0, ENCODER, "Consecutive B-frames (H.264 main/high, H.265); > 0 gives non-monotonic DTS"),
    Field("h264_profile", str, "main", ENCODER, "H.264 profile", ("baseline", "main", "high")),
    Field("bitrate", str, "1M", ENCODER, "Video bitrate (ignored for mjpeg)"),
    Field("audio", str, "none", ENCODER, "Audio track carrying a 1 kHz tone", ("none", "pcmu", "pcma")),
    Field("overlay", bool, True, ENCODER, "Burn wall-clock time and frame number into the image"),
    Field("size_change_every", float, 0.0, ENCODER_NATIVE,
          "Restart the encoder at alternately full and half size every N s (0 = never)"),
    # RTSP signalling
    Field("auth", str, "none", SERVER, "Authentication on every method but OPTIONS", ("none", "basic", "digest")),
    Field("user", str, "admin", SERVER, "Expected user name"),
    Field("password", str, "admin", SERVER, "Expected password"),
    Field("nonce_lifetime", float, 0.0, SERVER, "Digest nonce validity in s, then 401 stale=TRUE (0 = forever)"),
    Field("transports", str, "tcp,udp", SERVER, "Accepted lower transports, others get 461",
          ("tcp,udp", "tcp", "udp")),
    Field("max_clients", int, 0, SERVER, "Max concurrent sessions on this path (0 = unlimited)"),
    Field("busy_status", int, 453, SERVER, "Status code returned to DESCRIBE when max_clients is reached"),
    Field("session_timeout", int, 60, SERVER, "Timeout advertised in the Session header, in s"),
    Field("keepalive", str, "off", SERVER,
          "Requests that refresh the session; without one for session_timeout s the connection is closed",
          ("off", "any", "get_parameter", "options", "rtcp")),
    Field("advertise_get_parameter", bool, True, SERVER, "List GET_PARAMETER in the OPTIONS Public header"),
    Field("describe_delay", float, 0.0, SERVER, "Delay before answering DESCRIBE, in s (-1 = never answer)"),
    # SDP
    Field("control", str, "relative", SERVER, "Track control URLs and Content-Base style",
          ("relative", "absolute", "no_base", "foreign_base")),
    Field("sdp_sprop", bool, True, SERVER, "Put SPS/PPS (and VPS) in the SDP fmtp line"),
    Field("inband_params", str, "always", SERVER,
          "SPS/PPS (and VPS) inside the RTP stream: at every keyframe, at the first one only, or never",
          ("always", "first", "never")),
    Field("join", str, "keyframe", SERVER,
          "Where a new client starts: at the next keyframe (like most cameras) or immediately, mid-GOP",
          ("keyframe", "any")),
    Field("onvif_metadata", bool, False, SERVER, "Add an ONVIF metadata track (one XML packet per second)"),
    # RTP timing
    Field("rtp_ts_start", str, "random", SERVER, "Initial RTP timestamp ('wrap' = wraps past 2^32 after 10 s)",
          ("random", "zero", "wrap")),
    Field("clock_rate_factor", float, 1.0, SERVER, "RTP clock speed versus real time (1.02 = camera clock 2 % fast)"),
    Field("ts_jump_every", float, 0.0, SERVER, "Every N s after PLAY, shift RTP timestamps by ts_jump (0 = never)"),
    Field("ts_jump", float, -5.0, SERVER, "Timestamp shift in s (negative = backwards)"),
    Field("rtcp", str, "sr", SERVER, "RTCP sender reports: normal, none, or NTP clock counting from 1970",
          ("sr", "none", "bogus")),
    # Delivery
    Field("stall_after", float, 0.0, SERVER, "Stop sending media N s after PLAY, keeping the connection (0 = never)"),
    Field("stall_for", float, 0.0, SERVER, "Stall duration in s (0 = forever)"),
    Field("reset_after", float, 0.0, SERVER, "Abort the TCP connection with a RST N s after PLAY (0 = never)"),
    Field("packet_loss", float, 0.0, SERVER, "Probability of dropping each RTP packet"),
    Field("reorder", float, 0.0, SERVER, "Probability of swapping an RTP packet with the next one"),
]
FIELDS_BY_NAME = {f.name: f for f in FIELDS}

PRESETS = {
    # Encoder-only presets, also available in mediamtx mode
    "default": ("H.264 Main 640x360@15, keyframe every 2 s, no audio, no auth, TCP+UDP: a well-behaved camera", {}),
    "hd": ("H.264 High 1920x1080@25, keyframe every 2 s, 4 Mb/s",
           dict(size="1920x1080", fps=25, gop=50, h264_profile="high", bitrate="4M")),
    "baseline": ("H.264 Constrained Baseline", dict(h264_profile="baseline")),
    "bframes": ("H.264 High with 2 B-frames: presentation order differs from decode order",
                dict(h264_profile="high", bframes=2)),
    "h265": ("H.265/HEVC", dict(codec="h265")),
    "mjpeg": ("Motion JPEG (RFC 2435)", dict(codec="mjpeg")),
    "pcmu": ("Extra G.711 mu-law audio track (like the Bluestork cameras)", dict(audio="pcmu")),
    "pcma": ("Extra G.711 A-law audio track", dict(audio="pcma")),
    "long-gop": ("Keyframe every 10 s ('smart codec' style): slow start, late preview image", dict(gop=150)),
    # Native-only presets
    "onvif": ("Typical ONVIF camera: digest auth, mu-law audio, ONVIF metadata track",
              dict(auth="digest", audio="pcmu", onvif_metadata=True)),
    "basic-auth": ("Basic authentication (admin/admin)", dict(auth="basic")),
    "digest-auth": ("Digest authentication (admin/admin)", dict(auth="digest")),
    "digest-stale": ("Digest authentication, nonces expire after 10 s (401 stale=TRUE)",
                     dict(auth="digest", nonce_lifetime=10)),
    "tcp-only": ("Refuses UDP transport (461)", dict(transports="tcp")),
    "udp-only": ("Refuses TCP interleaved transport (461)", dict(transports="udp")),
    "single-client": ("One session at a time, other DESCRIBEs get 453", dict(max_clients=1)),
    "mid-gop-join": ("New clients start immediately, mid-GOP, with undecodable frames until the next keyframe",
                     dict(join="any")),
    "keepalive-any": ("Connection closed after 10 s without any keepalive",
                      dict(session_timeout=10, keepalive="any")),
    "keepalive-strict": ("Connection closed after 10 s without GET_PARAMETER, which is not advertised in OPTIONS",
                         dict(session_timeout=10, keepalive="get_parameter", advertise_get_parameter=False)),
    "slow-describe": ("Answers DESCRIBE after 3 s", dict(describe_delay=3)),
    "no-sprop": ("SPS/PPS only in-band, not in the SDP", dict(sdp_sprop=False)),
    "params-sdp-only": ("SPS/PPS only in the SDP, never in-band", dict(inband_params="never")),
    "params-once": ("SPS/PPS in-band before the first keyframe only, not in the SDP",
                    dict(inband_params="first", sdp_sprop=False)),
    "absolute-control": ("Absolute track control URLs in the SDP", dict(control="absolute")),
    "no-content-base": ("No Content-Base header, relative track control URLs", dict(control="no_base")),
    "foreign-base": ("Content-Base pointing at another IP address and path", dict(control="foreign_base")),
    "ts-wrap": ("RTP timestamps wrap past 2^32 10 s after PLAY", dict(rtp_ts_start="wrap")),
    "ts-jump-back": ("RTP timestamps jump 5 s backwards every 20 s (clock resync)",
                     dict(ts_jump_every=20, ts_jump=-5)),
    "ts-jump-forward": ("RTP timestamps jump 5 s forwards every 20 s", dict(ts_jump_every=20, ts_jump=5)),
    "clock-drift": ("Camera RTP clock runs 2 % fast", dict(clock_rate_factor=1.02)),
    "no-rtcp": ("No RTCP sender reports", dict(rtcp="none")),
    "bogus-rtcp": ("RTCP sender reports with an NTP clock counting from 1970", dict(rtcp="bogus")),
    "stall": ("Media stops 20 s after PLAY, connection stays open", dict(stall_after=20)),
    "hiccup": ("Media pauses for 8 s, 20 s after PLAY", dict(stall_after=20, stall_for=8)),
    "drop-connection": ("TCP connection reset 30 s after PLAY", dict(reset_after=30)),
    "lossy": ("1 % RTP packet loss and 1 % reordering", dict(packet_loss=0.01, reorder=0.01)),
    "res-change": ("Resolution alternates 640x360 / 320x180 every 30 s", dict(size_change_every=30)),
}

TRUE_WORDS = {"1", "true", "yes", "on"}
FALSE_WORDS = {"0", "false", "no", "off"}


class ConfigError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def parse_field_value(field: Field, raw):
    if isinstance(raw, str):
        if field.kind is bool:
            lowered = raw.strip().lower()
            if lowered in TRUE_WORDS:
                value = True
            elif lowered in FALSE_WORDS:
                value = False
            else:
                raise ConfigError("Field %r expects a boolean, got %r" % (field.name, raw))
        else:
            try:
                value = field.kind(raw.strip())
            except ValueError:
                raise ConfigError("Field %r expects %s, got %r" % (field.name, field.kind.__name__, raw))
    else:
        value = field.kind(raw)
    if field.choices and value not in field.choices:
        raise ConfigError("Field %r must be one of %s, got %r" % (field.name, "|".join(field.choices), value))
    return value


def _validate_config(values: dict):
    match = re.fullmatch(r"(\d+)x(\d+)", values["size"])
    if not match or int(match.group(1)) % 2 or int(match.group(2)) % 2 or int(match.group(1)) < 16:
        raise ConfigError("Field 'size' must look like 640x360, with even numbers, got %r" % values["size"])
    if values["codec"] == "mjpeg" and (int(match.group(1)) > 2040 or int(match.group(2)) > 2040):
        raise ConfigError("RTP/JPEG frames are limited to 2040x2040")
    if values["fps"] <= 0 or values["gop"] <= 0:
        raise ConfigError("Fields 'fps' and 'gop' must be positive")
    if not 0 <= values["bframes"] <= 16:
        raise ConfigError("Field 'bframes' must be between 0 and 16")
    for name in ("packet_loss", "reorder"):
        if not 0 <= values[name] <= 1:
            raise ConfigError("Field %r is a probability, between 0 and 1" % name)
    if values["clock_rate_factor"] <= 0:
        raise ConfigError("Field 'clock_rate_factor' must be positive")
    if values["session_timeout"] <= 0:
        raise ConfigError("Field 'session_timeout' must be positive")


class Config:
    """Field values resolved from a preset, global overrides and URL query parameters."""

    def __init__(self, preset: str, values: dict):
        self.__dict__["preset"] = preset
        self.__dict__["values"] = values

    def __getattr__(self, name):
        try:
            return self.__dict__["values"][name]
        except KeyError:
            raise AttributeError(name)

    @property
    def dimensions(self):
        width, height = self.size.split("x")
        return int(width), int(height)

    def source_key(self):
        return tuple(sorted((k, v) for k, v in self.values.items() if FIELDS_BY_NAME[k].scope != SERVER))

    def non_default_fields(self, scopes):
        return [f.name for f in FIELDS if f.scope in scopes and self.values[f.name] != f.default]


def resolve_config(preset: str, *override_layers) -> Config:
    if preset not in PRESETS:
        raise ConfigError("Unknown preset %r (run the 'list' command)" % preset, status=404)
    values = {f.name: f.default for f in FIELDS}
    layers = [list(PRESETS[preset][1].items())] + [list(layer) for layer in override_layers]
    for layer in layers:
        for name, raw in layer:
            field = FIELDS_BY_NAME.get(name)
            if field is None:
                raise ConfigError("Unknown field %r (run the 'list' command)" % name)
            values[name] = parse_field_value(field, raw)
    _validate_config(values)
    return Config(preset, values)


def parse_set_options(items) -> list:
    pairs = []
    for item in items or ():
        name, sep, raw = item.partition("=")
        if not sep:
            raise ConfigError("--set expects FIELD=VALUE, got %r" % item)
        pairs.append((name.strip(), raw))
    return pairs


def preset_works_with_mediamtx(name: str) -> bool:
    return all(FIELDS_BY_NAME[k].scope == ENCODER for k in PRESETS[name][1])


# ---------------------------------------------------------------------------------------------
# ffmpeg command lines (shared by both modes)
# ---------------------------------------------------------------------------------------------


def _even(value: int) -> int:
    return max(2, value - value % 2)


def build_encoder_inputs(cfg: Config, width: int, height: int) -> list:
    args = ["-re", "-f", "lavfi", "-i", "testsrc2=size=%dx%d:rate=%d" % (width, height, cfg.fps)]
    if cfg.audio != "none":
        args += ["-re", "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=8000:samples_per_frame=160"]
    return args


def build_video_args(cfg: Config, width: int, height: int, overlay_supported: bool) -> list:
    filters = []
    if cfg.overlay and overlay_supported:
        label = "%s %dx%d %dfps gop%d" % (cfg.codec, width, height, cfg.fps, cfg.gop)
        if cfg.bframes and cfg.codec != "mjpeg":
            label += " bf%d" % cfg.bframes
        filters.append(
            "drawtext=text='%{localtime}  " + label + "  frame %{n}'"
            + ":fontsize=%d:fontcolor=white:box=1:boxcolor=black@0.6:x=8:y=8" % max(12, height // 20)
        )
    filters.append("format=" + ("yuvj420p" if cfg.codec == "mjpeg" else "yuv420p"))
    args = ["-map", "0:v", "-vf", ",".join(filters)]

    gop = str(cfg.gop)
    rate_control = ["-b:v", cfg.bitrate, "-maxrate", cfg.bitrate, "-bufsize", cfg.bitrate]
    if cfg.codec == "h264":
        profile = cfg.h264_profile
        if profile == "baseline" and cfg.bframes:
            logger.warning("H.264 baseline has no B-frames, using the main profile")
            profile = "main"
        args += ["-c:v", "libx264", "-preset", "ultrafast"]
        if not cfg.bframes:
            args += ["-tune", "zerolatency"]
        args += ["-profile:v", profile, "-g", gop, "-keyint_min", gop, "-sc_threshold", "0",
                 "-bf", str(cfg.bframes), "-x264-params", "repeat-headers=1"] + rate_control
    elif cfg.codec == "h265":
        args += ["-c:v", "libx265", "-preset", "ultrafast"]
        if not cfg.bframes:
            args += ["-tune", "zerolatency"]
        args += ["-g", gop, "-x265-params",
                 "keyint=%s:min-keyint=%s:scenecut=0:bframes=%d:repeat-headers=1:log-level=error"
                 % (gop, gop, cfg.bframes)] + rate_control
    else:
        # RFC 2435 requires the standard Huffman tables
        args += ["-c:v", "mjpeg", "-q:v", "5", "-huffman", "default"]
    return args


def build_audio_args(cfg: Config) -> list:
    if cfg.audio == "none":
        return []
    codec = {"pcmu": "pcm_mulaw", "pcma": "pcm_alaw"}[cfg.audio]
    return ["-map", "1:a", "-c:a", codec, "-ar", "8000", "-ac", "1"]


def probe_ffmpeg(ffmpeg: str) -> bool:
    """Exit if ffmpeg is missing; return whether its drawtext filter works."""
    try:
        subprocess.run([ffmpeg, "-hide_banner", "-version"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
    except (OSError, subprocess.CalledProcessError):
        raise SystemExit("ffmpeg not found or not working: %r (use --ffmpeg PATH)" % ffmpeg)
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=1",
         "-frames:v", "1", "-vf", "drawtext=text='x'", "-f", "null", "-"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if result.returncode:
        logger.warning("ffmpeg drawtext filter unavailable, the time overlay is disabled")
    return result.returncode == 0


async def pump_stderr(stream, tail: collections.deque, label: str):
    while True:
        line = await stream.readline()
        if not line:
            return
        text = line.decode("utf-8", "replace").rstrip()
        if not text or "Fontconfig" in text:
            continue
        tail.append(text)
        logger.debug("[%s] %s", label, text)


async def terminate_process(process):
    if process is None or process.returncode is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(process.wait(), 5)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


# ---------------------------------------------------------------------------------------------
# RTP helpers
# ---------------------------------------------------------------------------------------------


class TrackDesc:
    __slots__ = ("kind", "media", "pt", "clock", "encoding")

    def __init__(self, kind, media, pt, clock, encoding):
        self.kind = kind
        self.media = media
        self.pt = pt
        self.clock = clock
        self.encoding = encoding


VIDEO_RTP = {"h264": (96, 90000, "H264"), "h265": (96, 90000, "H265"), "mjpeg": (26, 90000, "JPEG")}
AUDIO_RTP = {"pcmu": (0, 8000, "PCMU"), "pcma": (8, 8000, "PCMA")}
METADATA_TRACK = TrackDesc("metadata", "application", 107, 90000, "vnd.onvif.metadata")

PARAM_TYPES = {"h264": {7, 8}, "h265": {32, 33, 34}}
IRAP_TYPES = {"h264": {5}, "h265": set(range(16, 24))}


def source_tracks(cfg: Config) -> list:
    tracks = [TrackDesc("video", "video", *VIDEO_RTP[cfg.codec])]
    if cfg.audio != "none":
        tracks.append(TrackDesc("audio", "audio", *AUDIO_RTP[cfg.audio]))
    return tracks


def session_tracks(cfg: Config) -> list:
    return source_tracks(cfg) + ([METADATA_TRACK] if cfg.onvif_metadata else [])


def parse_rtp(data: bytes):
    if len(data) < 12 or data[0] >> 6 != 2:
        return None
    offset = 12 + 4 * (data[0] & 0x0F)
    if data[0] & 0x10:
        if len(data) < offset + 4:
            return None
        offset += 4 + 4 * int.from_bytes(data[offset + 2:offset + 4], "big")
    end = len(data) - (data[-1] if data[0] & 0x20 else 0)
    if end <= offset:
        return None
    marker = bool(data[1] & 0x80)
    ts = int.from_bytes(data[4:8], "big")
    return marker, ts, data[offset:end]


def _nal_type(codec: str, nal: bytes) -> int:
    return nal[0] & 0x1F if codec == "h264" else (nal[0] >> 1) & 0x3F


def _split_aggregate(payload: bytes, offset: int) -> list:
    nals = []
    while offset + 2 <= len(payload):
        size = int.from_bytes(payload[offset:offset + 2], "big")
        offset += 2
        if size == 0 or offset + size > len(payload):
            break
        nals.append(payload[offset:offset + size])
        offset += size
    return nals


def split_rtp_payload(codec: str, payload: bytes):
    """Return ("single"|"agg", [nal, ...]) or ("frag", nal_type) or (None, None)."""
    if codec == "h264" and payload:
        nal_type = payload[0] & 0x1F
        if 1 <= nal_type <= 23:
            return "single", [payload]
        if nal_type == 24:
            return "agg", _split_aggregate(payload, 1)
        if nal_type == 28 and len(payload) > 1:
            return "frag", payload[1] & 0x1F
    elif codec == "h265" and len(payload) >= 2:
        nal_type = (payload[0] >> 1) & 0x3F
        if nal_type < 48:
            return "single", [payload]
        if nal_type == 48:
            return "agg", _split_aggregate(payload, 2)
        if nal_type == 49 and len(payload) > 2:
            return "frag", payload[2] & 0x3F
    return None, None


def strip_param_sets(codec: str, payload: bytes):
    """Remove parameter set NAL units from an RTP payload; None if nothing is left."""
    kind, data = split_rtp_payload(codec, payload)
    params = PARAM_TYPES[codec]
    if kind == "single":
        return None if _nal_type(codec, payload) in params else payload
    if kind == "agg":
        kept = [nal for nal in data if _nal_type(codec, nal) not in params]
        if len(kept) == len(data):
            return payload
        if not kept:
            return None
        if len(kept) == 1:
            return kept[0]
        header = payload[:1] if codec == "h264" else payload[:2]
        return header + b"".join(len(nal).to_bytes(2, "big") + nal for nal in kept)
    return payload


def video_fmtp(cfg: Config, params: dict) -> str:
    def b64(nal):
        return base64.b64encode(nal).decode("ascii")

    if cfg.codec == "h264":
        parts = ["packetization-mode=1"]
        sps = params.get(7)
        if sps and len(sps) >= 4:
            parts.append("profile-level-id=" + sps[1:4].hex().upper())
        if cfg.sdp_sprop and sps and 8 in params:
            parts.append("sprop-parameter-sets=%s,%s" % (b64(sps), b64(params[8])))
        return ";".join(parts)
    if cfg.codec == "h265" and cfg.sdp_sprop and all(t in params for t in (32, 33, 34)):
        return "sprop-vps=%s;sprop-sps=%s;sprop-pps=%s" % (b64(params[32]), b64(params[33]), b64(params[34]))
    return ""


# ---------------------------------------------------------------------------------------------
# Native mode: shared encoder
# ---------------------------------------------------------------------------------------------


class Unit:
    """An access unit (video frame, audio packet), timestamped on the source's continuous timeline."""

    __slots__ = ("ts", "packets", "key", "params")

    def __init__(self, ts, packets, key, params):
        self.ts = ts
        self.packets = packets  # [(marker, payload), ...]
        self.key = key
        self.params = params


class _TrackIngest:
    __slots__ = ("generation", "first_ts", "offset", "last_norm", "last_wall",
                 "pending", "pending_ts", "pending_key", "pending_params")

    def __init__(self):
        self.generation = 0
        self.first_ts = 0
        self.offset = 0
        self.last_norm = None
        self.last_wall = 0.0
        self.pending = []
        self.pending_ts = 0
        self.pending_key = False
        self.pending_params = False


class _IngestProtocol(asyncio.DatagramProtocol):
    def __init__(self, source, track_index):
        self.source = source
        self.track_index = track_index

    def datagram_received(self, data, addr):
        self.source.on_datagram(self.track_index, data)

    def error_received(self, exc):
        logger.debug("Ingest socket error: %s", exc)


class StreamSource:
    """One ffmpeg encoder sending RTP to local UDP ports, fanned out to all subscribed sessions.

    Like a real camera, every client gets the same live stream and starts at the next keyframe.
    """

    def __init__(self, cfg: Config, ffmpeg: str, overlay_supported: bool):
        self.cfg = cfg
        self.ffmpeg = ffmpeg
        self.overlay_supported = overlay_supported
        self.tracks = source_tracks(cfg)
        width, height = cfg.dimensions
        self.label = "%s %dx%d@%d" % (cfg.codec, width, height, cfg.fps)
        self.subscribers = set()
        self.users = 0
        self.linger_handle = None
        self.params = {}  # NAL type -> latest parameter set NAL
        self.ready = asyncio.Event()
        self._ingest = [_TrackIngest() for _ in self.tracks]
        self._transports = []
        self._ports = []
        self._generation = 0
        self._half_size = False
        self._process = None
        self._task = None
        self._stderr_tail = collections.deque(maxlen=20)

    async def start(self):
        loop = asyncio.get_running_loop()
        for index in range(len(self.tracks)):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
            except OSError:
                pass
            sock.bind(("127.0.0.1", 0))
            self._ports.append(sock.getsockname()[1])
            transport, _ = await loop.create_datagram_endpoint(
                lambda index=index: _IngestProtocol(self, index), sock=sock)
            self._transports.append(transport)
        self._task = asyncio.ensure_future(self._run())

    async def stop(self):
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await terminate_process(self._process)
        for transport in self._transports:
            transport.close()
        self._transports = []
        logger.info("Encoder %s stopped", self.label)

    def _build_command(self, width, height):
        cmd = [self.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "warning"]
        cmd += build_encoder_inputs(self.cfg, width, height)
        cmd += build_video_args(self.cfg, width, height, self.overlay_supported)
        cmd += ["-f", "rtp", "-rtpflags", "skip_rtcp", "rtp://127.0.0.1:%d?pkt_size=1400" % self._ports[0]]
        if self.cfg.audio != "none":
            cmd += build_audio_args(self.cfg)
            cmd += ["-f", "rtp", "-rtpflags", "skip_rtcp", "rtp://127.0.0.1:%d?pkt_size=1400" % self._ports[1]]
        return cmd

    async def _run(self):
        backoff = 1
        try:
            while True:
                width, height = self.cfg.dimensions
                if self._half_size:
                    width, height = _even(width // 2), _even(height // 2)
                self._generation += 1
                cmd = self._build_command(width, height)
                logger.info("Encoder %s starting at %dx%d", self.label, width, height)
                logger.debug("Encoder command: %s", subprocess.list2cmdline(cmd))
                started = time.monotonic()
                self._process = await asyncio.create_subprocess_exec(
                    *cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                pump = asyncio.ensure_future(pump_stderr(self._process.stderr, self._stderr_tail, self.label))
                try:
                    if self.cfg.size_change_every > 0:
                        try:
                            await asyncio.wait_for(asyncio.shield(self._process.wait()), self.cfg.size_change_every)
                        except asyncio.TimeoutError:
                            logger.info("Encoder %s: resolution change", self.label)
                            self._half_size = not self._half_size
                            await terminate_process(self._process)
                            continue
                    else:
                        await self._process.wait()
                finally:
                    await terminate_process(self._process)
                    pump.cancel()
                logger.warning("Encoder %s exited with code %s:\n  %s", self.label, self._process.returncode,
                               "\n  ".join(self._stderr_tail) or "(no output)")
                if time.monotonic() - started > 30:
                    backoff = 1
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Encoder %s crashed", self.label)

    def on_datagram(self, index: int, data: bytes):
        parsed = parse_rtp(data)
        if parsed is None:
            return
        marker, ts, payload = parsed
        ingest = self._ingest[index]
        desc = self.tracks[index]
        now = time.monotonic()

        # Normalize RTP timestamps to a continuous timeline, across encoder restarts
        if ingest.generation != self._generation:
            ingest.generation = self._generation
            ingest.first_ts = ts
            ingest.pending = []
            if ingest.last_norm is not None:
                ingest.offset = ingest.last_norm + int((now - ingest.last_wall) * desc.clock)
        delta = (ts - ingest.first_ts) & MASK32
        if delta >= 0x80000000:
            delta -= 0x100000000
        norm = ingest.offset + delta
        if ingest.last_norm is None or norm > ingest.last_norm:
            ingest.last_norm = norm
            ingest.last_wall = now

        if desc.kind != "video":
            self._dispatch(index, Unit(norm, [(marker, payload)], True, False))
            return

        if ingest.pending and norm != ingest.pending_ts:
            self._flush(index, ingest)  # Marker bit lost
        if not ingest.pending:
            ingest.pending_ts = norm
            ingest.pending_key = self.cfg.codec == "mjpeg"
            ingest.pending_params = False
        codec = self.cfg.codec
        if codec in PARAM_TYPES:
            kind, content = split_rtp_payload(codec, payload)
            if kind in ("single", "agg"):
                types = []
                for nal in content:
                    nal_type = _nal_type(codec, nal)
                    types.append(nal_type)
                    if nal_type in PARAM_TYPES[codec]:
                        self.params[nal_type] = bytes(nal)
            elif kind == "frag":
                types = [content]
            else:
                types = []
            if any(t in PARAM_TYPES[codec] for t in types):
                ingest.pending_params = True
                ingest.pending_key = True
                if not self.ready.is_set() and PARAM_TYPES[codec].issubset(self.params):
                    self.ready.set()
            elif any(t in IRAP_TYPES[codec] for t in types):
                ingest.pending_key = True
        ingest.pending.append((marker, payload))
        if marker:
            self._flush(index, ingest)

    def _flush(self, index: int, ingest: _TrackIngest):
        unit = Unit(ingest.pending_ts, ingest.pending, ingest.pending_key, ingest.pending_params)
        ingest.pending = []
        if self.cfg.codec == "mjpeg" and not self.ready.is_set():
            self.ready.set()
        self._dispatch(index, unit)

    def _dispatch(self, index: int, unit: Unit):
        for session in list(self.subscribers):
            try:
                session.on_unit(index, unit)
            except Exception:
                logger.exception("Error while sending to %s", session.conn.label)


# ---------------------------------------------------------------------------------------------
# Native mode: RTSP sessions
# ---------------------------------------------------------------------------------------------


class ClientTrack:
    def __init__(self, index: int, desc: TrackDesc, cfg: Config, setup_url: str):
        self.index = index
        self.desc = desc
        self.setup_url = setup_url
        self.ssrc = random.getrandbits(32)
        self.seq = random.getrandbits(16)
        self.initial_seq = self.seq
        if cfg.rtp_ts_start == "zero":
            self.ts_base = 0
        elif cfg.rtp_ts_start == "wrap":
            self.ts_base = (1 << 32) - 10 * desc.clock
        else:
            self.ts_base = random.getrandbits(32)
        self.tcp_channel = None
        self.udp_rtp = None
        self.udp_rtcp = None
        self.anchor = 0
        self.started = False
        self.params_sent = False
        self.held = None
        self.packets = 0
        self.octets = 0
        self.last_ts = 0
        self.last_wall = None


class Session:
    def __init__(self, conn, cfg: Config, source: StreamSource):
        self.id = "%08X" % random.getrandbits(32)
        self.conn = conn
        self.cfg = cfg
        self.source = source
        self.tracks = {}  # SDP track index -> ClientTrack
        self.playing = False
        self.play_wall = 0.0
        self.last_keepalive = time.monotonic()
        self.closed = False
        self._stall_state = False
        self._backlog_warned = False
        self._ticker = asyncio.ensure_future(self._tick())

    @property
    def header(self) -> str:
        return "%s;timeout=%d" % (self.id, self.cfg.session_timeout)

    def play(self):
        # Each track is anchored on its first sent unit, so that its first RTP timestamp equals the
        # "rtptime" announced in RTP-Info (like real cameras, and unlike a PLAY-time anchor which would
        # make clients see a gap until the first keyframe).
        for track in self.tracks.values():
            track.started = False
            track.initial_seq = track.seq
        self.playing = True
        self.play_wall = time.monotonic()
        self.source.subscribers.add(self)

    def pause(self):
        self.playing = False
        self.source.subscribers.discard(self)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.pause()
        self._ticker.cancel()

    def refresh(self, kind: str):
        mode = self.cfg.keepalive
        if kind in ("SETUP", "PLAY") or mode in ("off", "any") or mode == kind.lower():
            self.last_keepalive = time.monotonic()

    def is_stalled(self, elapsed: float) -> bool:
        cfg = self.cfg
        stalled = cfg.stall_after > 0 and elapsed >= cfg.stall_after and (
            cfg.stall_for <= 0 or elapsed < cfg.stall_after + cfg.stall_for)
        if stalled != self._stall_state:
            self._stall_state = stalled
            logger.warning("%s: media %s", self.conn.label, "stalled" if stalled else "resumed")
        return stalled

    def _video_started(self) -> bool:
        video = self.tracks.get(0)
        return video is None or video.started

    def _map_ts(self, track: ClientTrack, norm: int, elapsed: float) -> int:
        cfg = self.cfg
        delta = (norm - track.anchor) * cfg.clock_rate_factor
        if cfg.ts_jump_every > 0:
            delta += int(elapsed // cfg.ts_jump_every) * cfg.ts_jump * track.desc.clock
        return (track.ts_base + int(round(delta))) & MASK32

    def on_unit(self, index: int, unit: Unit):
        track = self.tracks.get(index)
        if track is None or not self.playing:
            return
        now = time.monotonic()
        elapsed = now - self.play_wall
        if self.is_stalled(elapsed):
            return
        if not track.started:
            if track.desc.kind == "video" and not unit.key and self.cfg.join == "keyframe":
                return
            if track.desc.kind != "video" and not self._video_started():
                return
            track.started = True
            track.anchor = unit.ts
            logger.info("%s: %s track started", self.conn.label, track.desc.kind)
        packets = unit.packets
        codec = self.cfg.codec
        if track.desc.kind == "video" and codec in PARAM_TYPES:
            mode = self.cfg.inband_params
            if mode == "never" or (mode == "first" and track.params_sent):
                packets = [(marker, stripped) for marker, payload in packets
                           for stripped in (strip_param_sets(codec, payload),) if stripped is not None]
            elif unit.params:
                track.params_sent = True
        ts = self._map_ts(track, unit.ts, elapsed)
        for marker, payload in packets:
            self._send_rtp(track, marker, ts, payload, now)

    def _send_rtp(self, track: ClientTrack, marker: bool, ts: int, payload: bytes, now: float):
        cfg = self.cfg
        seq = track.seq
        track.seq = (seq + 1) & 0xFFFF
        if cfg.packet_loss and random.random() < cfg.packet_loss:
            return
        header = struct.pack("!BBHII", 0x80, (0x80 if marker else 0) | track.desc.pt, seq, ts, track.ssrc)
        packet = header + payload
        track.packets += 1
        track.octets += len(payload)
        track.last_ts = ts
        track.last_wall = now
        if cfg.reorder and track.held is None and random.random() < cfg.reorder:
            track.held = packet
            return
        self.conn.send_media(self, track, packet, rtcp=False)
        if track.held is not None:
            self.conn.send_media(self, track, track.held, rtcp=False)
            track.held = None

    def _send_sender_report(self, track: ClientTrack, now: float):
        if track.last_wall is None:
            return
        cfg = self.cfg
        rtp_ts = (track.last_ts + int((now - track.last_wall) * track.desc.clock * cfg.clock_rate_factor)) & MASK32
        if cfg.rtcp == "bogus":
            ntp = NTP_UNIX_DELTA + (now - STARTUP_MONOTONIC)  # Camera believing it booted in 1970
        else:
            ntp = NTP_UNIX_DELTA + time.time()
        seconds = int(ntp)
        fraction = int((ntp - seconds) * (1 << 32)) & MASK32
        report = struct.pack("!BBHIIIIII", 0x80, 200, 6, track.ssrc, seconds & MASK32, fraction, rtp_ts,
                             track.packets & MASK32, track.octets & MASK32)
        cname = SERVER_NAME.encode("ascii")
        chunk = struct.pack("!I", track.ssrc) + bytes([1, len(cname)]) + cname + b"\x00"
        chunk += b"\x00" * (-len(chunk) % 4)
        sdes = struct.pack("!BBH", 0x81, 202, len(chunk) // 4) + chunk
        self.conn.send_media(self, track, report + sdes, rtcp=True)

    def _send_metadata(self, now: float, elapsed: float):
        track = self.tracks.get(len(self.source.tracks))
        if track is None:
            return
        if not track.started:
            if not self._video_started():
                return
            track.started = True
            track.anchor = int(now * track.desc.clock)
        utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        xml = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<tt:MetadataStream xmlns:tt="http://www.onvif.org/ver10/schema">'
               '<tt:VideoAnalytics><tt:Frame UtcTime="%s"/></tt:VideoAnalytics></tt:MetadataStream>' % utc)
        ts = self._map_ts(track, int(now * track.desc.clock), elapsed)
        self._send_rtp(track, True, ts, xml.encode("utf-8"), now)

    async def _tick(self):
        cfg = self.cfg
        next_report = next_metadata = 0.0
        while True:
            await asyncio.sleep(0.2)
            now = time.monotonic()
            if cfg.keepalive != "off" and now - self.last_keepalive > cfg.session_timeout:
                logger.warning("%s: session %s expired (no '%s' keepalive for %d s), closing connection",
                               self.conn.label, self.id, cfg.keepalive, cfg.session_timeout)
                self.conn.abort(rst=False)
                return
            if not self.playing:
                continue
            elapsed = now - self.play_wall
            if cfg.reset_after > 0 and elapsed >= cfg.reset_after:
                logger.warning("%s: resetting connection (reset_after=%s)", self.conn.label, cfg.reset_after)
                self.conn.abort(rst=True)
                return
            if self.is_stalled(elapsed):
                continue
            if cfg.onvif_metadata and now >= next_metadata:
                next_metadata = now + 1
                self._send_metadata(now, elapsed)
            if cfg.rtcp != "none" and now >= next_report:
                next_report = now + 5
                for track in self.tracks.values():
                    if track.started:
                        self._send_sender_report(track, now)


REASONS = {
    200: "OK", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
    405: "Method Not Allowed", 453: "Not Enough Bandwidth", 454: "Session Not Found",
    455: "Method Not Valid in This State", 461: "Unsupported Transport", 500: "Internal Server Error",
    501: "Not Implemented", 503: "Service Unavailable",
}


class RtspConnection:
    def __init__(self, server, reader, writer):
        self.server = server
        self.reader = reader
        self.writer = writer
        peer = writer.get_extra_info("peername") or ("?", 0)
        self.peer_ip = peer[0]
        self.label = "%s:%s" % (peer[0], peer[1])
        self.local_ip = (writer.get_extra_info("sockname") or ("127.0.0.1", 0))[0]
        self.cfg = None
        self.source = None
        self.session = None
        self.closed = False
        self._nonce = None
        self._nonce_time = 0.0
        self._new_nonce()

    def _new_nonce(self):
        self._nonce = "%032x" % random.getrandbits(128)
        self._nonce_time = time.monotonic()

    async def run(self):
        logger.info("%s: connected", self.label)
        try:
            while True:
                first = await self.reader.readexactly(1)
                if first == b"$":
                    header = await self.reader.readexactly(3)
                    data = await self.reader.readexactly(int.from_bytes(header[1:3], "big"))
                    if header[0] % 2 and self.session is not None:
                        self.session.refresh("rtcp")
                    continue
                if first in b"\r\n":
                    continue
                head = first + await self.reader.readuntil(b"\r\n\r\n")
                lines = head.decode("utf-8", "replace").split("\r\n")
                parts = lines[0].split()
                if len(parts) != 3:
                    logger.warning("%s: malformed request line %r", self.label, lines[0])
                    return
                headers = {}
                for line in lines[1:]:
                    name, sep, value = line.partition(":")
                    if sep:
                        headers[name.strip().lower()] = value.strip()
                length = int(headers.get("content-length", "0") or 0)
                if length:
                    await self.reader.readexactly(length)
                await self._handle(parts[0].upper(), parts[1], headers)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError, OSError, ValueError):
            pass
        finally:
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._end_session()
        if self.source is not None:
            self.server.release_source(self.source)
            self.source = None
        try:
            self.writer.close()
        except Exception:
            pass
        logger.info("%s: disconnected", self.label)

    def abort(self, rst: bool):
        if rst:
            sock = self.writer.get_extra_info("socket")
            if sock is not None:
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                except OSError:
                    pass
            self.writer.transport.abort()
        self.close()

    def _end_session(self):
        if self.session is not None:
            self.server.unregister_session(self.session)
            self.session.close()
            self.session = None

    def respond(self, cseq, status: int, headers=(), body: bytes = b""):
        if self.closed:
            return
        lines = ["RTSP/1.0 %d %s" % (status, REASONS.get(status, "Error")), "CSeq: %s" % cseq,
                 "Server: %s" % SERVER_NAME, "Date: %s" % formatdate(usegmt=True)]
        lines += ["%s: %s" % item for item in headers]
        if body:
            lines.append("Content-Length: %d" % len(body))
        self.writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("utf-8") + body)

    def send_media(self, session: Session, track: ClientTrack, packet: bytes, rtcp: bool):
        if self.closed:
            return
        if track.tcp_channel is not None:
            if self.writer.transport.get_write_buffer_size() > MAX_TCP_BACKLOG:
                if not session._backlog_warned:
                    session._backlog_warned = True
                    logger.warning("%s: client too slow, dropping packets", self.label)
                return
            channel = track.tcp_channel + (1 if rtcp else 0)
            self.writer.write(b"$" + bytes([channel]) + len(packet).to_bytes(2, "big") + packet)
        else:
            self.server.send_udp(packet, track.udp_rtcp if rtcp else track.udp_rtp, rtcp)

    async def _handle(self, method: str, url: str, headers: dict):
        cseq = headers.get("cseq", "0")
        cfg = self.cfg
        if method == "DESCRIBE" or cfg is None:
            try:
                cfg = self.server.resolve_url_config(url)
            except ConfigError as exc:
                if method == "OPTIONS":
                    cfg = resolve_config("default", self.server.overrides)
                else:
                    logger.warning("%s: %s %s -> %d: %s", self.label, method, url, exc.status, exc)
                    self.respond(cseq, exc.status)
                    return
        if method != "OPTIONS" and cfg.auth != "none":
            challenge = self._check_auth(cfg, method, headers)
            if challenge:
                logger.info("%s: %s -> 401", self.label, method)
                self.respond(cseq, 401, [("WWW-Authenticate", challenge)])
                return
        handler = getattr(self, "_do_" + method.lower(), None)
        if handler is None:
            logger.info("%s: %s -> 501", self.label, method)
            self.respond(cseq, 501)
            return
        sid = headers.get("session", "").split(";")[0].strip()
        if sid and method not in ("OPTIONS", "DESCRIBE") and (self.session is None or sid != self.session.id):
            logger.info("%s: %s with unknown session %s -> 454", self.label, method, sid)
            self.respond(cseq, 454)
            return
        await handler(cseq, url, headers, cfg)
        if self.session is not None:
            self.session.refresh(method)

    def _check_auth(self, cfg: Config, method: str, headers: dict):
        """Return None if authorized, else the WWW-Authenticate challenge."""
        authorization = headers.get("authorization", "")
        if cfg.auth == "basic":
            expected = base64.b64encode(("%s:%s" % (cfg.user, cfg.password)).encode("utf-8")).decode("ascii")
            if authorization.strip() == "Basic " + expected:
                return None
            return 'Basic realm="%s"' % REALM

        def md5(text):
            return hashlib.md5(text.encode("utf-8")).hexdigest()

        stale = False
        if authorization[:7].lower() == "digest ":
            params = {m.group(1).lower(): m.group(2) if m.group(2) is not None else m.group(3)
                      for m in re.finditer(r'(\w+)\s*=\s*(?:"([^"]*)"|([^,\s]+))', authorization[7:])}
            if params.get("username") == cfg.user and params.get("nonce") == self._nonce:
                ha1 = md5("%s:%s:%s" % (cfg.user, REALM, cfg.password))
                ha2 = md5("%s:%s" % (method, params.get("uri", "")))
                if params.get("qop"):
                    expected = md5("%s:%s:%s:%s:%s:%s" % (ha1, self._nonce, params.get("nc", ""),
                                                          params.get("cnonce", ""), params["qop"], ha2))
                else:
                    expected = md5("%s:%s:%s" % (ha1, self._nonce, ha2))
                if params.get("response", "").lower() == expected:
                    if cfg.nonce_lifetime <= 0 or time.monotonic() - self._nonce_time <= cfg.nonce_lifetime:
                        return None
                    stale = True
                    self._new_nonce()
        return 'Digest realm="%s", nonce="%s"%s' % (REALM, self._nonce, ", stale=TRUE" if stale else "")

    def _session_headers(self):
        return [("Session", self.session.header)] if self.session is not None else []

    async def _ensure_source(self, cfg: Config) -> bool:
        if self.source is not None and self.source.cfg.source_key() != cfg.source_key():
            self._end_session()
            self.server.release_source(self.source)
            self.source = None
        if self.source is None:
            self.source = await self.server.acquire_source(cfg)
        self.cfg = cfg
        try:
            await asyncio.wait_for(self.source.ready.wait(), 15)
        except asyncio.TimeoutError:
            logger.error("Encoder %s did not produce a stream, see its log above", self.source.label)
            return False
        return True

    async def _do_options(self, cseq, url, headers, cfg):
        methods = ["OPTIONS", "DESCRIBE", "SETUP", "PLAY", "PAUSE", "TEARDOWN", "SET_PARAMETER"]
        if cfg.advertise_get_parameter:
            methods.insert(-1, "GET_PARAMETER")
        logger.debug("%s: OPTIONS -> 200", self.label)
        self.respond(cseq, 200, [("Public", ", ".join(methods))] + self._session_headers())

    async def _do_describe(self, cseq, url, headers, cfg):
        logger.info("%s: DESCRIBE %s", self.label, url)
        if cfg.describe_delay < 0:
            logger.warning("%s: never answering DESCRIBE (describe_delay=%s)", self.label, cfg.describe_delay)
            return
        if cfg.describe_delay > 0:
            await asyncio.sleep(cfg.describe_delay)
        if cfg.max_clients > 0:
            others = [s for s in self.server.sessions.get(cfg.preset, ()) if s.conn is not self]
            if len(others) >= cfg.max_clients:
                logger.warning("%s: DESCRIBE -> %d, %d session(s) already open on %r",
                               self.label, cfg.busy_status, len(others), cfg.preset)
                self.respond(cseq, cfg.busy_status)
                return
        if not await self._ensure_source(cfg):
            self.respond(cseq, 503)
            return

        parts = urllib.parse.urlsplit(url)
        netloc = parts.netloc.rpartition("@")[2]
        base = "%s://%s%s/" % (parts.scheme or "rtsp", netloc, parts.path.rstrip("/"))
        headers_out = [("Content-Type", "application/sdp")]
        if cfg.control == "foreign_base":
            headers_out.append(("Content-Base", FOREIGN_CONTENT_BASE))
        elif cfg.control != "no_base":
            headers_out.append(("Content-Base", base))

        lines = ["v=0", "o=- %d 1 IN IP4 %s" % (random.getrandbits(31), self.local_ip),
                 "s=Fake RTSP camera (%s)" % cfg.preset, "c=IN IP4 0.0.0.0", "t=0 0",
                 "a=control:*", "a=range:npt=0-"]
        for index, desc in enumerate(session_tracks(cfg)):
            lines.append("m=%s 0 RTP/AVP %d" % (desc.media, desc.pt))
            lines.append("a=rtpmap:%d %s/%d" % (desc.pt, desc.encoding, desc.clock))
            if desc.kind == "video":
                fmtp = video_fmtp(cfg, self.source.params)
                if fmtp:
                    lines.append("a=fmtp:%d %s" % (desc.pt, fmtp))
                lines.append("a=framerate:%d" % cfg.fps)
            control = "trackID=%d" % index
            lines.append("a=control:" + (base + control if cfg.control == "absolute" else control))
        sdp = ("\r\n".join(lines) + "\r\n").encode("utf-8")
        logger.debug("%s: SDP\n%s", self.label, sdp.decode("utf-8"))
        self.respond(cseq, 200, headers_out, sdp)

    @staticmethod
    def _negotiate_transport(cfg: Config, header: str):
        allowed = cfg.transports.split(",")
        for alternative in header.split(","):
            parts = [p.strip() for p in alternative.split(";") if p.strip()]
            if not parts:
                continue
            lower = "tcp" if parts[0].upper().endswith("/TCP") else "udp"
            params = {}
            for part in parts[1:]:
                name, _, value = part.partition("=")
                params[name.lower()] = value
            if "multicast" in params or lower not in allowed:
                continue
            if lower == "udp" and "client_port" not in params:
                continue
            return lower, params
        return None

    async def _do_setup(self, cseq, url, headers, cfg):
        if self.source is None and not await self._ensure_source(cfg):
            self.respond(cseq, 503)
            return
        cfg = self.cfg
        tracks = session_tracks(cfg)
        match = re.search(r"trackID=(\d+)", url)
        index = int(match.group(1)) if match else (0 if len(tracks) == 1 else None)
        if index is None or index >= len(tracks):
            logger.warning("%s: SETUP of unknown track %s -> 404", self.label, url)
            self.respond(cseq, 404)
            return
        negotiated = self._negotiate_transport(cfg, headers.get("transport", ""))
        if negotiated is None:
            logger.warning("%s: SETUP transport %r refused (transports=%s) -> 461",
                           self.label, headers.get("transport", ""), cfg.transports)
            self.respond(cseq, 461)
            return
        lower, params = negotiated
        if self.session is None:
            self.session = Session(self, cfg, self.source)
            self.server.register_session(self.session)
        track = ClientTrack(index, tracks[index], cfg, url)
        if lower == "tcp":
            numbers = [int(n) for n in re.findall(r"\d+", params.get("interleaved", ""))]
            track.tcp_channel = numbers[0] if numbers else 2 * index
            transport = "RTP/AVP/TCP;unicast;interleaved=%d-%d" % (track.tcp_channel, track.tcp_channel + 1)
        else:
            numbers = [int(n) for n in re.findall(r"\d+", params["client_port"])]
            rtp_port = numbers[0]
            rtcp_port = numbers[1] if len(numbers) > 1 else rtp_port + 1
            track.udp_rtp = (self.peer_ip, rtp_port)
            track.udp_rtcp = (self.peer_ip, rtcp_port)
            self.server.register_udp_client(self.session, track)
            transport = "RTP/AVP;unicast;client_port=%d-%d;server_port=%d-%d" % (
                rtp_port, rtcp_port, self.server.udp_port, self.server.udp_port + 1)
        transport += ";ssrc=%08X" % track.ssrc
        self.session.tracks[index] = track
        logger.info("%s: SETUP %s track over %s", self.label, track.desc.kind, lower.upper())
        self.respond(cseq, 200, [("Transport", transport)] + self._session_headers())

    async def _do_play(self, cseq, url, headers, cfg):
        if self.session is None or not self.session.tracks:
            self.respond(cseq, 455)
            return
        if not self.session.playing:
            self.session.play()
        infos = ["url=%s;seq=%d;rtptime=%d" % (t.setup_url, t.initial_seq, t.ts_base)
                 for t in self.session.tracks.values()]
        logger.info("%s: PLAY %s (session %s)", self.label, self.cfg.preset, self.session.id)
        self.respond(cseq, 200, [("Range", "npt=0.000-"), ("RTP-Info", ",".join(infos))] + self._session_headers())

    async def _do_pause(self, cseq, url, headers, cfg):
        if self.session is None:
            self.respond(cseq, 454)
            return
        self.session.pause()
        self.respond(cseq, 200, self._session_headers())

    async def _do_teardown(self, cseq, url, headers, cfg):
        session_headers = self._session_headers()
        self._end_session()
        logger.info("%s: TEARDOWN", self.label)
        self.respond(cseq, 200, session_headers)

    async def _do_get_parameter(self, cseq, url, headers, cfg):
        logger.debug("%s: GET_PARAMETER -> 200", self.label)
        self.respond(cseq, 200, self._session_headers())

    async def _do_set_parameter(self, cseq, url, headers, cfg):
        self.respond(cseq, 200, self._session_headers())


# ---------------------------------------------------------------------------------------------
# Native mode: server
# ---------------------------------------------------------------------------------------------


class NativeServer:
    def __init__(self, host, port, overrides, ffmpeg, overlay_supported, reboot_every, reboot_for):
        self.host = host
        self.port = port
        self.overrides = overrides
        self.ffmpeg = ffmpeg
        self.overlay_supported = overlay_supported
        self.reboot_every = reboot_every
        self.reboot_for = reboot_for
        self.sources = {}
        self.sessions = collections.defaultdict(set)  # preset -> sessions
        self.connections = set()
        self.udp_port = 0
        self._udp_sockets = []
        self._udp_clients = {}  # (ip, port) -> Session
        self._loop = None

    def resolve_url_config(self, url: str) -> Config:
        parts = urllib.parse.urlsplit(url)
        segments = [s for s in parts.path.split("/") if s]
        preset = urllib.parse.unquote(segments[0]) if segments else "default"
        query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        return resolve_config(preset, self.overrides, query)

    async def acquire_source(self, cfg: Config) -> StreamSource:
        key = cfg.source_key()
        source = self.sources.get(key)
        if source is None:
            source = StreamSource(cfg, self.ffmpeg, self.overlay_supported)
            self.sources[key] = source
            await source.start()
        source.users += 1
        if source.linger_handle is not None:
            source.linger_handle.cancel()
            source.linger_handle = None
        return source

    def release_source(self, source: StreamSource):
        source.users -= 1
        if source.users <= 0 and source.linger_handle is None:
            source.linger_handle = self._loop.call_later(
                SOURCE_LINGER_S, lambda: asyncio.ensure_future(self._stop_idle_source(source)))

    async def _stop_idle_source(self, source: StreamSource):
        source.linger_handle = None
        if source.users > 0:
            return
        if self.sources.get(source.cfg.source_key()) is source:
            del self.sources[source.cfg.source_key()]
        await source.stop()

    def register_session(self, session: Session):
        self.sessions[session.cfg.preset].add(session)

    def unregister_session(self, session: Session):
        self.sessions[session.cfg.preset].discard(session)
        for address in [a for a, s in self._udp_clients.items() if s is session]:
            del self._udp_clients[address]

    def register_udp_client(self, session: Session, track: ClientTrack):
        self._udp_clients[track.udp_rtp] = session
        self._udp_clients[track.udp_rtcp] = session

    def send_udp(self, packet: bytes, address, rtcp: bool):
        try:
            self._udp_sockets[1 if rtcp else 0].sendto(packet, address)
        except OSError:
            pass

    def _open_udp(self):
        for _ in range(100):
            port = random.randrange(20000, 60000, 2)
            sockets = []
            try:
                for offset in (0, 1):
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sockets.append(sock)
                    sock.bind((self.host, port + offset))
            except OSError:
                for sock in sockets:
                    sock.close()
                continue
            self.udp_port = port
            self._udp_sockets = sockets
            for sock in sockets:
                # A thread rather than asyncio: on Windows, ICMP "port unreachable" errors would stop
                # the proactor's datagram reading for good.
                threading.Thread(target=self._udp_reader, args=(sock,), daemon=True).start()
            return
        raise SystemExit("Could not bind a pair of UDP ports")

    def _udp_reader(self, sock):
        while True:
            try:
                _data, address = sock.recvfrom(4096)
            except ConnectionResetError:
                continue
            except OSError:
                return
            self._loop.call_soon_threadsafe(self._on_udp_from_client, address)

    def _on_udp_from_client(self, address):
        session = self._udp_clients.get(address)
        if session is not None:
            session.refresh("rtcp")

    async def _on_client(self, reader, writer):
        conn = RtspConnection(self, reader, writer)
        self.connections.add(conn)
        try:
            await conn.run()
        finally:
            self.connections.discard(conn)

    async def _shutdown_everything(self):
        for conn in list(self.connections):
            conn.abort(rst=True)
        for source in list(self.sources.values()):
            if source.linger_handle is not None:
                source.linger_handle.cancel()
            await source.stop()
        self.sources.clear()

    async def run(self):
        self._loop = asyncio.get_running_loop()
        self._open_udp()
        shown_host = "127.0.0.1" if self.host in ("0.0.0.0", "") else self.host
        try:
            while True:
                server = await asyncio.start_server(self._on_client, self.host, self.port)
                logger.info("Native fake camera listening on rtsp://%s:%d/<preset>[?field=value&...] "
                            "(UDP server ports %d-%d)", shown_host, self.port, self.udp_port, self.udp_port + 1)
                logger.info("  e.g. rtsp://%s:%d/default  rtsp://%s:%d/pcmu?gop=60  ('list' shows presets/fields)",
                            shown_host, self.port, shown_host, self.port)
                try:
                    if self.reboot_every <= 0:
                        await server.serve_forever()
                    await asyncio.sleep(self.reboot_every)
                finally:
                    server.close()
                logger.warning("Simulating a camera reboot: down for %s s", self.reboot_for)
                await self._shutdown_everything()
                await asyncio.sleep(self.reboot_for)
        finally:
            await self._shutdown_everything()
            for sock in self._udp_sockets:
                sock.close()


# ---------------------------------------------------------------------------------------------
# MediaMTX mode
# ---------------------------------------------------------------------------------------------


def _cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "fake_rtsp_camera"


def _mediamtx_asset_name() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = {"amd64": "amd64", "x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64",
            "armv7l": "armv7", "armv6l": "armv6"}.get(machine)
    if system not in ("windows", "linux", "darwin") or arch is None:
        raise SystemExit("No MediaMTX build known for %s/%s, use --mediamtx PATH" % (system, machine))
    extension = "zip" if system == "windows" else "tar.gz"
    return "mediamtx_%s_%s_%s.%s" % (MEDIAMTX_VERSION, system, arch, extension)


def download_mediamtx(destination: Path) -> Path:
    asset = _mediamtx_asset_name()
    base_url = "https://github.com/bluenviron/mediamtx/releases/download/%s/" % MEDIAMTX_VERSION
    logger.info("Downloading %s%s", base_url, asset)
    with urllib.request.urlopen(base_url + asset, timeout=60) as response:
        archive = response.read()
    with urllib.request.urlopen(base_url + "checksums.sha256", timeout=60) as response:
        checksums = response.read().decode("utf-8", "replace")
    expected = None
    for line in checksums.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1].lstrip("*") == asset:
            expected = fields[0].lower()
    actual = hashlib.sha256(archive).hexdigest()
    if expected != actual:
        raise SystemExit("Checksum mismatch for %s: expected %s, got %s" % (asset, expected, actual))

    executable_name = "mediamtx.exe" if asset.endswith(".zip") else "mediamtx"
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / executable_name
    if asset.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive)) as archive_file:
            content = archive_file.read(executable_name)
    else:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as archive_file:
            member = archive_file.extractfile(executable_name)
            if member is None:
                raise SystemExit("No %s in %s" % (executable_name, asset))
            content = member.read()
    target.write_bytes(content)
    target.chmod(0o755)
    logger.info("MediaMTX %s installed in %s", MEDIAMTX_VERSION, target)
    return target


def find_mediamtx(explicit, download: bool) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise SystemExit("MediaMTX executable not found: %s" % path)
        return path
    found = shutil.which("mediamtx")
    if found:
        return Path(found)
    cached_dir = _cache_dir() / ("mediamtx-" + MEDIAMTX_VERSION)
    cached = cached_dir / ("mediamtx.exe" if platform.system() == "Windows" else "mediamtx")
    if cached.is_file():
        return cached
    if not download:
        raise SystemExit("MediaMTX not found on PATH nor in %s.\nUse --download to fetch %s from GitHub, "
                         "or --mediamtx PATH." % (cached_dir, MEDIAMTX_VERSION))
    return download_mediamtx(cached_dir)


def build_mediamtx_config(host: str, port: int, path_names) -> str:
    lines = [
        "# Generated by fake_rtsp_camera.py",
        "logLevel: info",
        "rtspAddress: %s:%d" % (host, port),
        "rtmp: no",
        "hls: no",
        "webrtc: no",
        "srt: no",
        "moq: no",
        "paths:",
    ]
    lines += ["  %s:" % name for name in path_names]
    return "\n".join(lines) + "\n"


async def _wait_for_port(host: str, port: int, timeout: float, process):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.returncode is not None:
            raise SystemExit("MediaMTX exited with code %s" % process.returncode)
        try:
            _reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            return
        except OSError:
            await asyncio.sleep(0.2)
    raise SystemExit("MediaMTX did not open port %d" % port)


async def run_publisher(ffmpeg: str, cfg: Config, url: str, overlay_supported: bool):
    width, height = cfg.dimensions
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "warning"]
    cmd += build_encoder_inputs(cfg, width, height)
    cmd += build_video_args(cfg, width, height, overlay_supported)
    cmd += build_audio_args(cfg)
    cmd += ["-f", "rtsp", "-rtsp_transport", "tcp", url]
    logger.debug("Publisher command: %s", subprocess.list2cmdline(cmd))
    while True:
        tail = collections.deque(maxlen=15)
        process = await asyncio.create_subprocess_exec(
            *cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        pump = asyncio.ensure_future(pump_stderr(process.stderr, tail, cfg.preset))
        try:
            await process.wait()
        finally:
            await terminate_process(process)
            pump.cancel()
        logger.warning("Publisher %s exited with code %s:\n  %s", cfg.preset, process.returncode,
                       "\n  ".join(tail) or "(no output)")
        await asyncio.sleep(2)


async def run_mediamtx_mode(args, overrides, overlay_supported):
    executable = find_mediamtx(args.mediamtx, args.download)
    if args.all_presets:
        names = [name for name in PRESETS if preset_works_with_mediamtx(name)]
    else:
        names = args.preset or ["default"]
    configs = []
    for name in names:
        cfg = resolve_config(name, overrides)
        ignored = cfg.non_default_fields((ENCODER_NATIVE, SERVER))
        if ignored:
            logger.warning("Preset %r: fields ignored in mediamtx mode: %s", name, ", ".join(ignored))
        configs.append(cfg)

    workdir = Path(tempfile.mkdtemp(prefix="fakecam_mediamtx_"))
    config_path = workdir / "mediamtx.yml"
    config_path.write_text(build_mediamtx_config(args.host, args.port, names), encoding="utf-8")
    local_host = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    process = None
    publishers = []
    try:
        logger.info("Starting %s", executable)
        process = await asyncio.create_subprocess_exec(str(executable), str(config_path), stdin=subprocess.DEVNULL)
        await _wait_for_port(local_host, args.port, 15, process)
        for cfg in configs:
            url = "rtsp://%s:%d/%s" % (local_host, args.port, cfg.preset)
            publishers.append(asyncio.ensure_future(run_publisher(args.ffmpeg, cfg, url, overlay_supported)))
            logger.info("Serving %s  (%s)", url, PRESETS[cfg.preset][0])
        await process.wait()
        logger.error("MediaMTX exited with code %s", process.returncode)
    finally:
        for task in publishers:
            task.cancel()
        await asyncio.gather(*publishers, return_exceptions=True)
        await terminate_process(process)
        shutil.rmtree(str(workdir), ignore_errors=True)


# ---------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------


def print_catalog():
    print("Presets: URL path rtsp://HOST:PORT/<preset>   ([M] = also available in mediamtx mode)\n")
    for name, (description, overrides) in PRESETS.items():
        flag = "[M]" if preset_works_with_mediamtx(name) else "   "
        print("  %-18s %s %s" % (name, flag, description))
        if overrides:
            print("  %-18s     %s" % ("", " ".join("%s=%s" % item for item in overrides.items())))
    titles = {ENCODER: "Encoder fields (both modes)", ENCODER_NATIVE: "Encoder fields (native mode only)",
              SERVER: "Server fields (native mode only)"}
    print("\nFields: override with ?field=value in the URL, or --set field=value for all paths\n")
    for scope in (ENCODER, ENCODER_NATIVE, SERVER):
        print("  %s:" % titles[scope])
        for field in FIELDS:
            if field.scope != scope:
                continue
            default = field.default
            if field.kind is bool:
                default = int(default)
            choices = " (%s)" % "|".join(field.choices) if field.choices else ""
            print("    %-24s %s%s" % ("%s=%s" % (field.name, default), field.help, choices))
        print()


def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0].strip(), epilog=__doc__.split("\n\n", 1)[1],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", metavar="{list,native,mediamtx}")
    subparsers.required = True

    subparsers.add_parser("list", help="List presets and fields")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--host", default="0.0.0.0", help="Listening address (default: %(default)s)")
    common.add_argument("--port", type=int, default=8554, help="RTSP port (default: %(default)s)")
    common.add_argument("--ffmpeg", default="ffmpeg", help="ffmpeg executable (default: %(default)s)")
    common.add_argument("--set", action="append", metavar="FIELD=VALUE",
                        help="Override a field for every path (repeatable)")
    common.add_argument("-v", "--verbose", action="store_true", help="Debug logs (RTSP details, ffmpeg output)")

    native = subparsers.add_parser("native", parents=[common], help="Quirky pure-Python RTSP server")
    native.add_argument("--reboot-every", type=float, default=0, metavar="S",
                        help="Simulate a camera reboot every S seconds: all connections reset, port closed")
    native.add_argument("--reboot-for", type=float, default=20, metavar="S",
                        help="Reboot duration (default: %(default)s)")

    mediamtx = subparsers.add_parser("mediamtx", parents=[common], help="Reference MediaMTX server")
    mediamtx.add_argument("--preset", action="append", help="Preset to publish (repeatable, default: default)")
    mediamtx.add_argument("--all-presets", action="store_true", help="Publish every [M] preset (one encoder each)")
    mediamtx.add_argument("--mediamtx", metavar="PATH", help="MediaMTX executable (default: PATH, then cache)")
    mediamtx.add_argument("--download", action="store_true",
                          help="Download MediaMTX %s from GitHub if not found" % MEDIAMTX_VERSION)
    return parser


def _raise_keyboard_interrupt(signum, frame):
    raise KeyboardInterrupt


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "list":
        print_catalog()
        return
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    try:
        overrides = parse_set_options(args.set)
        resolve_config("default", overrides)  # Validate early
        if args.command == "mediamtx":
            for name in args.preset or ():
                resolve_config(name, overrides)
    except ConfigError as exc:
        raise SystemExit(str(exc))
    overlay_supported = probe_ffmpeg(args.ffmpeg)
    if hasattr(signal, "SIGBREAK"):  # Windows: stop gracefully on Ctrl+Break too (scripts can send it)
        signal.signal(signal.SIGBREAK, _raise_keyboard_interrupt)
    try:
        if args.command == "native":
            server = NativeServer(args.host, args.port, overrides, args.ffmpeg, overlay_supported,
                                  args.reboot_every, args.reboot_for)
            asyncio.run(server.run())
        else:
            asyncio.run(run_mediamtx_mode(args, overrides, overlay_supported))
    except KeyboardInterrupt:
        logger.info("Stopped")


if __name__ == "__main__":
    main()
