from concurrent.futures.thread import ThreadPoolExecutor

import random
from kivy.logger import Logger as logger
from uuid0 import UUID

from wacryptolib.container import AUTHENTICATION_DEVICE_ESCROW_MARKER, SHARED_SECRET_MARKER, LOCAL_ESCROW_MARKER, \
    ContainerStorage
from wacryptolib.key_storage import KeyStorageBase
from wacryptolib.sensor import TarfileRecordsAggregator, SensorsManager
from waguilib.background_service import WaBackgroundService
from waguilib.importable_settings import INTERNAL_CACHE_DIR, INTERNAL_CONTAINERS_DIR
from waguilib.logging.handlers import safe_catch_unhandled_exception
from waguilib.utilities import get_system_information
from waguilib.gpio_buttons import register_button_callback
from wanvr.common import WanvrRuntimeSupportMixin
from wasensorlib.camera.rtsp_stream import RtspCameraSensor


PREVIEW_IMAGE_PATH = INTERNAL_CACHE_DIR / "video_preview_image.jpg"


class WanvrBackgroundServer(WanvrRuntimeSupportMixin, WaBackgroundService):

    # CLASS VARIABLES #
    thread_pool_executor = ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="service_worker"  # SINGLE worker for now, to avoid concurrency
    )

    _epaper_display = None  # Not always available

    def __init__(self):
        super().__init__()
        self._setup_epaper_screen()

    def _setup_epaper_screen(self):
        try:
            from waguilib.epaper import EpaperStatusDisplay
        except ImportError:
            logger.warning("Could not import EpaperStatusDisplay, aborting setup of epaper display")
            return
        logger.info("Setting up epaper screen and refresh button")
        self._epaper_display = EpaperStatusDisplay()
        register_button_callback(self._epaper_display.BUTTON_PIN_1, self._epaper_status_refresh_callback)

    @safe_catch_unhandled_exception
    def _epaper_status_refresh_callback(self, *args, **kwargs):  # Might receioved pin number and such as arguments
        epaper_display = self._epaper_display
        assert epaper_display, epaper_display
        epaper_display.initialize_display()
        status_obj = get_system_information(INTERNAL_CONTAINERS_DIR)

        containers_count = "Unknown"
        if self._recording_toolchain:
            containers_count = len(self._recording_toolchain["container_storage"])

        status_obj.update({
            "recording_status": "ON" if self.is_recording else "OFF",
            "containers": str(containers_count),
        })

        epaper_display.display_status(status_obj, preview_image_path=str(PREVIEW_IMAGE_PATH))
        epaper_display.release_display()

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

        container_storage = ContainerStorage(  # FIXME deduplicate paramateres with default (readonly) ContainerStorage
                       default_encryption_conf=self._get_encryption_conf(),
                       containers_dir=self.internal_containers_dir,
                       key_storage_pool=self.filesystem_key_storage_pool,
                       max_workers=1, # Protect memory usage
                       max_containers_count=12*24*1)  # 1 DAY OF DATA FOR NOW!!!

        assert container_storage is not None, container_storage
        tarfile_aggregator = TarfileRecordsAggregator(
            container_storage=container_storage,
            max_duration_s=5*60 - 10,  # FIXME  see get_conf_value()
        )

        ip_camera_url = self.get_ip_camera_url()  #FIXME normalize names

        rtsp_camera_sensor = RtspCameraSensor(
                interval_s=5*60,  # FIXME  see get_conf_value()
                tarfile_aggregator=tarfile_aggregator,
                video_stream_url=ip_camera_url,
                preview_image_path=PREVIEW_IMAGE_PATH)

        sensors_manager = SensorsManager(sensors=[rtsp_camera_sensor])

        toolchain = dict(
            sensors_manager=sensors_manager,
            data_aggregators=[],
            tarfile_aggregators=[tarfile_aggregator],
            container_storage=container_storage,
            free_keys_generator_worker=None,  # For now
        )
        return toolchain


def main():
    logger.info("Service process launches")
    server = WanvrBackgroundServer()
    server.join()
    logger.info("Service process exits")
