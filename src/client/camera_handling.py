import cv2
import numpy as np
import logging
import pytest
import os
import time

logger = logging.getLogger()


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
        self.timeout = timeout

    def display_video_stream(self):
        cap = cv2.VideoCapture(self.video_stream_url)
        if not cap.isOpened():
            logger.debug("Opening video capture")
            cap.open(self.video_stream_url)

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
            cap.open(self.video_stream_url)

        frame_count = 0
        while cap.isOpened():
            self._simulate_gui()
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

    def pause(self):
        self.on_pause = True

    def unpause(self):
        self.on_pause = False

    def exit_cap(self):
        self.quit = True

    def _simulate_gui(self):
        """Test function which will disappear when GUI will be done"""
        key_pressed = cv2.waitKey(1) & 0xFF
        if key_pressed == ord("p"):
            self.pause()
        if key_pressed == ord("c"):
            self.unpause()
        if key_pressed == ord("q"):
            self.exit_cap()

    def change_recording_file(self, frame_width, frame_height):
        logger.debug("Changing recording file")
        time_beginning_video = time.strftime("%m-%d-%Y_%H-%M-%S")
        filename = f"saved_video_stream/{time_beginning_video}.avi"
        fps = 10

        out = cv2.VideoWriter(
            filename,
            cv2.VideoWriter_fourcc("M", "J", "P", "G"),
            fps,
            (frame_width, frame_height),
        )
        
        return out
