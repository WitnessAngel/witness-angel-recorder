import cv2
import numpy as np
import logging
import pytest
import time
from datetime import datetime

logger = logging.getLogger()


def create_video_writer(frame_width, frame_height):
    logger.debug("Creating a new video writer")
    date = datetime.now().strftime("%d-%m-%Y-%Hh%Mm%Ss")
    path = "saved_video_stream/{}.avi".format(date)
    out = cv2.VideoWriter(
        path,
        cv2.VideoWriter_fourcc("M", "J", "P", "G"),
        10,
        (frame_width, frame_height),
    )
    return out


class VideoStream:
    def __init__(self, timeout, video_stream_url=None):
        """
        Initialize VideoStream class
        :param video_stream_url: rtsp url to video stream (h264)
        :param timeout: duration in seconds of a .avi saved files
        """
        self.video_stream_url = video_stream_url
        self.timeout = timeout
        self.on_pause = False
        self.quit = False

    def display_video_stream(self):
        """
        Permits to show on a window the video stream.
        """
        cap = cv2.VideoCapture(self.video_stream_url)

        while True:
            ret, frame = cap.read()
            if not ret:
                cap.release()
                cv2.destroyAllWindows()
                raise ValueError
            cv2.imshow("frame", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        cap.release()
        cv2.destroyAllWindows()

    def write_video_stream(self):
        """
        Save as an .avi file the video stream in saved_video_stream directory. If the state of the video stream is
        on pause, images won't be saved until the state changes.
        """
        cap = cv2.VideoCapture(self.video_stream_url)
        frame_width = int(cap.get(3))
        frame_height = int(cap.get(4))
        out = create_video_writer(frame_width=frame_width, frame_height=frame_height)

        time_beginning_video = time.time()

        while cap.isOpened():
            if time.time() >= time_beginning_video + self.timeout:
                out.release()
                out = create_video_writer(frame_width=frame_width, frame_height=frame_height)
                time_beginning_video = time.time()
            self.get_state()
            ret, frame = cap.read()
            if not ret:  # Nothing can be read from cap
                cap.release()
                cv2.destroyAllWindows()
                raise ValueError
            if not self.on_pause:
                out.write(frame)
            cv2.imshow("frame", frame)
            if self.quit:  # quit
                break

        cap.release()
        out.release()
        cv2.destroyAllWindows()

    def get_state(self):
        """
        Changes state of the video stream according to condition (WILL CHANGE WHEN GUI WILL BE DONE).
        """
        key_pressed = cv2.waitKey(1) & 0xFF
        if key_pressed == ord("p"):
            self.on_pause = True
        if key_pressed == ord("c"):
            self.on_pause = False
        if key_pressed == ord("q"):
            self.quit = True
