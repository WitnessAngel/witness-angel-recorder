import logging
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from subprocess import TimeoutExpired

logger = logging.getLogger()


class VideoStreamWriterOpenCV:
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
            cap.open(self.video_stream_url)

        while True:
            ret, frame = cap.read()
            try:
                cv2.imshow("frame", frame)
            except cv2.error:
                raise ValueError("Frame is empty.")
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

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

    def write_video_stream(self):
        cap = cv2.VideoCapture(self.video_stream_url)
        if not cap.isOpened():
            cap.open(self.video_stream_url)

        frame_width = int(cap.get(3))
        frame_height = int(cap.get(4))

        if not os.path.isdir("saved_video_stream"):
            logger.debug("Creating directory 'saved_video_stream'")
            os.mkdir("saved_video_stream")

        fps = 10
        out = self.change_recording_file(
            frame_width=frame_width, frame_height=frame_height
        )

        frame_count = 0
        while True:
            self._simulate_gui()
            logger.debug("Read a frame")
            ret, frame = cap.read()

            if not self.on_pause:
                try:
                    logger.debug("Write a frame")
                    out.write(frame)
                except cv2.error:
                    raise ValueError("Frame is empty.")

            frame_count += 1
            duration = frame_count / fps
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


class VideoStreamWriterFfmpeg(threading.Thread):

    process = None  # Popen instance for Ffmpeg

    _stopped = False   # Signals that recoding should stop

    def __init__(self, video_stream_url, recording_time, segment_time, output_folder):
        super().__init__(name="VideoStreamWriterFfmpeg")

        self.input = ["-i", video_stream_url]

        # If recording_time is None, recording will never stop by himself
        self.recording_duration = [] if recording_time is None else ["-t", str(recording_time)]

        self.segment_duration = ["-segment_time", str(segment_time)]
        self.process = None
        self.output_folder = Path(output_folder)

    def _launch_and_wait_ffmpeg_process(self):

        date_prefix = datetime.utcnow().strftime("%Y%m%d%H%M%S")

        exec = [
            "ffmpeg",
            "-rtsp_transport",
            "tcp"]
        codec = [
            "-vcodec",
            "copy",
            "-acodec",
            "copy",
            "-map",
            "0"]
        segment = [
            "-f",
            "segment"]
        format = [
            "-segment_format",
            "mp4",
            str(self.output_folder.joinpath(date_prefix+"_ffmpeg_capture-%03d.mp4")),
            "-y",
        ]
        logs = [
            "-loglevel",
            "warning"
        ]

        pipeline = exec + self.input + codec + self.recording_duration + segment + self.segment_duration + format + logs
        logger.info("Calling subprocess command: {}".format(" ".join(pipeline)))
        self.process = subprocess.Popen(pipeline, stdin=subprocess.PIPE)
        returncode = self.process.wait()

        if returncode:
            logger.warning("recorder process exited with abnormal code %s", returncode)


    def run(self):
        while not self._stopped:
            # Process might have stopped due to end of record time, or to crash
            self._launch_and_wait_ffmpeg_process()

    def start_writing(self):
        self.start()


    def stop_writing(self):  # FIXME - might be called before process has finished setup!
        self._stopped = True
        try:
            self.process.communicate(b"q", timeout=5)  # Clean exit of ffmpeg
        except TimeoutExpired:
            logger.warning("Killing ffmpeg subprocess which didn't stop via std input command")
            self.process.terminate()
        #graceful_exit_signal = signal.SIGTERM  #CTRL_BREAK_EVENT  # TODO add linux version
        #logger.info("Sending signal %s to gracefully terminate ffmpeg process %s", graceful_exit_signal, self.process.pid)
        #self.process.terminate()  #
        #self.process.send_signal(graceful_exit_signal)
        logger.info("Sent quit key to ffmpeg, waiting for VideoStreamWriterFfmpeg thread exit")
        self.join()

    def get_writer_status(self):
        return self.is_alive()
