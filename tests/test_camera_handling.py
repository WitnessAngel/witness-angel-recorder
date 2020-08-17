import pytest
from client.camera_handling import VideoStream
from os.path import isdir, isfile
from os import listdir
from moviepy.editor import VideoFileClip


def test_display_video_stream():
    camera_url = (
        "rtsp://170.93.143.139/rtplive/470011e600ef003a004ee33696235daa"
    )  # Public video stream
    video_stream = VideoStream(timeout=10.0, video_stream_url=camera_url)
    video_stream.display_video_stream()

    assert isdir("saved_video_stream")


def test_write_video_stream():
    camera_url = (
        "rtsp://170.93.143.139/rtplive/470011e600ef003a004ee33696235daa"
    )  # Public video stream
    timeout = 10.0
    video_stream = VideoStream(timeout=timeout, video_stream_url=camera_url)
    video_stream.write_video_stream()

    assert isdir("saved_video_stream")
    video_files = listdir("saved_video_stream")
    for file in video_files:
        filename = "saved_video_stream/" + str(file)
        assert isfile(filename)
        clip = VideoFileClip(filename)
        assert clip.duration <= timeout
