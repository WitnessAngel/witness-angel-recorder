from wacryptolib.encryption import encrypt_bytestring
from wacryptolib.container import (
    encrypt_data_into_container,
    decrypt_data_from_container,
)
from wacryptolib.encryption import encrypt_bytestring, decrypt_bytestring


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
