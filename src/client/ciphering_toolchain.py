from wacryptolib.encryption import encrypt_bytestring
from wacryptolib.container import encrypt_data_into_container


def encrypt_video_stream(
    path: str, conf: dict, keychain_uid=None, metadata=None
) -> dict:
    with open(path, "rb") as video_stream:
        data = video_stream.read()

    assert isinstance(data, bytes)
    cipherdict = encrypt_data_into_container(
        data=data, conf=conf, keychain_uid=keychain_uid, metadata=metadata
    )
    return cipherdict
