from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging
import time
import os
import threading
from concurrent.futures.thread import ThreadPoolExecutor

from wacryptolib.container import (
    encrypt_data_into_container,
    decrypt_data_from_container,
)
from wacryptolib.key_generation import (
    generate_asymmetric_keypair,
    load_asymmetric_key_from_pem_bytestring,
)
from wacryptolib.encryption import encrypt_bytestring, decrypt_bytestring
from wacryptolib.utilities import generate_uuid0

logger = logging.getLogger()
THREAD_POOL_EXECUTOR = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="recording_worker"
)


class NewVideoHandler(FileSystemEventHandler):
    def __init__(self, key_type, conf, key_length_bits=2048, metadata=None):
        self.files = []
        self.threads = []
        self._termination_event = threading.Event()
        self.key_type = key_type
        self.conf = conf
        self.key_length_bits = key_length_bits
        self.metadata = metadata

    def on_created(self, event):
        print("New video recording : {} ".format(event.src_path))
        self.start_encryption(path=event.src_path)

    def start_encryption(self, path):
        return self._offload_task(self._offloaded_start_encryption, path)
        # return THREAD_POOL_EXECUTOR.submit(self._offloaded_start_encryption, path)

    def _offloaded_start_encryption(self, path):
        if len(self.files) == 0:
            self.files.append(path)
        else:
            self.files.append(path)
            print(self.files[0])
            logger.debug("files: {}".format(self.files))
            print("Beginning encryption for {}".format(path))
            apply_entire_encryption_algorithm(
                self.key_type, self.conf, self.files[0], self.key_length_bits, self.metadata
            )
            del self.files[0]

    def _offload_task(self, method, *args, **kwargs):
        return THREAD_POOL_EXECUTOR.submit(method, *args, **kwargs)


def get_data_from_video(path: str) -> bytes:
    with open(path, 'rb') as file:
        data = file.read()
    os.remove(path=path)
    print("file {} has been deleted from system".format(path))
    return data


def apply_entire_encryption_algorithm(
        key_type: str, conf: dict, path: str, key_length_bits=None, metadata=None
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
    print("Getting assymetric keypair")
    keypair = get_assymetric_keypair(key_type=key_type, key_length_bits=key_length_bits)
    print("Ciphering data")
    ciphered_data = encrypt_video_stream(path=path, encryption_algo=key_type, keypair=keypair)

    keychain_uid = get_uuid0()
    print("Encrypting symmetric key")
    container_private_key = encrypt_symmetric_key(
        keypair=keypair, conf=conf, metadata=metadata, keychain_uid=keychain_uid
    )
    encryption_data = {"encryption_algo": key_type, "data": ciphered_data, "private_key": container_private_key}
    return encryption_data


def apply_entire_decryption_algorithm(encryption_data: dict) -> bytes:
    """
    Apply entire decryption algorithm, from ciphered data in dictionary to video file as bytes

    :param encryption_data: dictionary returned by apply_entire_encryption_algorithm

    :return: video file as bytes
    """
    deciphered_private_key = decrypt_symmetric_key(
        container=encryption_data["private_key"], key_type=encryption_data["encryption_algo"]
    )

    data = decrypt_video_stream(
        cipherdict=encryption_data["data"],
        encryption_algo=encryption_data["encryption_algo"],
        key=deciphered_private_key,
    )

    return data


def create_observer_thread(encryption_algo: str, conf: dict):
    """
    Create a thread where an observer check recursively a new file in the directory /ffmpeg_video_stream
    """
    observer = Observer()
    new_video_handler = NewVideoHandler(key_type=encryption_algo, conf=conf)
    observer.schedule(new_video_handler, path='ffmpeg_video_stream/', recursive=True)
    print("Observer started")
    observer.start()
    try:
        while True:
            time.sleep(.5)
    except:
        observer.stop()
        print("Observer Stopped")


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
    keypair = generate_asymmetric_keypair(key_type=key_type, serialize=False, key_length_bits=key_length_bits)
    return keypair


def encrypt_video_stream(path: str, encryption_algo: str, keypair: dict) -> dict:
    """
    Put the video stream data saved in an .avi files into a container

    :param key: assymetric keypair which must be used to encrypt/decrypt video stream
    :param encryption_algo: name of algorithm used to encrypt
    :param data: video files as bytes

    :return: dictionary which contains every information to decrypt container
    """
    data = get_data_from_video(path=path)

    cipherdict = encrypt_bytestring(
        plaintext=data, encryption_algo=encryption_algo, key=keypair["public_key"]
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


def encrypt_symmetric_key(keypair: dict, conf: dict, metadata: dict, keychain_uid) -> dict:
    """
    Permits to encrypt the private symmetric key.

    :param keypair: symmetric keypair
    :param conf: configuration tree
    :param metadata: optional metadata
    :param keychain_uid: optional ID of a keychain to reuse

    :return: dict of container
    """
    bytes_private_key = keypair["private_key"].export_key()

    container_private_key = encrypt_data_into_container(
        data=bytes_private_key, conf=conf, keychain_uid=keychain_uid, metadata=metadata
    )
    return container_private_key


def decrypt_symmetric_key(container: dict, key_type: str) -> bytes:
    """
    Permits to decrypt the private symmetric key

    :param container: container returned by encrypt_symmetric_key
    :param key_type: algorithm which has created key pair

    :return: private key as *key_type* key object
    """
    bytes_private_key = decrypt_data_from_container(container=container)
    deciphered_private_key = load_asymmetric_key_from_pem_bytestring(bytes_private_key, key_type=key_type)
    return deciphered_private_key
