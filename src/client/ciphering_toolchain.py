from wacryptolib.encryption import encrypt_bytestring
from wacryptolib.container import encrypt_data_into_container, decrypt_data_from_container


def encrypt_video_stream(
    path: str, conf: dict, keychain_uid=None, metadata=None
) -> dict:
    """
    Put the video stream data saved in an .avi files into a container

    :param path: str with relative path to .avi video stream file
    :param conf: dictionary with entire configuration tree
    :param keychain_uid: uuid for the set of encryption keys used
    :param metadata: additional data to store unencrypted in container

    :return: dictionary which contains every information to decrypt container
    """
    with open(path, "rb") as video_stream:
        data = video_stream.read()

    assert isinstance(data, bytes)
    cipherdict = encrypt_data_into_container(
        data=data, conf=conf, keychain_uid=keychain_uid, metadata=metadata
    )
    return cipherdict


def decrypt_video_stream(container: dict) -> bytes:
    """
    Decipher container where a video stream saved as an .avi file has been ciphered

    :param container: dictionary which contains every information to decrypt container, returned by encrypt_video_stream

    :return: initial data decrypted
    """
    initial_data = decrypt_data_from_container(container=container)
    return initial_data
