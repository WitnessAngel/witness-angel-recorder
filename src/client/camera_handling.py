import cv2
import numpy as np
import logging
import pytest
import datetime

logger = logging.getLogger()


class VideoStream:
    def __init__(self, video_stream_url=None):
        self.video_stream_url = video_stream_url
        self.on_pause = False
        self.quit = False
        self.time = datetime.time(0, 0, 0)

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
        out = cv2.VideoWriter(
            "saved_video_stream/outpy.avi",
            cv2.VideoWriter_fourcc("M", "J", "P", "G"),
            10,
            (frame_width, frame_height),
        )

        while cap.isOpened():
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
