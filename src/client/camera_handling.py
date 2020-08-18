import cv2
from numpy import asarray
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

    def _get_video_capture(self):
        cap = cv2.VideoCapture(self.video_stream_url)
        if not cap.isOpened():
            logger.debug("Opening video capture")
            cap.open(self.video_stream_url)
        return cap

    def _read_video_capture(self, cap):
        ret, frame = cap.read()
        if not ret:
            logger.debug("No image retrieved")
            cap.release()
            cv2.destroyAllWindows()
            raise ValueError
        return frame

    def display_video_stream(self):
        cap = self._get_video_capture()

        while cap.isOpened():
            frame = self._read_video_capture(cap=cap)

            cv2.imshow("frame", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        logger.debug("Closing video capture")
        cap.release()
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

    @staticmethod
    def _change_recording_array(entire_videos, video):
        logger.debug("Changing recording file")
        time_beginning_video = time.strftime("%m-%d-%Y_%H-%M-%S")
        entire_videos[time_beginning_video] = video

    def write_video_stream(self):
        cap = self._get_video_capture()

        fps = 10
        entire_videos = {}
        video = []
        frame_count = 0

        while cap.isOpened():
            self._simulate_gui()
            frame = self._read_video_capture(cap=cap)

            if not self.on_pause:
                data = asarray(frame)
                video.append(data)
                frame_count += 1

            duration = frame_count/fps
            if duration >= self.timeout:
                logger.debug("Closing video writer")
                self._change_recording_array(entire_videos=entire_videos, video=video)
                video = []
                frame_count = 0

            cv2.imshow("frame", frame)
            if self.quit:
                break

        logger.debug("Closing video capture")
        cap.release()
        cv2.destroyAllWindows()
        self._change_recording_array(entire_videos=entire_videos, video=video)

        return entire_videos
