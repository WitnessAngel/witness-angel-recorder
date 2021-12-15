import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import os
from uuid0 import UUID

from kivy.logger import Logger as logger
from wacryptolib.container import ContainerStorage
from wacryptolib.key_storage import FilesystemKeyStoragePool
from waguilib.importable_settings import INTERNAL_CACHE_DIR


class WanvrRuntimeSupportMixin:

    _config_file_basename = "wanvr_config.ini"

    preview_image_path = INTERNAL_CACHE_DIR / "video_preview_image.jpg"

    # To be instantiated per-instance
    filesystem_key_storage_pool = None

    def __init__(self, *args, **kwargs):

        assert self.internal_keys_dir, self.internal_keys_dir
        self.filesystem_key_storage_pool = FilesystemKeyStoragePool(
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

    def get_readonly_container_storage(self):
        if not self.config:
            return  # Too early inspection

        containers_dir = self.get_containers_dir()

        if not containers_dir.is_dir():
            logger.warning("No valid containers dir configured for readonly visualization")
            return None

        # FIXME - use ReadonlYContainerStorage class when implemented in wacryptolib!
        # BEWARE - don't use this one for recording, only for container management (no encryption conf)
        readonly_container_storage = ContainerStorage(
               default_encryption_conf=None,
               containers_dir=self.get_containers_dir(),
               key_storage_pool=self.filesystem_key_storage_pool,
               max_workers=1,) # Protect memory usage
        readonly_container_storage.enqueue_file_for_encryption = None  # HACK, we want it readonly!
        return readonly_container_storage

    def get_shared_secret_threshold(self):
        return int(self.config.get("nvr", "shared_secret_threshold"))

    def get_containers_dir(self) -> Path:
        containers_dir_str = self.config.get("nvr", "containers_dir")  # Might be wrong!
        if not containers_dir_str:
            logger.warning("Containers directory not configured, falling back to internal folder")
            from waguilib.importable_settings import INTERNAL_CONTAINERS_DIR
            return INTERNAL_CONTAINERS_DIR
        return Path(containers_dir_str)  # Might NOT exist!

    def _load_selected_authentication_device_uids(self):
        """This setting is loaded from config file, but then dynamically updated in GUI app"""

        # Beware these are STRINGS
        selected_authentication_device_uids = self.config.get("nvr", "selected_authentication_device_uids").split(",")

        available_authentication_device_uids = self.filesystem_key_storage_pool.list_imported_key_storage_uids()

        # Check integrity of escrow selection
        selected_authentication_device_uids_filtered = [
            x for x in selected_authentication_device_uids
            if x and (UUID(x) in available_authentication_device_uids)
        ]
        print("> Initial selected_authentication_device_uids", selected_authentication_device_uids)

        # TODO issue warning() if some uids were wrong!

        return selected_authentication_device_uids_filtered

    def get_ip_camera_url(self):
        return self.config.get("nvr", "ip_camera_url")

    def get_max_container_age_day(self):
        return int(self.config.get("nvr", "max_container_age_day"))

    def get_video_recording_duration_mn(self):
        return int(self.config.get("nvr", "video_recording_duration_mn"))

    def _get_status_checkers(self):
        return [
            lambda: self.check_camera_url(self.get_ip_camera_url()),
            lambda: self.check_keyguardian_counts(
                    keyguardian_threshold=self.get_shared_secret_threshold(),
                    keyguardian_count=len(self._load_selected_authentication_device_uids())),
            lambda: self.check_container_output_dir(self.get_containers_dir()),
        ]

