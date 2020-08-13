import cv2
import numpy as np
import logging
import pytest
import os
import time

logger = logging.getLogger()


class VideoStream:
    def __init__(self, timeout, video_stream_url=None):
        self.video_stream_url = video_stream_url
        self.on_pause = False
        self.quit = False
        self.timeout = timeout

    def display_video_stream(self):
        cap = cv2.VideoCapture(self.video_stream_url)
        if not cap.isOpened():
            logger.debug("Opening video capture")
            cap.open()

        while cap.isOpened():
            ret, frame = cap.read()

            if not ret:
                logger.debug("No image retrieved")
                cap.release()
                cv2.destroyAllWindows()
                raise ValueError

            cv2.imshow("frame", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        logger.debug("Closing video capture")
        cap.release()
        cv2.destroyAllWindows()

    def write_video_stream(self):
        cap = cv2.VideoCapture(self.video_stream_url)
        frame_width = int(cap.get(3))
        frame_height = int(cap.get(4))

        if not os.path.isdir("saved_video_stream"):
            logger.debug("Creating directory 'saved_video_stream'")
            os.mkdir("saved_video_stream")

        fps = 10
        out = self.change_recording_file(
            frame_width=frame_width, frame_height=frame_height
            )

        if not cap.isOpened():
            cap.open()
        frame_count = 0
        while cap.isOpened():
            self.get_state()
            ret, frame = cap.read()

            if not ret:
                logger.debug("No image retrieved")
                cap.release()
                cv2.destroyAllWindows()
                raise ValueError

            if not self.on_pause:
                out.write(frame)

            frame_count += 1
            duration = frame_count/fps
            if duration >= self.timeout:
                logger.debug("Closing video writer")
                out.release()
                out = self.change_recording_file(
                    frame_width=frame_width, frame_height=frame_height 
                )
                frame_count = 0

            cv2.imshow("frame", frame)
            if self.quit:
                break

        logger.debug("Closing video capture")
        cap.release()

        logger.debug("Closing video writer")
        out.release()

        cv2.destroyAllWindows()

    def get_state(self):
        key_pressed = cv2.waitKey(1) & 0xFF
        if key_pressed == ord("p"):
            self.on_pause = True
        if key_pressed == ord("c"):
            self.on_pause = False
        if key_pressed == ord("q"):
            self.quit = True

    def change_recording_file(self, frame_width, frame_height):
        logger.debug("Changing recording file")
        filename = "saved_video_stream/" + str(time.strftime("%m-%d-%Y_%H-%M-%S")) + ".avi"
        fps = 10

        out = cv2.VideoWriter(
            filename,
            cv2.VideoWriter_fourcc("M", "J", "P", "G"),
            fps,
            (frame_width, frame_height),
        )
        
        return out

