import logging
import os
import pprint
import random
import subprocess
from pathlib import Path
from uuid import UUID

from decorator import decorator
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from wanvr.rtsp_recorder.camera_handling import VideoStreamWriterFfmpeg
from wacryptolib.container import (
    encrypt_data_into_container,
    dump_container_to_filesystem,
    LOCAL_ESCROW_MARKER,
    SHARED_SECRET_MARKER, ContainerStorage, AUTHENTICATION_DEVICE_ESCROW_MARKER,
)
from wacryptolib.key_storage import FilesystemKeyStoragePool

logger = logging.getLogger()

DEFAULT_FILES_ROOT = Path(os.environ.get("WA_DEFAULT_FILES_ROOT", Path.home() / "WitnessAngelWard")).resolve()
DEFAULT_FILES_ROOT.mkdir(exist_ok=True)

print("WA_DEFAULT_FILES_ROOT is", DEFAULT_FILES_ROOT)

_filesystem_key_storage_pool_path = Path(os.environ.get("WA_KEY_STORAGE_POOL", DEFAULT_FILES_ROOT / "key_storage_pool")).resolve()
_filesystem_key_storage_pool_path.mkdir(exist_ok=True)
filesystem_key_storage_pool = FilesystemKeyStoragePool(
    root_dir=_filesystem_key_storage_pool_path
)

_filesystem_container_storage_path = Path(os.environ.get("WA_INTERNAL_CONTAINER_STORAGE", DEFAULT_FILES_ROOT / "container_storage")).resolve()
_filesystem_container_storage_path.mkdir(exist_ok=True)
filesystem_container_storage = ContainerStorage(
        default_encryption_conf=None,
        containers_dir=_filesystem_container_storage_path,
        key_storage_pool=filesystem_key_storage_pool,
        max_workers=1, # Protects memory usage
        max_containers_count=4*24*1)  # 1 DAY OF DATA FOR NOW!!!

rtsp_recordings_folder = Path(os.environ.get("WA_TEMP_RECORDING_FOLDER", DEFAULT_FILES_ROOT / "temp_recordings"))
rtsp_recordings_folder.mkdir(exist_ok=True)

decrypted_records_folder = Path(os.environ.get("WA_DECRYPTED_RECORDS_FOLDER", DEFAULT_FILES_ROOT / "decrypted_records")).resolve()
decrypted_records_folder.mkdir(exist_ok=True)

preview_image_path = Path(os.environ.get("WA_PREVIEW_IMAGE_PATH", DEFAULT_FILES_ROOT / "preview_image.jpg"))


# FIXME move this to wacryptolib in common with wamobile?
@decorator
def safe_catch_unhandled_exception(f, *args, **kwargs):
    try:
        return f(*args, **kwargs)
    except Exception as exc:
        try:
            logger.error(
                f"Caught unhandled exception in call of function {f!r}: {exc!r}",
                exc_info=True,
            )
        except Exception as exc2:
            print(
                f"Beware, service callback {f!r} and logging system are both broken: {exc2!r}"
            )


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

    @safe_catch_unhandled_exception
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
        # FIXME see https://stackoverflow.com/a/4425466/11581928 to use ffmpeg instead of opencv
        # see https://gist.github.com/ExpandOcean/de261e66949009f44ad2  kivy and opencv work together demo
        command = ["ffmpeg", "-i", str(path), "-r", "1", "-vframes", "1", str(preview_image_path), "-y"]  # "-f",  str(preview_image_path.parent) To rescale: -s WxH
        logger.info("Calling preview extraction command: %s", str(command))
        try:
            res = subprocess.run(command, timeout=10)  # Process is killed brutally if timeout
            logger.info("Preview extraction command exited with code %s", res.returncode)
        except subprocess.TimeoutExpired:
            logger.warning("Preview extraction failed with timeout")
        '''
        cap = cv2.VideoCapture(path)
        success, first_frame = cap.read()
        if success:
            cv2.imwrite(str(preview_image_path), first_frame)
        '''
    def get_first_frame(self):
        return self.first_frame

    @safe_catch_unhandled_exception
    def start_processing(self, path_file):
        """Launch a thread where a file will be ciphered"""
        self.extract_first_frame(path=path_file)
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


# FIXME REMOVE THIS USELESS WRAPPER
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

    @safe_catch_unhandled_exception
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

    @safe_catch_unhandled_exception
    def get_status(self):
        """Check if recorder thread is alive (True) or not (False)"""
        self.rtsp_video_recorder.get_ffmpeg_status()

    @safe_catch_unhandled_exception
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
    data = open(path, "rb")  # Save memory, this way
    try:
        os.remove(path=path)  # FIXME what if it fails?
    except PermissionError:
        pass  # On windows, open file can't be removed
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
                              keychain_uid=UUID("06c4ae77-abed-40d9-8adf-82c11261c8d6"),  # Arbitrary but FIXED!
                          )
                      ]
    data_encryption_strata = [
        dict(
             data_encryption_algo="AES_CBC",
             key_encryption_strata=shared_secret_encryption,
             data_signatures=data_signatures)
    ]
    container_conf = dict(data_encryption_strata=data_encryption_strata)

    print(">>>>> USING ENCRYPTION CONF")
    pprint.pprint(container_conf)

    return container_conf
