import logging
import os
import pprint
import uuid
from uuid import UUID

import cv2
import random
from concurrent.futures.thread import ThreadPoolExecutor
from pathlib import Path

from client.camera_handling import VideoStreamWriterFfmpeg
from client.utilities.misc import safe_catch_unhandled_exception
from wacryptolib.container import (
    encrypt_data_into_container,
    dump_container_to_filesystem,
    LOCAL_ESCROW_MARKER,
    SHARED_SECRET_MARKER, ContainerStorage, AUTHENTICATION_DEVICE_ESCROW_MARKER,
)
from wacryptolib.key_storage import FilesystemKeyStorage, FilesystemKeyStoragePool
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger()

_filesystem_key_storage_path = Path(os.environ.get("FILE_SYSTEM_KEY_STORAGE", "filesystem_key_storage"))
_filesystem_key_storage_path.mkdir(exist_ok=True)
filesystem_key_storage_pool = FilesystemKeyStoragePool(
    root_dir=_filesystem_key_storage_path
)

_filesystem_container_storage_path = Path(os.environ.get("CONTAINER_STORAGE", "container_storage"))
_filesystem_container_storage_path.mkdir(exist_ok=True)
filesystem_container_storage = ContainerStorage(default_encryption_conf=None, containers_dir=_filesystem_container_storage_path, key_storage_pool=filesystem_key_storage_pool, max_workers=os.cpu_count() or 1, max_containers_count=6)

rtsp_recordings_folder = Path(os.environ.get("RECORDING_FOLDER", "ffmpeg_video_stream"))
rtsp_recordings_folder.mkdir(exist_ok=True)


