import pytest
from client.camera_handling import VideoStreamWriterOpenCV, VideoStreamWriterFfmpeg
from os.path import isdir, isfile
from os import listdir
import time
import random

# FIXME OBSOLETE #

def test_display_video_stream():
    camera_url = "rtsp://viewer:SomePwd8162@92.89.82.156:554/Streaming/channels/2"
    # camera_url = (
    #     "rtsp://170.93.143.139/rtplive/470011e600ef003a004ee33696235daa"
    # )  # Public video stream
    video_stream = VideoStreamWriterOpenCV(timeout=10.0, video_stream_url=camera_url)
    video_stream.display_video_stream()

    assert isdir("saved_video_stream")


def test_write_video_stream():
    # camera_url = (
    #     "rtsp://viewer:SomePwd8162@92.89.81.50:554/Streaming/Channels/101"
    # )
    camera_url = (
        "rtsp://170.93.143.139/rtplive/470011e600ef003a004ee33696235daa"
    )  # Public video stream
    timeout = 10.0
    video_stream = VideoStreamWriterOpenCV(timeout=timeout, video_stream_url=camera_url)
    video_stream.write_video_stream()

    assert isdir("saved_video_stream")
    video_files = listdir("saved_video_stream")
    for file in video_files:
        filename = f"saved_video_stream/{file}"
        assert isfile(filename)


def test_write_video_stream_ffmpeg():
    camera_url = "rtsp://viewer:SomePwd8162@92.89.81.50:554/Streaming/Channels/101"
    # camera_url = (
    #     "rtsp://170.93.143.139/rtplive/470011e600ef003a004ee33696235daa"
    # )  # Public video stream
    recording_time = random.choice(["20", None])
    writer_ffmpeg = VideoStreamWriterFfmpeg(
        video_stream_url=camera_url, recording_time="30", segment_time="10"
    )
    writer_ffmpeg.start_writing()
    if recording_time == "20":
        time.sleep(20)
    else:
        time.sleep(30)
    writer_ffmpeg.stop_writing()
