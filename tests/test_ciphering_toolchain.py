import pytest
import random
import os
from pathlib import Path
import time

from client.ciphering_toolchain import (
    RecordingToolchain,
    NewVideoHandler,
    save_cryptainer,
    generate_keypair,
)
from wacryptolib.utilities import generate_uuid0

from wacryptolib.cryptainer import (
    LOCAL_TRUSTEE_MARKER,
    SHARED_SECRET_MARKER,
    decrypt_payload_from_cryptainer,
    load_cryptainer_from_filesystem,
)
from wacryptolib.keystore import FilesystemKeystore

SIMPLE_SHAMIR_CRYPTOCONF = dict(
    payload_encryption_layers=[
        dict(
            payload_encryption_algo="AES_CBC",
            key_encryption_layers=[
                dict(key_encryption_algo="RSA_OAEP", key_encryption_trustee=LOCAL_TRUSTEE_MARKER),
                dict(
                    key_encryption_algo=SHARED_SECRET_MARKER,
                    key_shared_secret_threshold=3,
                    key_shared_secret_shards=[
                        dict(
                            shard_encryption_algo="RSA_OAEP",
                            # shared_trustee=dict(url="http://example.com/jsonrpc"),
                            shard_trustee=LOCAL_TRUSTEE_MARKER,
                        ),
                        dict(
                            shard_encryption_algo="RSA_OAEP",
                            # shared_trustee=dict(url="http://example.com/jsonrpc"),
                            shard_trustee=LOCAL_TRUSTEE_MARKER,
                        ),
                        dict(
                            shard_encryption_algo="RSA_OAEP",
                            # shared_trustee=dict(url="http://example.com/jsonrpc"),
                            shard_trustee=LOCAL_TRUSTEE_MARKER,
                        ),
                        dict(
                            shard_encryption_algo="RSA_OAEP",
                            # shared_trustee=dict(url="http://example.com/jsonrpc"),
                            shard_trustee=LOCAL_TRUSTEE_MARKER,
                        ),
                        dict(
                            shard_encryption_algo="RSA_OAEP",
                            # shared_trustee=dict(url="http://example.com/jsonrpc"),
                            shard_trustee=LOCAL_TRUSTEE_MARKER,
                        ),
                    ],
                ),
            ],
            payload_signatures=[
                dict(
                    payload_digest_algo="SHA256",
                    payload_signature_algo="DSA_DSS",
                    payload_signature_trustee=LOCAL_TRUSTEE_MARKER,
                )
            ],
        )
    ]
)

COMPLEX_SHAMIR_CRYPTOCONF = dict(
    payload_encryption_layers=[
        dict(
            payload_encryption_algo="AES_EAX",
            key_encryption_layers=[
                dict(key_encryption_algo="RSA_OAEP", key_encryption_trustee=LOCAL_TRUSTEE_MARKER)
            ],
            payload_signatures=[],
        ),
        dict(
            payload_encryption_algo="AES_CBC",
            key_encryption_layers=[
                dict(key_encryption_algo="RSA_OAEP", key_encryption_trustee=LOCAL_TRUSTEE_MARKER)
            ],
            payload_signatures=[
                dict(
                    payload_digest_algo="SHA3_512",
                    payload_signature_algo="DSA_DSS",
                    payload_signature_trustee=LOCAL_TRUSTEE_MARKER,
                )
            ],
        ),
        dict(
            payload_encryption_algo="CHACHA20_POLY1305",
            key_encryption_layers=[
                dict(
                    key_encryption_algo=SHARED_SECRET_MARKER,
                    key_shared_secret_threshold=2,
                    key_shared_secret_shards=[
                        dict(
                            shard_encryption_algo="RSA_OAEP",
                            # shared_trustee=dict(url="http://example.com/jsonrpc"),
                            shard_trustee=LOCAL_TRUSTEE_MARKER,
                        ),
                        dict(
                            shard_encryption_algo="RSA_OAEP",
                            # shared_trustee=dict(url="http://example.com/jsonrpc"),
                            shard_trustee=LOCAL_TRUSTEE_MARKER,
                        ),
                        dict(
                            shard_encryption_algo="RSA_OAEP",
                            # shared_trustee=dict(url="http://example.com/jsonrpc"),
                            shard_trustee=LOCAL_TRUSTEE_MARKER,
                        ),
                        dict(
                            shard_encryption_algo="RSA_OAEP",
                            # shared_trustee=dict(url="http://example.com/jsonrpc"),
                            shard_trustee=LOCAL_TRUSTEE_MARKER,
                        ),
                    ],
                )
            ],
            payload_signatures=[
                dict(
                    payload_digest_algo="SHA3_256",
                    payload_signature_algo="RSA_PSS",
                    payload_signature_trustee=LOCAL_TRUSTEE_MARKER,
                ),
                dict(
                    payload_digest_algo="SHA512",
                    payload_signature_algo="ECC_DSS",
                    payload_signature_trustee=LOCAL_TRUSTEE_MARKER,
                ),
            ],
        ),
    ]
)


@pytest.mark.parametrize("cryptoconf", [SIMPLE_SHAMIR_CRYPTOCONF])
def test_create_observer_thread(cryptoconf):
    encryption_algo = "RSA_OAEP"
    new_video_handler = NewVideoHandler(
       cryptoconf=cryptoconf,
        key_algo=encryption_algo,
        recordings_folder="ffmpeg_video_stream/",
    )
    new_video_handler.start_observer()


def test_decipher_cryptainer():
    video_files = os.listdir("ciphered_video_stream/")
    for file in video_files:
        if file.endswith(".crypt"):
            cryptainer = load_cryptainer_from_filesystem(
                cryptainer_filepath=Path("ciphered_video_stream/{}".format(file))
            )
            decrypt_payload_from_cryptainer(cryptainer=cryptainer)


@pytest.mark.parametrize("cryptoconf", [SIMPLE_SHAMIR_CRYPTOCONF])
def test_recording_toolchain(cryptoconf):
    key_algo = "RSA_OAEP"
    # camera_url = "rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mov"
    camera_url = "rtsp://viewer:SomePwd8162@92.89.81.50:554/Streaming/Channels/101"
    recording_time = 30
    segment_time = 10
    recording_toolchain = RecordingToolchain(
        recordings_folder="ffmpeg_video_stream/",
       cryptoconf=cryptoconf,
        key_algo=key_algo,
        camera_url=camera_url,
        recording_time=str(recording_time),
        segment_time=str(segment_time),
    )
    recording_toolchain.launch_recording_toolchain()
    time.sleep(recording_time)
    recording_toolchain.stop_recording_toolchain_and_wait()
    assert os.listdir("ffmpeg_video_stream/") == []

    # Assert every segment have been ciphered
    ciphered_segment = 0
    ciphered_videos = os.listdir("ciphered_video_stream/")
    for ciphered_video in ciphered_videos:
        if ciphered_video.endswith(".crypt"):
            ciphered_segment += 1

    assert ciphered_segment >= (recording_time / segment_time)
