import pytest
import random
from os import listdir

from client.ciphering_toolchain import create_observer_thread, get_uuid0, get_assymetric_keypair, \
    encrypt_video_stream, decrypt_video_stream, encrypt_symmetric_key, decrypt_symmetric_key

from wacryptolib.container import (
    LOCAL_ESCROW_PLACEHOLDER,
)

SIMPLE_SHAMIR_CONTAINER_CONF = dict(
    data_encryption_strata=[
        dict(
            data_encryption_algo="AES_CBC",
            key_encryption_strata=[
                dict(
                    key_encryption_algo="RSA_OAEP", key_escrow=LOCAL_ESCROW_PLACEHOLDER
                ),
                dict(
                    key_encryption_algo="SHARED_SECRET",
                    key_shared_secret_threshold=3,
                    key_shared_secret_escrows=[
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_PLACEHOLDER,
                        ),
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_PLACEHOLDER,
                        ),
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_PLACEHOLDER,
                        ),
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_PLACEHOLDER,
                        ),
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_PLACEHOLDER,
                        ),
                    ],
                ),
            ],
            data_signatures=[
                dict(
                    message_prehash_algo="SHA256",
                    signature_algo="DSA_DSS",
                    signature_escrow=LOCAL_ESCROW_PLACEHOLDER,
                )
            ],
        )
    ]
)

COMPLEX_SHAMIR_CONTAINER_CONF = dict(
    data_encryption_strata=[
        dict(
            data_encryption_algo="AES_EAX",
            key_encryption_strata=[
                dict(
                    key_encryption_algo="RSA_OAEP", key_escrow=LOCAL_ESCROW_PLACEHOLDER
                )
            ],
            data_signatures=[],
        ),
        dict(
            data_encryption_algo="AES_CBC",
            key_encryption_strata=[
                dict(
                    key_encryption_algo="RSA_OAEP", key_escrow=LOCAL_ESCROW_PLACEHOLDER
                )
            ],
            data_signatures=[
                dict(
                    message_prehash_algo="SHA3_512",
                    signature_algo="DSA_DSS",
                    signature_escrow=LOCAL_ESCROW_PLACEHOLDER,
                )
            ],
        ),
        dict(
            data_encryption_algo="CHACHA20_POLY1305",
            key_encryption_strata=[
                dict(
                    key_encryption_algo="SHARED_SECRET",
                    key_shared_secret_threshold=2,
                    key_shared_secret_escrows=[
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_PLACEHOLDER,
                        ),
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_PLACEHOLDER,
                        ),
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_PLACEHOLDER,
                        ),
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_PLACEHOLDER,
                        ),
                    ],
                ),
            ],
            data_signatures=[
                dict(
                    message_prehash_algo="SHA3_256",
                    signature_algo="RSA_PSS",
                    signature_escrow=LOCAL_ESCROW_PLACEHOLDER,
                ),
                dict(
                    message_prehash_algo="SHA512",
                    signature_algo="ECC_DSS",
                    signature_escrow=LOCAL_ESCROW_PLACEHOLDER,
                ),
            ],
        ),
    ]
)


@pytest.mark.parametrize(
    "container_conf", [SIMPLE_SHAMIR_CONTAINER_CONF, COMPLEX_SHAMIR_CONTAINER_CONF]
)
def test_encrypt_video_stream(container_conf):
    video_files = listdir("saved_video_stream")
    path = f"saved_video_stream/{random.choice(video_files)}"
    encryption_algo = "RSA_OAEP"
    key_length_bits = random.choice([2048, 3072, 4096])

    keypair = get_assymetric_keypair(
        key_type=encryption_algo, key_length_bits=key_length_bits
    )

    ciphered_data = encrypt_video_stream(
        path=path, encryption_algo=encryption_algo, keypair=keypair
    )

    assert isinstance(ciphered_data, dict)

    keychain_uid = get_uuid0()
    metadata = random.choice([None, dict(a=[123])])

    container_private_key = encrypt_symmetric_key(
        keypair=keypair,
        conf=container_conf,
        metadata=metadata,
        keychain_uid=keychain_uid,
    )

    assert isinstance(container_private_key, dict)

    deciphered_private_key = decrypt_symmetric_key(
        container=container_private_key, key_type=encryption_algo
    )

    assert deciphered_private_key == keypair["private_key"]

    result_data = decrypt_video_stream(
        cipherdict=ciphered_data,
        encryption_algo=encryption_algo,
        key=keypair["private_key"],
    )

    assert isinstance(result_data, bytes)
    with open(path, "rb") as video_stream:
        data = video_stream.read()

    assert result_data == data


def test_create_observer_thread():
    create_observer_thread()