class NewVideoHandler(FileSystemEventHandler):
    """Process each file in the directory where video files are stored"""

    def __init__(self, recordings_folder, key_type, conf, metadata=None):
        self.recordings_folder = recordings_folder
        assert os.path.exists(recordings_folder), recordings_folder

        self.key_type = key_type
        self.conf = conf
        self.metadata = metadata

        #self.THREAD_POOL_EXECUTOR = ThreadPoolExecutor()
        self.pending_files = os.listdir(self.recordings_folder)
        self.pending_files[:] = [
            os.path.join(self.recordings_folder, filename)
            for filename in self.pending_files
        ]
        self.pending_files.sort(key=os.path.getmtime)  # FIXME we'd need immediate flush too here

        self.observer = Observer()
        self.first_frame = None

    def start_observer(self):
        self.observer.schedule(self, path=str(self.recordings_folder), recursive=True)
        logger.debug("Observer thread started")
        self.observer.start()

    def process_pending_files(self):
        pending_files = self.pending_files[:]

        logger.info("We process pending files %s", pending_files)

        del self.pending_files[:]  # Immediate cleanup
        for pending_file in pending_files:
            self.start_processing(path_file=pending_file)

    def on_created(self, event):
        self.process_pending_files()
        self.pending_files.append(event.src_path)

    def extract_first_frame(self, path):
        cap = cv2.VideoCapture(path)
        while self.first_frame is None:
            ret, self.first_frame = cap.read()

    def get_first_frame(self):
        return self.first_frame

    @safe_catch_unhandled_exception
    def start_processing(self, path_file):
        """Launch a thread where a file will be ciphered"""
        data = get_data_then_delete_videofile(path=path_file)
        filesystem_container_storage.enqueue_file_for_encryption(
                filename_base=Path(path_file).name, data=data, metadata=None, keychain_uid=None, encryption_conf=self.conf)
        """
        return self.THREAD_POOL_EXECUTOR.submit(
            self._offloaded_start_processing, path_file
        )"""

    @safe_catch_unhandled_exception
    def ______offloaded_start_processing(self, path_file):
        logger.debug("Starting thread processing for {}".format(path_file))
        # key_pair = generate_asymmetric_keypair(key_type=self.key_type)
        # keychain_uid = generate_uuid0()
        # filesystem_key_storage.set_keys(
        #     keychain_uid=keychain_uid,
        #     key_type=self.key_type,
        #     public_key=key_pair["public_key"],
        #     private_key=key_pair["private_key"],
        # )

        logger.debug("Beginning encryption for {}".format(path_file))

        container = encrypt_data_into_container(
            conf=self.conf,
            data=data,
            metadata=self.metadata,
            key_storage_pool=filesystem_key_storage_pool
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

        #logger.debug("Shutdown THREAD_POOL_EXECUTOR")
        #self.THREAD_POOL_EXECUTOR.shutdown()



class RtspVideoRecorder:
    """Generic wrapper around some actual recorder implementation"""

    def __init__(self, camera_url, recording_time, segment_time, output_folder):
        self.writer_ffmpeg = VideoStreamWriterFfmpeg(
            video_stream_url=camera_url,
            recording_time=recording_time,
            segment_time=segment_time,
            output_folder=output_folder,
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
            output_folder=recordings_folder,
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
        filesystem_container_storage.wait_for_idle_state()

    def get_status(self):
        """Check if recorder thread is alive (True) or not (False)"""
        self.rtsp_video_recorder.get_ffmpeg_status()

    def get_first_frame(self):
        return self.new_video_handler.get_first_frame()


def __save_container(video_filepath: str, container: dict):
    """
    Save container of a video in a .txt file as bytes.

    :param video_filepath: path to .avi video file
    :param container: ciphered data to save of video stored at video_filepath
    """
    filename, extension = os.path.splitext(video_filepath)
    dir_name, file = filename.split("/")
    container_filepath = Path(
        os.path.abspath(".container_storage_ward/{}.crypt".format(file))
    )
    dump_container_to_filesystem(
        container_filepath=container_filepath, container=container
    )


# TODO - maybe we should tweak all Wacryptolib utils so that they coerce to Path() their inputs ? Or just raise instead...


def get_data_then_delete_videofile(path: str) -> bytes:
    """Read video file's data then delete the file from system"""
    with open(path, "rb") as file:
        data = file.read()
    os.remove(path=path)  # FIXME what if it fails?
    logger.debug("file {} has been deleted from system".format(path))
    return data


def _generate_encryption_conf(shared_secret_threshold: int, authentication_devices_used: list):
    info_escrows = []
    for authentication_device_uid in authentication_devices_used:
        key_storage = filesystem_key_storage_pool.get_imported_key_storage(key_storage_uid=authentication_device_uid) # Fixme rename key_storage_uid
        key_information_list = key_storage.list_keypair_identifiers()
        key = random.choice(key_information_list)

        share_escrow = AUTHENTICATION_DEVICE_ESCROW_MARKER.copy()
        share_escrow["authentication_device_uid"] = UUID(authentication_device_uid)

        info_escrows.append(
            dict(
                share_encryption_algo=key["key_type"],
                keychain_uid=key["keychain_uid"],
                share_escrow=share_escrow,
             )
        )
    shared_secret_encryption = [
                                  dict(
                                     key_encryption_algo=SHARED_SECRET_MARKER,
                                     key_shared_secret_threshold=shared_secret_threshold,
                                     key_shared_secret_escrows=info_escrows,
                                  )
                               ]
    data_signatures = [
                          dict(
                              message_prehash_algo="SHA256",
                              signature_algo="DSA_DSS",
                              signature_escrow=LOCAL_ESCROW_MARKER,
                          )
                      ]
    data_encryption_strata = [
        dict(data_encryption_algo="AES_CBC",
             key_encryption_strata=shared_secret_encryption,
             data_signatures=data_signatures)
    ]
    container_conf = dict(data_encryption_strata=data_encryption_strata)

    print(">>>>> USING ENCRYPTION CONF")
    pprint.pprint(container_conf)

    return container_conf
