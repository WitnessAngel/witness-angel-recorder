import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import os
from uuid import UUID

from wacomponents.i18n import tr
from wacomponents.sensors.camera.raspberrypi_camera_audio import list_pulseaudio_microphone_names
from wacryptolib.cryptainer import CryptainerStorage, ReadonlyCryptainerStorage
from wacryptolib.keystore import FilesystemKeystorePool
from wacomponents.default_settings import INTERNAL_CACHE_DIR, IS_RASPBERRY_PI

logger = logging.getLogger(__name__)


class WanvrRuntimeSupportMixin:

    config_file_basename = "wanvr_config.ini"

    preview_image_path = INTERNAL_CACHE_DIR / "video_preview_image.jpg"

    # To be instantiated per-instance
    filesystem_keystore_pool = None

    def __init__(self, *args, **kwargs):

        assert self.internal_keys_dir, self.internal_keys_dir
        self.filesystem_keystore_pool = FilesystemKeystorePool(
            root_dir=self.internal_keys_dir
        )

        # FIXME move at a better place
        log_path = os.path.join(self.internal_logs_dir, "log.txt")
        handler = RotatingFileHandler(log_path, maxBytes=20 * (1024 ** 2), backupCount=100)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logging.root.addHandler(handler)
        logging.root.setLevel(logging.DEBUG)

        super().__init__(*args, **kwargs)  # ONLY NOW we call super class init

    def get_cryptainer_storage_or_none(self, read_only=False):
        if not self.config:
            return  # Too early inspection

        cryptainer_dir = self.get_cryptainer_dir()

        if not cryptainer_dir.is_dir():
            logger.warning("No valid containers dir configured for readonly visualization")
            return None

        klass = ReadonlyCryptainerStorage if read_only else CryptainerStorage
        return klass(cryptainer_dir=self.get_cryptainer_dir(), keystore_pool=self.filesystem_keystore_pool)

    def get_keyguardian_threshold(self):
        return int(self.config.get("nvr", "keyguardian_threshold"))

    def get_cryptainer_dir(self) -> Path:
        cryptainer_dir_str = self.config.get("nvr", "cryptainer_dir")  # Might be wrong!
        if not cryptainer_dir_str:
            logger.info("Containers directory not configured, falling back to internal folder")
            from wacomponents.default_settings import INTERNAL_CRYPTAINER_DIR
            return INTERNAL_CRYPTAINER_DIR
        return Path(cryptainer_dir_str)  # Might NOT exist!

    def _load_selected_keystore_uids(self):
        """This setting is loaded from config file, but then dynamically updated in GUI app"""

        # Beware these are STRINGS
        selected_keystore_uids = self.config.get("nvr", "selected_keystore_uids").split(",")

        available_keystore_uids = self.filesystem_keystore_pool.list_foreign_keystore_uids()

        # Check integrity of trustee selection
        selected_keystore_uids_filtered = [
            x for x in selected_keystore_uids
            if x and (UUID(x) in available_keystore_uids)
        ]
        #print("> Initial selected_keystore_uids", selected_keystore_uids)

        # TODO issue warning() if some uids were wrong!

        return selected_keystore_uids_filtered

    def get_ip_camera_url(self):
        return self.config.get("nvr", "ip_camera_url")

    def get_enable_local_camera(self):
        return self.config.getboolean("nvr", "enable_local_camera")

    def get_enable_local_microphone(self):
        return self.config.getboolean("nvr", "enable_local_microphone")

    def get_video_recording_duration_mn(self):
        return int(self.config.get("nvr", "video_recording_duration_mn"))

    def get_max_cryptainer_age_day(self):
        return int(self.config.get("nvr", "max_cryptainer_age_day"))

    def get_wagateway_url(self):
        return self.config.get("nvr", "wagateway_url")

    def get_epaper_type(self):
        return self.config.get("nvr", "epaper_type")

    def get_min_ffmpeg_version(self):
        return 4.3

    def check_all_raspberry_pi_sensors(self):
        enabled_sensor_titles = []

        enable_local_camera = self.get_enable_local_camera()
        #print(">>>>>>>>>>>enable_local_camera", enable_local_camera)
        if enable_local_camera:
            enabled_sensor_titles.append(tr._("local camera"))

        enable_local_microphone = self.get_enable_local_microphone()
        #print(">>>>>>>>>>>enable_local_microphone", enable_local_microphone)
        if enable_local_microphone:
            enabled_sensor_titles.append(tr._("local microphone"))
            microphone_names = list_pulseaudio_microphone_names()
            if not microphone_names:
                return False, tr._("Local microphone not found")

        ip_camera_url = self.get_ip_camera_url()
        if ip_camera_url:
            enabled_sensor_titles.append(tr._("IP camera %s") % ip_camera_url)
            ip_camera_res, ip_camera_msg = self.check_camera_url(ip_camera_url)
            if not ip_camera_res:
                return False, ip_camera_msg

        if not enabled_sensor_titles:
            return False, tr._("No sensors are enabled")

        return True, tr._("Sensors: %s") % (", ".join(enabled_sensor_titles))

    def _get_status_checkers(self):

        if IS_RASPBERRY_PI:
            specific_checkers = [self.check_all_raspberry_pi_sensors]
        else:
            specific_checkers = [lambda: self.check_camera_url(self.get_ip_camera_url())]

        return specific_checkers + [
            lambda: self.check_keyguardian_counts(
                    keyguardian_threshold=self.get_keyguardian_threshold(),
                    keyguardian_count=len(self._load_selected_keystore_uids())),
            lambda: self.check_cryptainer_output_dir(self.get_cryptainer_dir()),
            lambda: self.check_video_recording_duration_mn(self.get_video_recording_duration_mn()),
            lambda: self.check_max_cryptainer_age_day(self.get_max_cryptainer_age_day()),
            lambda: self.check_ffmpeg(self.get_min_ffmpeg_version()),
        ]
