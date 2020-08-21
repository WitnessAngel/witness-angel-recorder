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


def encrypt_video_stream(path: str, encryption_algo: str, key) -> dict:
    """
    Put the video stream data saved in an .avi files into a container

    :param key: assymetric key which must be used to encrypt video stream
    :param encryption_algo: name of algorithm used to encrypt
    :param path: str with relative path to .avi video stream file

    :return: dictionary which contains every information to decrypt container
    """
    with open(path, "rb") as video_stream:
        data = video_stream.read()

    cipherdict = encrypt_bytestring(
        plaintext=data, encryption_algo=encryption_algo, key=key
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


def encrypt_symmetric_key(private_symmetric_key, conf: dict, metadata: dict, keychain_uid) -> dict:
    """
    Permits to encrypt the private symmetric key.

    :param private_symmetric_key: private symmetric key
    :param conf: configuration tree
    :param metadata: optional metadata
    :param keychain_uid: optional ID of a keychain to reuse

    :return: dict of container
    """
    bytes_private_key = private_symmetric_key.export_key()

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
