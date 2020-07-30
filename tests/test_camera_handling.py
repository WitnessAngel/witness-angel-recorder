import pytest
from client.camera_handling import display_video_stream, write_video_stream


def test_display_video_stream():
    camera_url = "rtsp://170.93.143.139/rtplive/470011e600ef003a004ee33696235daa"  # Public video stream
    # camera_url = "rtsp://192.168.1.37:8554/screen"
    display_video_stream(camera_url)


def test_write_video_stream():
    camera_url = "rtsp://170.93.143.139/rtplive/470011e600ef003a004ee33696235daa"  # Public video stream
    write_video_stream(camera_url)
