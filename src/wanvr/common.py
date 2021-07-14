import logging
from logging.handlers import RotatingFileHandler

import os
from uuid0 import UUID

from wacryptolib.container import ContainerStorage
from wacryptolib.key_storage import FilesystemKeyStoragePool
from waguilib.importable_settings import INTERNAL_CACHE_DIR


class WanvrRuntimeSupportMixin:

    _config_file_basename = "wanvr_config.ini"

    preview_image_path = INTERNAL_CACHE_DIR / "preview_image.jpg"

    # To be instantiated per-instance
    filesystem_key_storage_pool = None
    filesystem_container_storage = None

    def __init__(self, *args, **kwargs):

        assert self.internal_keys_dir, self.internal_keys_dir
        self.filesystem_key_storage_pool = FilesystemKeyStoragePool(
            root_dir=self.internal_keys_dir
        )

        # BEWARE - don't use this one for recording, only for container management (no encryption conf)
        self.filesystem_container_storage = ContainerStorage(
               default_encryption_conf=None,
               containers_dir=self.internal_containers_dir,
               key_storage_pool=self.filesystem_key_storage_pool,
               max_workers=1, # Protect memory usage
               max_containers_count=4*24*1)  # 1 DAY OF DATA FOR NOW!!!

        # FIXME move at a better place
        log_path = os.path.join(self.internal_logs_dir, "log.txt")
        logging.root.addHandler(RotatingFileHandler(log_path, maxBytes=10 * (1024 ** 2), backupCount=10))

        super().__init__(*args, **kwargs)  # ONLY NOW we call super class init


    def get_shared_secret_threshold(self):
        return int(self.config.get("nvr", "shared_secret_threshold"))

    def load_selected_authentication_device_uids(self):
        # Beware these are STRINGS
        selected_authentication_device_uids = self.config["nvr"].get("selected_authentication_device_uids", "").split(",")

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



