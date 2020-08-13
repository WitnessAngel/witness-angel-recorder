import pytest
from client.camera_handling import VideoStream


def test_display_video_stream():
    camera_url = (
        "rtsp://170.93.143.139/rtplive/470011e600ef003a004ee33696235daa"
    )  # Public video stream
    video_stream = VideoStream(10.0, video_stream_url=camera_url)
    video_stream.display_video_stream()


def test_write_video_stream():
    camera_url = (
        "rtsp://170.93.143.139/rtplive/470011e600ef003a004ee33696235daa"
    )  # Public video stream
    video_stream = VideoStream(10.0, video_stream_url=camera_url)
    video_stream.write_video_stream()
