import random
from uuid0 import UUID

from wacryptolib.key_storage import KeyStorageBase
from wacryptolib.sensor import TarfileRecordsAggregator, SensorsManager
from waguilib.background_service import WaBackgroundService, osc

from pathlib import Path

import io
import os
import tarfile
from concurrent.futures.thread import ThreadPoolExecutor
from kivy.logger import Logger as logger

from waguilib.importable_settings import INTERNAL_KEYS_DIR, EXTERNAL_DATA_EXPORTS_DIR, INTERNAL_APP_ROOT
from wanvr.common import WanvrRuntimeSupportMixin
from wasensorlib.camera.rtsp_stream import RtspCameraSensor

'''
from waclient.common_config import (
    APP_CONFIG_FILE,
    INTERNAL_KEYS_DIR,
    EXTERNAL_DATA_EXPORTS_DIR,
    get_encryption_conf,
    IS_ANDROID, WIP_RECORDING_MARKER, CONTEXT)
    '''
from waguilib.logging.handlers import CallbackHandler, safe_catch_unhandled_exception
from wacryptolib.container import decrypt_data_from_container, load_container_from_filesystem, \
    AUTHENTICATION_DEVICE_ESCROW_MARKER, SHARED_SECRET_MARKER, LOCAL_ESCROW_MARKER


class WanvrBackgroundServer(WanvrRuntimeSupportMixin, WaBackgroundService):

    # CLASS VARIABLES #

    thread_pool_executor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="service_worker"  # SINGLE worker for now, to avoid concurrency
    )
    #default_app_config_name = INTERNAL_APP_ROOT / "wanvr_config.ini"  # Might no exist yet

    #app_config_file = INTERNAL_APP_ROOT / "wanvr_config.ini"  # Might no exist yet

    @safe_catch_unhandled_exception
    def _offloaded_attempt_container_decryption(self, container_filepath):  #FIXME move out of here
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
    def attempt_container_decryption(self, container_filepath: str):  #FIXME move out of here
        container_filepath = Path(container_filepath)
        return self._offload_task(self._offloaded_attempt_container_decryption, container_filepath=container_filepath)

    def _get_encryption_conf(self):
        """Return a wacryptolib-compatible encryption configuration"""
        shared_secret_threshold = self.get_shared_secret_threshold()
        selected_authentication_device_uids = self.load_selected_authentication_device_uids()
        return self._build_encryption_conf(
                shared_secret_threshold=shared_secret_threshold,
                selected_authentication_device_uids=selected_authentication_device_uids,
                filesystem_key_storage_pool=self.filesystem_key_storage_pool)

    @staticmethod
    def _build_encryption_conf(shared_secret_threshold: int,
                               selected_authentication_device_uids: list,
                               filesystem_key_storage_pool: KeyStorageBase):
        info_escrows = []
        for authentication_device_uid in selected_authentication_device_uids:
            key_storage = filesystem_key_storage_pool.get_imported_key_storage(key_storage_uid=authentication_device_uid) # Fixme rename key_storage_uid
            key_information_list = key_storage.list_keypair_identifiers()
            key = random.choice(key_information_list)

            share_escrow = AUTHENTICATION_DEVICE_ESCROW_MARKER.copy()
            share_escrow["authentication_device_uid"] = UUID(authentication_device_uid)

            info_escrows.append(
                dict(
                    share_encryption_algo=key["key_type"],
                    keychain_uid=key["keychain_uid"],
                    share_escrow=share_escrow,
                 )
            )
        shared_secret_encryption = [
                                      dict(
                                         key_encryption_algo=SHARED_SECRET_MARKER,
                                         key_shared_secret_threshold=shared_secret_threshold,
                                         key_shared_secret_escrows=info_escrows,
                                      )
                                   ]
        data_signatures = [
                              dict(
                                  message_prehash_algo="SHA256",
                                  signature_algo="DSA_DSS",
                                  signature_escrow=LOCAL_ESCROW_MARKER,
                                  keychain_uid=UUID("06c4ae77-abed-40d9-8adf-82c11261c8d6"),  # Arbitrary but FIXED!
                              )
                          ]
        data_encryption_strata = [
            dict(
                 data_encryption_algo="AES_CBC",
                 key_encryption_strata=shared_secret_encryption,
                 data_signatures=data_signatures)
        ]
        container_conf = dict(data_encryption_strata=data_encryption_strata)

        #print(">>>>> USING ENCRYPTION CONF")
        #import pprint ; pprint.pprint(container_conf)

        return container_conf


    def _build_recording_toolchain(self):

        #Was using rtsp://viewer:SomePwd8162@192.168.0.29:554/Streaming/Channels/101

        tarfile_aggregator = TarfileRecordsAggregator(
            container_storage=self.filesystem_container_storage,
            max_duration_s=30*60,  # FIXME  see get_conf_value()
        )

        ip_camera_url = self.get_ip_camera_url()  #FIXME normalize names

        rtsp_camera_sensor = RtspCameraSensor(
                interval_s=10*60,  # FIXME  see get_conf_value()
                tarfile_aggregator=tarfile_aggregator,
                video_stream_url=ip_camera_url)

        sensors_manager = SensorsManager(sensors=[rtsp_camera_sensor])

        toolchain = dict(
            sensors_manager=sensors_manager,
            data_aggregators=[],
            tarfile_aggregators=[tarfile_aggregator],
            container_storage=self.filesystem_container_storage,
            free_keys_generator_worker=None,  # For now
        )
        return toolchain



def main():
    logger.info("Service process launches")
    server = WanvrBackgroundServer()
    server.join()
    logger.info("Service process exits")
