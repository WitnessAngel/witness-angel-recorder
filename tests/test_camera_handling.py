import pytest
from client.camera_handling import VideoStream, VideoStreamWriterFfmpeg
from os.path import isdir, isfile
from os import listdir
import time


def test_display_video_stream():
    camera_url = "rtsp://viewer:SomePwd8162@92.89.82.156:554/Streaming/channels/2"
    # camera_url = (
    #     "rtsp://170.93.143.139/rtplive/470011e600ef003a004ee33696235daa"
    # )  # Public video stream
    video_stream = VideoStream(timeout=10.0, video_stream_url=camera_url)
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
    video_stream = VideoStream(timeout=timeout, video_stream_url=camera_url)
    video_stream.write_video_stream()

    assert isdir("saved_video_stream")
    video_files = listdir("saved_video_stream")
    for file in video_files:
        filename = f"saved_video_stream/{file}"
        assert isfile(filename)


def test_write_video_stream_ffmpeg():
    camera_url = (
        "rtsp://viewer:SomePwd8162@92.89.81.50:554/Streaming/Channels/101"
    )
    # camera_url = (
    #     "rtsp://170.93.143.139/rtplive/470011e600ef003a004ee33696235daa"
    # )  # Public video stream
    writer_ffmpeg = VideoStreamWriterFfmpeg(video_stream_url=camera_url)
    writer_ffmpeg.start()
    time.sleep(20)
    writer_ffmpeg.stop()
