import pytest
import random
import os
from pathlib import Path

from client.ciphering_toolchain import (
    create_observer_thread,
    apply_entire_encryption_algorithm,
    apply_entire_decryption_algorithm,
    get_data_from_video,
    save_container,
    get_container,
    get_uuid0,
    generate_asymmetric_keypair,
)

from wacryptolib.container import LOCAL_ESCROW_MARKER, SHARED_SECRET_MARKER
from wacryptolib.key_storage import FilesystemKeyStorage

SIMPLE_SHAMIR_CONTAINER_CONF = dict(
    data_encryption_strata=[
        dict(
            data_encryption_algo="AES_CBC",
            key_encryption_strata=[
                dict(key_encryption_algo="RSA_OAEP", key_escrow=LOCAL_ESCROW_MARKER),
                dict(
                    key_encryption_algo=SHARED_SECRET_MARKER,
                    key_shared_secret_threshold=3,
                    key_shared_secret_escrows=[
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_MARKER,
                        ),
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_MARKER,
                        ),
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_MARKER,
                        ),
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_MARKER,
                        ),
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_MARKER,
                        ),
                    ],
                ),
            ],
            data_signatures=[
                dict(
                    message_prehash_algo="SHA256",
                    signature_algo="DSA_DSS",
                    signature_escrow=LOCAL_ESCROW_MARKER,
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
                dict(key_encryption_algo="RSA_OAEP", key_escrow=LOCAL_ESCROW_MARKER)
            ],
            data_signatures=[],
        ),
        dict(
            data_encryption_algo="AES_CBC",
            key_encryption_strata=[
                dict(key_encryption_algo="RSA_OAEP", key_escrow=LOCAL_ESCROW_MARKER)
            ],
            data_signatures=[
                dict(
                    message_prehash_algo="SHA3_512",
                    signature_algo="DSA_DSS",
                    signature_escrow=LOCAL_ESCROW_MARKER,
                )
            ],
        ),
        dict(
            data_encryption_algo="CHACHA20_POLY1305",
            key_encryption_strata=[
                dict(
                    key_encryption_algo=SHARED_SECRET_MARKER,
                    key_shared_secret_threshold=2,
                    key_shared_secret_escrows=[
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_MARKER,
                        ),
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_MARKER,
                        ),
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_MARKER,
                        ),
                        dict(
                            share_encryption_algo="RSA_OAEP",
                            # shared_escrow=dict(url="http://example.com/jsonrpc"),
                            share_escrow=LOCAL_ESCROW_MARKER,
                        ),
                    ],
                )
            ],
            data_signatures=[
                dict(
                    message_prehash_algo="SHA3_256",
                    signature_algo="RSA_PSS",
                    signature_escrow=LOCAL_ESCROW_MARKER,
                ),
                dict(
                    message_prehash_algo="SHA512",
                    signature_algo="ECC_DSS",
                    signature_escrow=LOCAL_ESCROW_MARKER,
                ),
            ],
        ),
    ]
)


@pytest.mark.parametrize(
    "container_conf", [SIMPLE_SHAMIR_CONTAINER_CONF, COMPLEX_SHAMIR_CONTAINER_CONF]
)
def test_encrypt_video_stream(container_conf):
    video_files = os.listdir("ffmpeg_video_stream")
    path = f"ffmpeg_video_stream/{random.choice(video_files)}"

    encryption_algo = "RSA_OAEP"
    key_length_bits = random.choice([2048, 3072, 4096])
    metadata = random.choice([None, dict(a=[123])])
    data = get_data_from_video(path=path)

    filesystem_key_storage = FilesystemKeyStorage(keys_dir="keys/")
    key_pair = generate_asymmetric_keypair(key_type=encryption_algo)
    keychain_uid = get_uuid0()
    filesystem_key_storage.set_keys(
        keychain_uid=keychain_uid,
        key_type=encryption_algo,
        public_key=key_pair["public_key"],
        private_key=key_pair["private_key"],
    )

    encryption_data = apply_entire_encryption_algorithm(
        data=data,
        key_type=encryption_algo,
        conf=container_conf,
        key_length_bits=key_length_bits,
        metadata=metadata,
        keychain_uid=keychain_uid,
    )

    assert isinstance(encryption_data, dict)
    assert isinstance(encryption_data["private_key"], dict)
    assert isinstance(encryption_data["encryption_algo"], str)
    assert isinstance(encryption_data["data_ciphertext"], dict)

    save_container(video_filepath=path, container=encryption_data)

    filename, extension = os.path.splitext(path)
    dir_name, file = filename.split("/")
    container_filepath = Path("ciphered_video_stream/{}.crypt".format(file))
    assert os.path.exists(container_filepath)

    container = get_container(container_filepath=container_filepath)

    result_data = apply_entire_decryption_algorithm(encryption_data=container)

    assert isinstance(result_data, bytes)

    assert result_data == data


@pytest.mark.parametrize("container_conf", [SIMPLE_SHAMIR_CONTAINER_CONF])
def test_create_observer_thread(container_conf):
    video_files = os.listdir("ffmpeg_video_stream")
    for file in video_files:
        os.remove("ffmpeg_video_stream/{}".format(file))

    encryption_algo = "RSA_OAEP"
    create_observer_thread(encryption_algo=encryption_algo, conf=container_conf)


def test_decipher_container():
    video_files = os.listdir("ciphered_video_stream/")
    for file in video_files:
        if file.endswith(".crypt"):
            container = get_container(
                container_filepath=Path("ciphered_video_stream/{}".format(file))
            )
            apply_entire_decryption_algorithm(encryption_data=container)
