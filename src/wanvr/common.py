import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import os
from uuid import UUID

from kivy.logger import Logger as logger
from wacryptolib.cryptainer import CryptainerStorage
from wacryptolib.keystore import FilesystemKeystorePool
from waguilib.importable_settings import INTERNAL_CACHE_DIR


class WanvrRuntimeSupportMixin:

    _config_file_basename = "wanvr_config.ini"

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
        handler = RotatingFileHandler(log_path, maxBytes=10 * (1024 ** 2), backupCount=50)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logging.root.addHandler(handler)
        logging.root.setLevel(logging.DEBUG)

        super().__init__(*args, **kwargs)  # ONLY NOW we call super class init

    def get_readonly_cryptainer_storage_or_none(self):
        if not self.config:
            return  # Too early inspection

        cryptainer_dir = self.get_cryptainer_dir()

        if not cryptainer_dir.is_dir():
            logger.warning("No valid containers dir configured for readonly visualization")
            return None

        # FIXME - use ReadonlYCryptainerStorage class when implemented in wacryptolib!
        # BEWARE - don't use this one for recording, only for container management (no encryption conf)
        readonly_cryptainer_storage = CryptainerStorage(
               default_cryptoconf=None,
               cryptainer_dir=self.get_cryptainer_dir(),
               keystore_pool=self.filesystem_keystore_pool,
               max_workers=1,) # Protect memory usage
        readonly_cryptainer_storage.enqueue_file_for_encryption = None  # HACK, we want it readonly!
        return readonly_cryptainer_storage

    def get_keyguardian_threshold(self):
        return int(self.config.get("nvr", "keyguardian_threshold"))

    def get_cryptainer_dir(self) -> Path:
        cryptainer_dir_str = self.config.get("nvr", "cryptainer_dir")  # Might be wrong!
        if not cryptainer_dir_str:
            logger.info("Containers directory not configured, falling back to internal folder")
            from waguilib.importable_settings import INTERNAL_CRYPTAINER_DIR
            return INTERNAL_CRYPTAINER_DIR
        return Path(cryptainer_dir_str)  # Might NOT exist!

    def _load_selected_authenticator_uids(self):
        """This setting is loaded from config file, but then dynamically updated in GUI app"""

        # Beware these are STRINGS
        selected_authenticator_uids = self.config.get("nvr", "selected_authenticator_uids").split(",")

        available_authenticator_uids = self.filesystem_keystore_pool.list_imported_keystore_uids()

        # Check integrity of trustee selection
        selected_authenticator_uids_filtered = [
            x for x in selected_authenticator_uids
            if x and (UUID(x) in available_authenticator_uids)
        ]
        #print("> Initial selected_authenticator_uids", selected_authenticator_uids)

        # TODO issue warning() if some uids were wrong!

        return selected_authenticator_uids_filtered

    def get_ip_camera_url(self):
        return self.config.get("nvr", "ip_camera_url")

    def get_video_recording_duration_mn(self):
        return int(self.config.get("nvr", "video_recording_duration_mn"))

    def get_max_cryptainer_age_day(self):
        return int(self.config.get("nvr", "max_cryptainer_age_day"))

    def _get_status_checkers(self):
        return [
            lambda: self.check_camera_url(self.get_ip_camera_url()),
            lambda: self.check_keyguardian_counts(
                    keyguardian_threshold=self.get_keyguardian_threshold(),
                    keyguardian_count=len(self._load_selected_authenticator_uids())),
            lambda: self.check_cryptainer_output_dir(self.get_cryptainer_dir()),
            lambda: self.check_video_recording_duration_mn(self.get_video_recording_duration_mn()),
            lambda: self.check_max_cryptainer_age_day(self.get_max_cryptainer_age_day()),
        ]

