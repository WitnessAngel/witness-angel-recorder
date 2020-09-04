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


def apply_entire_encryption_algorithm(  # TODO replace by container system
    key_type: str, conf: dict, data: bytes, keychain_uid, metadata=None
) -> dict:
    """
    Apply entire encryption algorithm, from video data file to dictionary which contains ciphered data and container to
    decipher private_key

    :param key_type: symmetric algorithm used to cipher video data
    :param conf: dictionary with configuration tree
    :param data: video file data
    :param keychain_uid: unique uuid of used keypair
    :param metadata: optional data to put into container

    :return: dictionary which contains every information to decipher video file
    """
    logger.debug("Ciphering data")
    ciphered_data = encrypt_video_stream(
        data=data, encryption_algo=key_type, keychain_uid=keychain_uid
    )

    logger.debug("Encrypting symmetric key")
    container_private_key = encrypt_symmetric_key(
        conf=conf,
        metadata=metadata,
        encryption_algo=key_type,
        keychain_uid=keychain_uid,
    )

    encryption_data = {
        "encryption_algo": key_type,
        "data_ciphertext": ciphered_data,
        "private_key": container_private_key,
    }
    logger.debug("Data has been encrypted")
    return encryption_data


def apply_entire_decryption_algorithm(encryption_data: dict) -> bytes:  # TODO replace by container system
    """
    Apply entire decryption algorithm, from ciphered data in dictionary to video file as bytes

    :param encryption_data: dictionary returned by apply_entire_encryption_algorithm

    :return: video file as bytes
    """
    logger.debug("Deciphering private key")
    deciphered_private_key = decrypt_symmetric_key(
        container=encryption_data["private_key"],
        key_type=encryption_data["encryption_algo"],
    )

    logger.debug("Deciphering data")
    data = decrypt_video_stream(
        cipherdict=encryption_data["data_ciphertext"],
        encryption_algo=encryption_data["encryption_algo"],
        key=deciphered_private_key,
    )

    return data


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


def get_uuid0(ts=None):  # FIXME - no need for this wrapper :?
    """
    Generate a random UUID according to current or given timestamp

    :param ts: optional timestamp to use instead of current time (if not falsey)

    :return: uuid0 object (subclass of UUID)
    """
    return generate_uuid0(ts=ts)


def get_assymetric_keypair(key_type: str, key_length_bits=2048) -> dict:  # FIXME - no need for this wrapper :?
    """
    Generate a (private_key, public_key) keypair

    :param key_type: algorithm to be used to create keypair
    :param key_length_bits: wanted length of key as bits

    :return: dict which contains private_key and public_key
    """
    keypair = generate_asymmetric_keypair(
        key_type=key_type, serialize=False, key_length_bits=key_length_bits
    )
    return keypair


def encrypt_video_stream(data: bytes, encryption_algo: str, keychain_uid) -> dict:  # FIXME - why reinvent this container subsystem?
    """
    Put the video stream data saved in an .avi files into a container

    :param keychain_uid: unique uuid of used keypair
    :param encryption_algo: name of algorithm used to encrypt
    :param data: video files as bytes

    :return: dictionary which contains every information to decrypt container
    """
    bytes_public_key = filesystem_key_storage.get_public_key(
        keychain_uid=keychain_uid, key_type=encryption_algo
    )
    public_key = load_asymmetric_key_from_pem_bytestring(
        key_pem=bytes_public_key, key_type=encryption_algo
    )

    cipherdict = encrypt_bytestring(
        plaintext=data, encryption_algo=encryption_algo, key=public_key
    )
    return cipherdict


def decrypt_video_stream(cipherdict: dict, encryption_algo: str, key) -> bytes:  # FIXME - why reinvent this container subsystem?
    """
    Decipher container where a video stream saved as an .avi file has been ciphered

    :param key: private key from initial assymetric keypair
    :param encryption_algo: name of algorithm used to decrypt
    :param cipherdict: dictionary which contains every information to decrypt data, returned by encrypt_video_stream

    :return: initial data decrypted
    """
    initial_data = decrypt_bytestring(
        cipherdict=cipherdict, encryption_algo=encryption_algo, key=key
    )
    return initial_data


def encrypt_symmetric_key(  # FIXME - why reinvent this container subsystem?
    conf: dict, encryption_algo: str, metadata: dict, keychain_uid
) -> dict:
    """
    Permits to encrypt the private symmetric key.

    :param keychain_uid: unique uuid of used keypair
    :param conf: configuration tree
    :param metadata: optional metadata
    :param keychain_uid: optional ID of a keychain to reuse

    :return: dict of container
    """
    private_key = filesystem_key_storage.get_private_key(
        keychain_uid=keychain_uid, key_type=encryption_algo
    )

    container_private_key = encrypt_data_into_container(
        data=private_key,
        conf=conf,
        keychain_uid=keychain_uid,
        metadata=metadata,
        local_key_storage=filesystem_key_storage,
    )
    return container_private_key


def decrypt_symmetric_key(container: dict, key_type: str) -> bytes:  # FIXME - why reinvent this container subsystem?
    """
    Permits to decrypt the private symmetric key

    :param container: container returned by encrypt_symmetric_key
    :param key_type: algorithm which has created key pair

    :return: private key as *key_type* key object
    """
    bytes_private_key = decrypt_data_from_container(
        container=container, local_key_storage=filesystem_key_storage
    )
    deciphered_private_key = load_asymmetric_key_from_pem_bytestring(
        bytes_private_key, key_type=key_type
    )
    return deciphered_private_key
