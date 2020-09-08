import logging
import os
from concurrent.futures.thread import ThreadPoolExecutor
from pathlib import Path

from client.camera_handling import VideoStreamWriterFfmpeg
from client.utilities.misc import safe_catch_unhandled_exception
from wacryptolib.container import (
    encrypt_data_into_container,
    dump_container_to_filesystem,
)
from wacryptolib.key_generation import generate_asymmetric_keypair
from wacryptolib.key_storage import FilesystemKeyStorage
from wacryptolib.utilities import generate_uuid0
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger()

filesystem_key_storage = FilesystemKeyStorage(
    keys_dir=os.environ.get("FILE_SYSTEM_KEY_STORAGE")
)


class NewVideoHandler(FileSystemEventHandler):
    """Process each file in the directory where video files are stored"""

    def __init__(self, recordings_folder, key_type, conf, metadata=None):
        self.recordings_folder = recordings_folder

        self.key_type = key_type
        self.conf = conf
        self.metadata = metadata

        self.THREAD_POOL_EXECUTOR = ThreadPoolExecutor()
        self.pending_files = os.listdir(self.recordings_folder)
        self.pending_files[:] = [
            os.path.join("ffmpeg_video_stream", filename)
            for filename in self.pending_files
        ]
        self.pending_files.sort(key=os.path.getmtime)

    def start_observer(self):
        self.observer = Observer()
        self.observer.schedule(self, path="ffmpeg_video_stream/", recursive=True)
        logger.debug("Observer thread started")
        self.observer.start()

    def process_pending_files(self):
        while self.pending_files:
            last_file = self.pending_files.pop()
            self.start_processing(path_file=last_file)

    def on_created(self, event):
        self.process_pending_files()
        self.pending_files.append(event.src_path)

    @safe_catch_unhandled_exception
    def start_processing(self, path_file):
        """Launch a thread where a file will be ciphered"""
        return self.THREAD_POOL_EXECUTOR.submit(
            self._offloaded_start_processing, path_file
        )

    @safe_catch_unhandled_exception
    def _offloaded_start_processing(self, path_file):
        logger.debug("Starting thread processing for {}".format(path_file))
        key_pair = generate_asymmetric_keypair(key_type=self.key_type)
        keychain_uid = generate_uuid0()
        filesystem_key_storage.set_keys(
            keychain_uid=keychain_uid,
            key_type=self.key_type,
            public_key=key_pair["public_key"],
            private_key=key_pair["private_key"],
        )

        logger.debug("Beginning encryption for {}".format(path_file))
        data = get_data_then_delete_videofile(path=path_file)
        container = encrypt_data_into_container(
            conf=self.conf, data=data, metadata=self.metadata, keychain_uid=keychain_uid
        )

        logger.debug("Saving container of {}".format(path_file))
        save_container(video_filepath=path_file, container=container)

        logger.debug("Finished processing thread for {}".format(path_file))

    @safe_catch_unhandled_exception
    def stop_new_files_processing_and_wait(self):
        logger.debug("Stop observer thread")
        self.observer.stop()

        logger.debug("Launch last files")
        self.process_pending_files()
        self.observer.join()

        logger.debug("Shutdown")
        self.THREAD_POOL_EXECUTOR.shutdown()


class RtspVideoRecorder:
    """Generic wrapper around some actual recorder implementation"""

    def __init__(self, camera_url, recording_time, segment_time):
        self.writer_ffmpeg = VideoStreamWriterFfmpeg(
            video_stream_url=camera_url,
            recording_time=recording_time,
            segment_time=segment_time,
        )

    @safe_catch_unhandled_exception
    def start_recording(self):
        logger.debug("Video stream writer thread started")
        self.writer_ffmpeg.start_writing()

    @safe_catch_unhandled_exception
    def stop_recording_and_wait(self):
        """Transmit stop call to VideoStreamWriterFfmpeg and wait on it"""
        logger.debug("Video stream writing thread stopped and waiting")
        self.writer_ffmpeg.stop_writing()

    def get_ffmpeg_status(self):
        return self.writer_ffmpeg.is_alive()


class RecordingToolchain:
    """Permits to handle every threads implied in the recording toolchain"""

    def __init__(
        self,
        recordings_folder,
        conf,
        key_type,
        camera_url,
        recording_time,
        segment_time,
    ):
        self.new_video_handler = NewVideoHandler(
            recordings_folder=recordings_folder, conf=conf, key_type=key_type
        )
        self.rtsp_video_recorder = RtspVideoRecorder(
            camera_url=camera_url,
            recording_time=recording_time,
            segment_time=segment_time,
        )

    @safe_catch_unhandled_exception
    def launch_recording_toolchain(self):
        """Launch every threads"""
        logger.debug("Beginning recording toolchain thread")
        self.new_video_handler.start_observer()
        self.rtsp_video_recorder.start_recording()

    @safe_catch_unhandled_exception
    def stop_recording_toolchain_and_wait(self):
        """Stop and wait every threads"""
        self.rtsp_video_recorder.stop_recording_and_wait()
        self.new_video_handler.stop_new_files_processing_and_wait()

    def get_status(self):
        """Check if recorder thread is alive (True) or not (False)"""
        self.rtsp_video_recorder.get_ffmpeg_status()


def save_container(video_filepath: str, container: dict):
    """
    Save container of a video in a .txt file as bytes.

    :param video_filepath: path to .avi video file
    :param container: ciphered data to save of video stored at video_filepath
    """
    filename, extension = os.path.splitext(video_filepath)
    dir_name, file = filename.split("/")
    container_filepath = Path(
        os.path.abspath("ciphered_video_stream/{}.crypt".format(file))
    )
    dump_container_to_filesystem(
        container_filepath=container_filepath, container=container
    )


# TODO - maybe we should tweak all Wacryptolib utils so that they coerce to Path() their inputs ? Or just raise instead...


def get_data_then_delete_videofile(path: str) -> bytes:
    """Read video file's data then delete the file from system"""
    with open(path, "rb") as file:
        data = file.read()
    os.remove(path=path)
    logger.debug("file {} has been deleted from system".format(path))
    return data
