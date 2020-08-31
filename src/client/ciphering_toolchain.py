from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path
import logging
import time
import os
import threading
from concurrent.futures.thread import ThreadPoolExecutor

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
THREAD_POOL_EXECUTOR = ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="recording_worker"
)

filesystem_key_storage = FilesystemKeyStorage(
    keys_dir="D:/Users/manon/Documents/GitHub/witness-ward-client/tests/keys"
)


class NewVideoHandler(FileSystemEventHandler):
    def __init__(self, key_type, conf, key_length_bits=2048, metadata=None):
        self.files = []
        self._termination_event = threading.Event()

        self.key_type = key_type
        self.conf = conf
        self.key_length_bits = key_length_bits
        self.metadata = metadata
        self.keychain_uid = None

    def on_created(self, event):
        logger.debug("New video recording : {} ".format(event.src_path))

    def on_modified(self, event):
        self.start_encryption(path=event.src_path)

    def start_encryption(self, path):
        return self._offload_task(self._offloaded_start_encryption, path)

    def _offloaded_start_encryption(self, path):
        key_pair = generate_asymmetric_keypair(key_type=self.key_type)
        keychain_uid = get_uuid0()
        logger.debug("UUID chiffrement : {}".format(keychain_uid))
        try:
            filesystem_key_storage.set_keys(
                keychain_uid=keychain_uid,
                key_type=self.key_type,
                public_key=key_pair["public_key"],
                private_key=key_pair["private_key"],
            )
        except Exception as ex:
            template = "An exception of type {0} occurred. Arguments:\n{1!r}"
            message = template.format(type(ex).__name__, ex.args)
            logger.debug(message)

        self.files.append(path)
        file = self.files[0]
        del self.files[0]
        logger.debug("Beginning encryption for {}".format(file))
        data = get_data_from_video(path=file)
        container = apply_entire_encryption_algorithm(
            key_type=self.key_type,
            conf=self.conf,
            data=data,
            key_length_bits=self.key_length_bits,
            metadata=self.metadata,
            keychain_uid=keychain_uid,
        )

        logger.debug("Saving container of {}".format(path))
        save_container(video_filepath=path, container=container)

    def _offload_task(self, method, *args, **kwargs):
        return THREAD_POOL_EXECUTOR.submit(method, *args, **kwargs)


def apply_entire_encryption_algorithm(
    key_type: str,
    conf: dict,
    data: bytes,
    keychain_uid,
    key_length_bits=None,
    metadata=None,
) -> dict:
    """
    Apply entire encryption algorithm, from video data file to dictionary which contains ciphered data and container to
    decipher private_key

    :param key_type: symmetric algorithm used to cipher video data
    :param conf: dictionary with configuration tree
    :param path: relative path to video file
    :param key_length_bits: size of returned key as bits
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


def apply_entire_decryption_algorithm(encryption_data: dict) -> bytes:
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
    container_filepath = Path("ciphered_video_stream/{}.crypt".format(file))
    logger.debug(container_filepath)
    dump_container_to_filesystem(
        container_filepath=container_filepath, container=container
    )


def get_container(container_filepath: str):
    container_filepath = Path(container_filepath)
    container = load_container_from_filesystem(container_filepath=container_filepath)
    return container


def get_data_from_video(path: str) -> bytes:
    with open(path, "rb") as file:
        data = file.read()
    os.remove(path=path)
    logger.debug("file {} has been deleted from system".format(path))
    return data


def create_observer_thread(encryption_algo: str, conf: dict):
    """
    Create a thread where an observer check recursively a new file in the directory /ffmpeg_video_stream
    """
    observer = Observer()
    new_video_handler = NewVideoHandler(key_type=encryption_algo, conf=conf)
    observer.schedule(new_video_handler, path="ffmpeg_video_stream/", recursive=True)
    logger.debug("Observer started")
    observer.start()
    try:
        while True:
            time.sleep(0.5)
    except:
        observer.stop()
        logger.debug("Observer Stopped")


def get_uuid0(ts=None):
    """
    Generate a random UUID according to current or given timestamp

    :param ts: optional timestamp to use instead of current time (if not falsey)

    :return: uuid0 object (subclass of UUID)
    """
    return generate_uuid0(ts=ts)


def get_assymetric_keypair(key_type: str, key_length_bits=2048) -> dict:
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


def encrypt_video_stream(data: bytes, encryption_algo: str, keychain_uid) -> dict:
    """
    Put the video stream data saved in an .avi files into a container

    :param key: assymetric keypair which must be used to encrypt/decrypt video stream
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


def decrypt_video_stream(cipherdict: dict, encryption_algo: str, key) -> bytes:
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


def encrypt_symmetric_key(
    conf: dict, encryption_algo: str, metadata: dict, keychain_uid
) -> dict:
    """
    Permits to encrypt the private symmetric key.

    :param keypair: symmetric keypair
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


def decrypt_symmetric_key(container: dict, key_type: str) -> bytes:
    """
    Permits to decrypt the private symmetric key

    :param container: container returned by encrypt_symmetric_key
    :param key_type: algorithm which has created key pair

    :return: private key as *key_type* key object
    """
    logger.debug("UUID déchiffrement : {}".format(container["keychain_uid"]))
    bytes_private_key = decrypt_data_from_container(
        container=container, local_key_storage=filesystem_key_storage
    )
    deciphered_private_key = load_asymmetric_key_from_pem_bytestring(
        bytes_private_key, key_type=key_type
    )
    return deciphered_private_key
