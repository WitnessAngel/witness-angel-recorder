from pathlib import Path

from waguilib.importable_settings import INTERNAL_APP_ROOT


WANVR_PACKAGE_DIR = Path(__file__).resolve().parent

WANVR_SRC_ROOT_DIR = WANVR_PACKAGE_DIR.parent

WANVR_CONFIG_TEMPLATE = WANVR_PACKAGE_DIR.joinpath("default_config_template.ini")

WANVR_CONFIG_SCHEMA = WANVR_PACKAGE_DIR.joinpath("user_settings_schema.json")

WANVR_CURRENT_CONFIG_FILE = INTERNAL_APP_ROOT / "waclient_config.ini"  # Might no exist yet
