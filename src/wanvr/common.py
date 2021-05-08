from wacryptolib.key_storage import FilesystemKeyStoragePool
from waguilib.importable_settings import INTERNAL_KEYS_DIR


class NvrRuntimeSupportMixin:

    _config_file_basename = "wanvr_config.ini"

    # We use a class-level singleton here to simplify
    filesystem_key_storage_pool = FilesystemKeyStoragePool(
        root_dir=INTERNAL_KEYS_DIR
    )

    def get_shared_secret_threshold(self):
        return int(self.config.get("nvr", "shared_secret_threshold"))

    def get_selected_authentication_device_uids(self):
        return self.config["nvr"].get("selected_authentication_device_uids", "").split(",")

    def get_url_camera(self):
        return self.config.get("nvr", "ip_camera_url")

