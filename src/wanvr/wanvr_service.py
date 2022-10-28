import logging
import os.path
from concurrent.futures.thread import ThreadPoolExecutor

import random
import time
from uuid import UUID
from datetime import timedelta, datetime, timezone

from wacomponents.default_settings import IS_RASPBERRY_PI
from wacomponents.devices.epaper import get_epaper_instance, EPAPER_TYPES
from wacomponents.sensors.camera.raspberrypi_camera_audio import RaspberryLibcameraSensor, \
    RaspberryAlsaMicrophoneSensor, list_pulseaudio_microphone_names
from wacryptolib.cryptainer import CRYPTAINER_TRUSTEE_TYPES, SHARED_SECRET_ALGO_MARKER, \
    CryptainerStorage, ReadonlyCryptainerStorage, check_cryptoconf_sanity
from wacryptolib.keystore import KeystoreBase
from wacryptolib.sensor import TarfileRecordAggregator, SensorManager
from wacryptolib.utilities import synchronized
from wacomponents.application.recorder_service import WaRecorderService
from wacomponents.logging.handlers import safe_catch_unhandled_exception
from wacomponents.utilities import get_system_information, convert_bytes_to_human_representation
from wacomponents.i18n import tr
try:
    from wacomponents.devices.gpio_buttons import register_button_callback
except ImportError:
    register_button_callback = lambda *args, **kwargs: None
from wanvr.common_runtime import WanvrRuntimeSupportMixin
from wacomponents.sensors.camera.rtsp_stream import RtspCameraSensor


logger = logging.getLogger(__name__)


