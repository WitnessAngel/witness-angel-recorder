import cv2
import numpy as np
import logging
import pytest

logger = logging.getLogger()


class VideoStream:
    def __init__(self, video_stream_url=None):
        self.video_stream_url = video_stream_url

    def display_video_stream(self):
        cap = cv2.VideoCapture(self.video_stream_url)

        while True:
            ret, frame = cap.read()
            if not ret:
                cap.release()
                cv2.destroyAllWindows()
                raise ValueError
            cv2.imshow('frame', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        cv2.destroyAllWindows()

    def write_video_stream(self):
        cap = cv2.VideoCapture(self.video_stream_url)
        # assert cap.isOpened(), "Error opening video stream"
        frame_width = int(cap.get(3))
        frame_height = int(cap.get(4))
        out = cv2.VideoWriter(
            'saved_video_stream/outpy.avi', cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'), 10, (frame_width, frame_height)
        )

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                cap.release()
                cv2.destroyAllWindows()
                raise ValueError
            out.write(frame)
            cv2.imshow('frame', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        out.release()
        cv2.destroyAllWindows()
