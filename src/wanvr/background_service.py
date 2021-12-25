from waguilib import kivy_presetup  # Trigger common kivy setup
del kivy_presetup

import os.path
from concurrent.futures.thread import ThreadPoolExecutor

import random
import time
from kivy.logger import Logger as logger
from uuid0 import UUID
from datetime import timedelta, datetime, timezone

from wacryptolib.container import AUTHENTICATION_DEVICE_ESCROW_MARKER, SHARED_SECRET_MARKER, LOCAL_ESCROW_MARKER, \
    ContainerStorage
from wacryptolib.key_storage import KeyStorageBase
from wacryptolib.sensor import TarfileRecordsAggregator, SensorsManager
from wacryptolib.utilities import synchronized
from waguilib.background_service import WaBackgroundService
from waguilib.importable_settings import INTERNAL_CACHE_DIR
from waguilib.logging.handlers import safe_catch_unhandled_exception
from waguilib.utilities import get_system_information, convert_bytes_to_human_representation
from waguilib.i18n import tr
try:
    from waguilib.gpio_buttons import register_button_callback
except ImportError:
    register_button_callback = lambda *args, **kwargs: None
from wanvr.common import WanvrRuntimeSupportMixin
from wasensorlib.camera.rtsp_stream import RtspCameraSensor


# FIXME move this to wacryptolib
class PassthroughTarfileRecordsAggregator(TarfileRecordsAggregator):  #FIXME WRONG NAME

    @synchronized
    def add_record(self, sensor_name: str, from_datetime, to_datetime, extension: str, data: bytes):

        filename = self._build_record_filename(
            sensor_name=sensor_name, from_datetime=from_datetime, to_datetime=to_datetime, extension=extension
        )
        self._container_storage.enqueue_file_for_encryption(
            filename_base=filename, data=data, metadata={}
        )

    @synchronized
    def finalize_tarfile(self):
        pass  # DO NOTHING



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
        logger.info("Setting up epaper screen and refresh/on-off buttons")
        self._epaper_display = EpaperStatusDisplay()
        register_button_callback(self._epaper_display.BUTTON_PIN_1, self._epaper_status_refresh_callback)
        register_button_callback(self._epaper_display.BUTTON_PIN_2, self._epaper_switch_recording_callback)

    def _retrieve_epaper_display_information(self):

        status_obj = get_system_information(self.get_containers_dir())

        containers_count_str = last_container_str = preview_image_age_s =  tr._("N/A")

        readonly_container_storage: ContainerStorage = self.get_readonly_container_storage_or_none()

        if readonly_container_storage:
            container_names = readonly_container_storage.list_container_names(as_sorted=True)
            containers_count_str = str(len(container_names))
            if container_names:
                _last_container_name = container_names[-1]  # We consider that their names contain proper timestamps
                _last_container_size_str = convert_bytes_to_human_representation(readonly_container_storage._get_container_size(_last_container_name))
                _utcnow = datetime.utcnow().replace(tzinfo=timezone.utc)
                _last_container_age_s = "%ds" % (_utcnow - readonly_container_storage._get_container_datetime(_last_container_name)).total_seconds()
                last_container_str = "%s (%s)" % (_last_container_age_s, _last_container_size_str)

        try:
            preview_image_age_s = "%ss" % int(time.time() - os.path.getmtime(self.preview_image_path))
        except FileNotFoundError:
            pass

        status_obj.update({
            "recording_status": "ON" if self.is_recording else "OFF",
            "container_count": containers_count_str,
            "last_container": last_container_str,
            "last_thumbnail": preview_image_age_s
        })
        return status_obj

    @safe_catch_unhandled_exception
    def _epaper_status_refresh_callback(self, *args, **kwargs):  # Might receive pin number and such as arguments

        logger.info("Epaper status refresh callback was triggered")
        epaper_display = self._epaper_display
        assert epaper_display, epaper_display
        epaper_display.initialize_display()

        status_obj = self._retrieve_epaper_display_information()

        epaper_display.display_status(status_obj, preview_image_path=str(self.preview_image_path))
        epaper_display.release_display()

    def _epaper_switch_recording_callback(self, *args, **kwargs):  # Might receive pin number and such as arguments
        logger.info("Epaper recording switch callback  was triggered")
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()


    def _get_encryption_conf(self):
        """Return a wacryptolib-compatible encryption configuration"""
        shared_secret_threshold = self.get_shared_secret_threshold()
        selected_authentication_device_uids = self._load_selected_authentication_device_uids()
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
                dict(key_encryption_strata=[dict(
                    key_encryption_algo=key["key_type"],
                    keychain_uid=key["keychain_uid"],
                    key_escrow=share_escrow,
                 )])
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
                                  message_digest_algo="SHA256",
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

        containers_dir = self.get_containers_dir()  # Might raise
        if not containers_dir.is_dir():
            raise RuntimeError(f"Invalid containers dir setting: {containers_dir}")

        #print(">>>>>>>>>>>>>>ENCRYPTION TO", containers_dir, "with max age", self.get_max_container_age_day())

        container_storage = ContainerStorage(  # FIXME deduplicate paramaters with default (readonly) ContainerStorage
                       default_encryption_conf=self._get_encryption_conf(),
                       containers_dir=containers_dir,
                       key_storage_pool=self.filesystem_key_storage_pool,
                       max_workers=1, # Protect memory usage
                       max_container_age=timedelta(days=self.get_max_container_age_day()))

        assert container_storage is not None, container_storage

        ip_camera_url = self.get_ip_camera_url()  #FIXME normalize names

        rtsp_camera_sensor = RtspCameraSensor(
                interval_s=self.get_video_recording_duration_mn()*60,
                container_storage=container_storage,
                video_stream_url=ip_camera_url,
                preview_image_path=self.preview_image_path)

        sensors_manager = SensorsManager(sensors=[rtsp_camera_sensor])
 
        toolchain = dict(
            sensors_manager=sensors_manager,
            data_aggregators=[],
            tarfile_aggregators=[],
            container_storage=container_storage,
            free_keys_generator_worker=None,  # For now
        )
        return toolchain


def main():
    logger.info("Service process launches")
    server = WanvrBackgroundServer()
    server.join()
    logger.info("Service process exits")