class WanvrBackgroundServer(WanvrRuntimeSupportMixin, WaRecorderService):  # FIXME RENAME THIS

    _epaper_display = None  # Not always available

    def __init__(self):
        super().__init__()
        self._setup_epaper_screen()


    def _setup_epaper_screen(self):
        epaper_type = self.get_epaper_type()
        epaper_type = epaper_type.strip().lower()
        if not epaper_type:
            return  # No e-paper expected on this installation
        try:
            self._epaper_display = get_epaper_instance(epaper_type)
        except (ImportError, ValueError):
            logger.warning("Could not import display of type %r, aborting setup of e-paper screen" % epaper_type)
            return
        logger.info("Setting up epaper screen and refresh/on-off buttons")
        if self._epaper_display.BUTTON_PIN_1 is not None:
            register_button_callback(self._epaper_display.BUTTON_PIN_1, self._epaper_status_refresh_callback)
        if self._epaper_display.BUTTON_PIN_2 is not None:
            register_button_callback(self._epaper_display.BUTTON_PIN_2, self._epaper_switch_recording_callback)

    def _retrieve_epaper_display_information(self):

        status_obj = get_system_information(self.get_cryptainer_dir())

        cryptainers_count_str = last_cryptainer_str = preview_image_age_s =  tr._("N/A")

        readonly_cryptainer_storage: ReadonlyCryptainerStorage = self.get_cryptainer_storage_or_none(read_only=True)

        if readonly_cryptainer_storage:
            cryptainer_names = readonly_cryptainer_storage.list_cryptainer_names(as_sorted_list=True)
            cryptainers_count_str = str(len(cryptainer_names))
            if cryptainer_names:
                _last_cryptainer_name = cryptainer_names[-1]  # We consider that their names contain proper timestamps
                _last_cryptainer_size_str = convert_bytes_to_human_representation(readonly_cryptainer_storage._get_cryptainer_size(_last_cryptainer_name))
                _utcnow = datetime.utcnow().replace(tzinfo=timezone.utc)
                _last_cryptainer_age_s = "%ds" % (_utcnow - readonly_cryptainer_storage._get_cryptainer_datetime_utc(_last_cryptainer_name)).total_seconds()
                last_cryptainer_str = "%s  (%s)" % (_last_cryptainer_age_s, _last_cryptainer_size_str)

        try:
            preview_image_age_s = "%ss" % int(time.time() - os.path.getmtime(self.preview_image_path))
        except FileNotFoundError:
            pass

        status_obj.update({  # Maps will-be-labels to values
            "recording_status": "ON" if self.is_recording else "OFF",
            "container_count": cryptainers_count_str,
            "last_container": last_cryptainer_str,
            "last_thumbnail": preview_image_age_s
        })

        # Put fields in importance order
        sorted_field_names = [
            "recording_status", "wifi_status", "ethernet_status", "now_datetime",
            "last_thumbnail", "last_container", "container_count",
            "disk_left", "ram_left",
        ]
        assert len(sorted_field_names) == len(status_obj)
        status_obj_sorted = {
            field_name: status_obj[field_name]
            for field_name in sorted_field_names
        }
        #print("status_obj_sorted>>>>>", status_obj_sorted)
        return status_obj_sorted

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


    def _get_cryptoconf(self):
        """Return a wacryptolib-compatible encryption configuration"""
        keyguardian_threshold = self.get_keyguardian_threshold()
        selected_keystore_uids = self._load_selected_keystore_uids()
        return self._build_cryptoconf(
                keyguardian_threshold=keyguardian_threshold,
                selected_keystore_uids=selected_keystore_uids,
                filesystem_keystore_pool=self.filesystem_keystore_pool)

    @staticmethod
    def _build_cryptoconf(keyguardian_threshold: int,
                               selected_keystore_uids: list,
                               filesystem_keystore_pool: KeystoreBase):
        info_trustees = []

        all_foreign_keystore_metadata = filesystem_keystore_pool.get_all_foreign_keystore_metadata()

        for keystore_uid_str in selected_keystore_uids:
            keystore_uid = UUID(keystore_uid_str)
            keystore_owner = all_foreign_keystore_metadata[keystore_uid]["keystore_owner"]  # Shall exist
            keystore = filesystem_keystore_pool.get_foreign_keystore(keystore_uid=keystore_uid)
            key_information_list = keystore.list_keypair_identifiers()
            key = random.choice(key_information_list)  # IMPORTANT - randomly select a key

            shard_trustee = dict(
                trustee_type=CRYPTAINER_TRUSTEE_TYPES.AUTHENTICATOR_TRUSTEE,
                keystore_uid=keystore_uid,
                keystore_owner=keystore_owner,
            )

            info_trustees.append(
                dict(key_cipher_layers=[dict(
                    key_cipher_algo=key["key_algo"],
                    keychain_uid=key["keychain_uid"],
                    key_cipher_trustee=shard_trustee,
                 )])
            )
        shared_secret_encryption = [
                                      dict(
                                         key_cipher_algo=SHARED_SECRET_ALGO_MARKER,
                                         key_shared_secret_threshold=keyguardian_threshold,
                                         key_shared_secret_shards=info_trustees,
                                      )
                                   ]
        payload_signatures = []
        payload_cipher_layers = [
            dict(
                 payload_cipher_algo="AES_CBC",
                 key_cipher_layers=shared_secret_encryption,
                 payload_signatures=payload_signatures)
        ]
        cryptoconf = dict(payload_cipher_layers=payload_cipher_layers)
        check_cryptoconf_sanity(cryptoconf)  # Sanity check
        #print(">>>>> USING ENCRYPTION CONF")
        #import pprint ; pprint.pprint(cryptoconf)
        return cryptoconf

    def _build_recording_toolchain(self):

        #Was using rtsp://viewer:SomePwd8162@192.168.0.29:554/Streaming/Channels/101

        cryptainer_dir = self.get_cryptainer_dir()  # Might raise
        if not cryptainer_dir.is_dir():
            raise RuntimeError(f"Invalid containers dir setting: {cryptainer_dir}")

        #print(">>>>>>>>>>>>>>ENCRYPTION TO", containers_dir, "with max age", self.get_max_cryptainer_age_day())

        cryptainer_storage = CryptainerStorage(  # FIXME deduplicate paramaters with default (readonly) CryptainerStorage
                       default_cryptoconf=self._get_cryptoconf(),
                       cryptainer_dir=cryptainer_dir,
                       keystore_pool=self.filesystem_keystore_pool,
                       max_workers=1, # Protect memory usage
                       max_cryptainer_age=timedelta(days=self.get_max_cryptainer_age_day()))

        assert cryptainer_storage is not None, cryptainer_storage

        sensors = []
        recording_duration_s = self.get_video_recording_duration_mn()*60

        ip_camera_url = self.get_ip_camera_url()  #FIXME normalize names
        if ip_camera_url:
            rtsp_camera_sensor = RtspCameraSensor(
                interval_s=recording_duration_s,
                cryptainer_storage=cryptainer_storage,
                video_stream_url=ip_camera_url,
                preview_image_path=self.preview_image_path)
            sensors.append(rtsp_camera_sensor)

        if IS_RASPBERRY_PI:

            enable_local_camera = self.get_enable_local_camera()
            enable_local_microphone = self.get_enable_local_microphone()

            if enable_local_camera:
                # NO combined recording, too buggy for now on PI ZERO!
                alsa_device_name = None  ##list_pulseaudio_microphone_names()[0] if enable_local_microphone else None
                raspberry_libcamera_sensor = RaspberryLibcameraSensor(
                    interval_s=recording_duration_s,
                    cryptainer_storage=cryptainer_storage,
                    preview_image_path=self.preview_image_path,
                    alsa_device_name=alsa_device_name,
                )
                sensors.append(raspberry_libcamera_sensor)

            if enable_local_microphone:  # Separate audio recording
                alsa_microphone_sensor = RaspberryAlsaMicrophoneSensor(
                    interval_s=recording_duration_s,
                    cryptainer_storage=cryptainer_storage,
                )
                sensors.append(alsa_microphone_sensor)

        assert sensors, sensors  # Conf checkers should ensure this
        sensors_manager = SensorManager(sensors=sensors)

        toolchain = dict(
            sensors_manager=sensors_manager,
            data_aggregators=[],
            tarfile_aggregators=[],
            cryptainer_storage=cryptainer_storage,
            free_keys_generator_worker=None,  # For now, no pregeneration of local keys
        )
        return toolchain


def main():
    logger.info("Service process launches")
    server = WanvrBackgroundServer()
    server.join()
    logger.info("Service process exits")
