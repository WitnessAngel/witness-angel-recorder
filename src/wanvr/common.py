import logging
from logging.handlers import RotatingFileHandler

import os
from uuid0 import UUID

from kivy.logger import Logger as logger
from wacryptolib.container import ContainerStorage
from wacryptolib.key_storage import FilesystemKeyStoragePool
from waguilib.importable_settings import INTERNAL_CACHE_DIR


class WanvrRuntimeSupportMixin:

    _config_file_basename = "wanvr_config.ini"

    preview_image_path = INTERNAL_CACHE_DIR / "preview_image.jpg"

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

    @property
    def readonly_container_storage(self):
        if not self.config:
            return  # Too early inspection

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

    def get_containers_dir(self):
        containers_dir = self.config.get("nvr", "containers_dir")  # Might be wrong!
        if not containers_dir or not os.path.exists(containers_dir):
            logger.warning("Containers directory not existing: %r - falling back to internal folder" % containers_dir)
            from waguilib.importable_settings import INTERNAL_CONTAINERS_DIR
            return INTERNAL_CONTAINERS_DIR
        return containers_dir

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



