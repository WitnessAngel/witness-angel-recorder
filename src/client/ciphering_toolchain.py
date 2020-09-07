from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path
import logging
import time
import os
from threading import Thread, Event
from concurrent.futures.thread import ThreadPoolExecutor

from client.camera_handling import VideoStreamWriterFfmpeg
from wacryptolib.container import (
    encrypt_data_into_container,
    decrypt_data_from_container,
    dump_container_to_filesystem,
    load_container_from_filesystem,
)
from wacryptolib.key_generation import (
    generate_asymmetric_keypair,
    load_asymmetric_key_from_pem_bytestring,
)
from wacryptolib.key_storage import FilesystemKeyStorage
from wacryptolib.encryption import encrypt_bytestring, decrypt_bytestring
from wacryptolib.utilities import generate_uuid0

logger = logging.getLogger()

THREAD_POOL_EXECUTOR = ThreadPoolExecutor()  # FIXME make this an instance attribute of NewVideoHandler

filesystem_key_storage = FilesystemKeyStorage(
    keys_dir="D:/Users/manon/Documents/GitHub/witness-ward-client/tests/keys"  # TODO remove asap
)


class NewVideoHandler(FileSystemEventHandler):
    def __init__(self, recordings_folder, key_type, conf, metadata=None):
        self.recordings_folder = recordings_folder

        self.key_type = key_type
        self.conf = conf
        self.metadata = metadata

        self._termination_event = Event()
        self.pending_files = os.listdir(self.recordings_folder)  # TODO later : sort by date and treat [:-1]

    def process_pending_files(self):
        pass  # TODO - This utility would be useful both to on_created() and stop_observer()

    def on_created(self, event):
        # FIXME just pop() and treat ALL entries which might be here, THEN append new path (it's more resilient this way)
        self.pending_files.append(event.src_path)
        try:
            self.start_processing(path_file=self.pending_files[-2])
        except IndexError:
            pass

    def start_processing(self, path_file):
        return THREAD_POOL_EXECUTOR.submit(self._offloaded_start_processing, path_file)

    def _offloaded_start_processing(self, path_file):
        logger.debug("Starting thread processing for {}".format(path_file))
        key_pair = generate_asymmetric_keypair(key_type=self.key_type)
        keychain_uid = get_uuid0()
        filesystem_key_storage.set_keys(
            keychain_uid=keychain_uid,
            key_type=self.key_type,
            public_key=key_pair["public_key"],
            private_key=key_pair["private_key"],
        )

        logger.debug("Beginning encryption for {}".format(path_file))
        data = get_data_from_video(path=path_file)
        container = apply_entire_encryption_algorithm(
            key_type=self.key_type,
            conf=self.conf,
            data=data,
            metadata=self.metadata,
            keychain_uid=keychain_uid,
        )

        logger.debug("Saving container of {}".format(path_file))
        save_container(video_filepath=path_file, container=container)
        logger.debug("Finished processing thread for {}".format(path_file))
        if path_file == self.pending_files[-1]:
            self._termination_event.set()
            return self._termination_event.is_set()

    def launch_termination(self):
        last_path_file = self.pending_files[-1]
        self.start_processing(last_path_file)  # FIXME someone must wait this job too


class RtspVideoRecorder:
    def __init__(self, camera_url, new_video_handler, recording_time, segment_time):
        self.new_video_handler = new_video_handler
        self.camera_url = camera_url
        self.recording_time = recording_time
        self.segment_time = segment_time

    def start_recording(self):
        return THREAD_POOL_EXECUTOR.submit(self._offloaded_start_recording)  # FIXME no need for this

    def _offloaded_start_recording(self):
        logger.debug("Video stream writer thread started")
        writer_ffmpeg = VideoStreamWriterFfmpeg(
            video_stream_url=self.camera_url, recording_time=self.recording_time, segment_time=self.segment_time
        )
        writer_ffmpeg.start()

        time.sleep(30)
        # self.join()
        logger.debug("Video stream writer thread stopped")
        self.new_video_handler.launch_termination()
        writer_ffmpeg.stop()
        return writer_ffmpeg.done


class RecordingToolchain(Thread):  # FIXME - doesn't have to be a thread
    def __init__(self, recordings_folder, conf, key_type, camera_url, recording_time, segment_time):
        Thread.__init__(self)
        self._termination_event = Event()
        self.camera_url = camera_url
        self.conf = conf
        self.key_type = key_type
        self.recordings_folder = recordings_folder
        self.recording_time = recording_time
        self.segment_time = segment_time

    def _offloaded_launch_recording_toolchain(self):  #FIXME - this is not an offloaded method here
        logger.debug("Beginning recording toolchain thread")
        new_video_handler = NewVideoHandler(
            recordings_folder=self.recordings_folder,
            conf=self.conf,
            key_type=self.key_type,
        )
        rtsp_video_recorder = RtspVideoRecorder(
            camera_url=self.camera_url,
            new_video_handler=new_video_handler,
            recording_time=self.recording_time,
            segment_time=self.segment_time
        )
        self.observer_future = THREAD_POOL_EXECUTOR.submit(  # FIXME Excessive creation of intermediate thread
            create_observer_thread, new_video_handler
        )
        self.recorder_future = THREAD_POOL_EXECUTOR.submit(  # FIXME Excessive creation of intermediate thread
            rtsp_video_recorder.start_recording
        )

    def launch_recording_toolchain(self):
        self.start()
        self._offloaded_launch_recording_toolchain()
        if self.recorder_future.result() and self.observer_future.result():
            self.join()
            logger.debug("End recording toolchain thread")


def save_container(video_filepath: str, container: dict):
    """
    Save container of a video in a .txt file as bytes.

    :param video_filepath: path to .avi video file
    :param container: ciphered data to save of video stored at video_filepath
    """
    filename, extension = os.path.splitext(video_filepath)
    dir_name, file = filename.split("/")
    container_filepath = Path("ciphered_video_stream/{}.crypt".format(file))  # TODO - we should use absolute paths asap
    logger.debug(container_filepath)
    dump_container_to_filesystem(
        container_filepath=container_filepath, container=container
    )

# TODO - maybe we should tweak all Wacryptolib utils so that they coerce to Path() their inputs ? Or just raise instead...

def get_container(container_filepath: str):  # FIXME rather use Path objects everywhere and avoid such wrappers
    container_filepath = Path(container_filepath)
    container = load_container_from_filesystem(container_filepath=container_filepath)
    return container


def get_data_from_video(path: str) -> bytes:  # Fixme improve fallacious naming here
    with open(path, "rb") as file:
        data = file.read()
    os.remove(path=path)
    logger.debug("file {} has been deleted from system".format(path))
    return data


def create_observer_thread(new_video_handler: classmethod):
    """
    Create a thread where an observer check recursively a new file in the directory /ffmpeg_video_stream
    """
    observer = Observer()
    observer.schedule(new_video_handler, path="ffmpeg_video_stream/", recursive=True)
    logger.debug("Observer thread started")
    observer.start()
    # FIXME - the observer should just be returned, so that the orchestrator of the system stop() it on shutdown ; no need to block current thread
    try:
        while True:
            time.sleep(0.5)
    except:
        observer.stop()
        logger.debug("Observer thread Stopped")
