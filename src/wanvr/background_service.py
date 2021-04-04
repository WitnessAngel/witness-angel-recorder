
from waguilib.background_service import WaBackgroundService, osc

from pathlib import Path

import io
import os
import tarfile
from concurrent.futures.thread import ThreadPoolExecutor
from kivy.logger import Logger as logger

from waguilib.importable_settings import INTERNAL_KEYS_DIR, EXTERNAL_DATA_EXPORTS_DIR, INTERNAL_APP_ROOT

'''
from waclient.common_config import (
    APP_CONFIG_FILE,
    INTERNAL_KEYS_DIR,
    EXTERNAL_DATA_EXPORTS_DIR,
    get_encryption_conf,
    IS_ANDROID, WIP_RECORDING_MARKER, CONTEXT)
    '''
from waguilib.logging.handlers import CallbackHandler, safe_catch_unhandled_exception
from wacryptolib.container import decrypt_data_from_container, load_container_from_filesystem



class WanvrBackgroundServer(WaBackgroundService):

    # CLASS VARIABLES #
    internal_keys_dir = INTERNAL_KEYS_DIR
    thread_pool_executor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="service_worker"  # SINGLE worker for now, to avoid concurrency
    )
    default_app_config_name = INTERNAL_APP_ROOT / "wanvr_config.ini"  # Might no exist yet

    app_config_file = INTERNAL_APP_ROOT / "wanvr_config.ini"  # Might no exist yet

    @safe_catch_unhandled_exception
    def _offloaded_attempt_container_decryption(self, container_filepath):
        logger.info("Decryption requested for container %s", container_filepath)
        target_directory = EXTERNAL_DATA_EXPORTS_DIR.joinpath(
            os.path.basename(container_filepath)
        )
        target_directory.mkdir(
            exist_ok=True
        )  # Double exports would replace colliding files
        container = load_container_from_filesystem(container_filepath, include_data_ciphertext=True)
        tarfile_bytes = decrypt_data_from_container(
            container, key_storage_pool=self._key_storage_pool
        )
        tarfile_bytesio = io.BytesIO(tarfile_bytes)
        tarfile_obj = tarfile.open(
            mode="r", fileobj=tarfile_bytesio  # TODO add gzip support here one day
        )
        # Beware, as root on unix systems it would apply chown/chmod
        tarfile_obj.extractall(target_directory)
        logger.info(
            "Container content was successfully decrypted into folder %s",
            target_directory,
        )

    @osc.address_method("/attempt_container_decryption")
    @safe_catch_unhandled_exception
    def attempt_container_decryption(self, container_filepath: str):
        container_filepath = Path(container_filepath)
        return self._offload_task(self._offloaded_attempt_container_decryption, container_filepath=container_filepath)


def main():
    logger.info("Service process launches")
    server = WanvrBackgroundServer()
    server.join()
    logger.info("Service process exits")
