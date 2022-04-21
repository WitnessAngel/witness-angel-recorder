
from kivy.resources import resource_find
import logging
from pathlib import Path
import functools

from kivy.clock import Clock

from wacomponents.application.recorder_gui import WaRecorderGui
from wacomponents.widgets.navigation_drawer import NavigationDrawerItem
from wacomponents.i18n import tr
from wacomponents.locale import LOCALE_DIR as GUILIB_LOCALE_DIR  # DEFAULT LOCALE DIR
from wanvr.common_runtime import WanvrRuntimeSupportMixin

WANVR_PACKAGE_DIR = Path(__file__).resolve().parent

# FIXME rename this file as foreground_app

# TODO - add retro "ping" from toolchain when a new record is present

LOCALE_DIR = WANVR_PACKAGE_DIR / "locale"
tr.add_locale_dirs(LOCALE_DIR, GUILIB_LOCALE_DIR)

logger = logging.getLogger(__name__)


if False:  #  ACTIVATE TO DEBUG GUI
    from wacomponents.widgets.layout_components import activate_widget_debug_outline
    activate_widget_debug_outline()


class WardGuiApp(WanvrRuntimeSupportMixin, WaRecorderGui):  # FIXME rename this to WANVR

    title_app_window = tr._("Witness Angel - Network Video Recorder")
    title_conf_panel = tr._("Recorder settings")

    kv_file = str(WANVR_PACKAGE_DIR / "wanvr_gui.kv")
    icon = resource_find("icons/witness_angel_logo_blue_32x32.png")

    app_logo_path = WANVR_PACKAGE_DIR.joinpath("desktop_icon_authenticator_512x512.png")  # E.g. for side menu
    fallback_preview_image_path = app_logo_path  # If no recording exists yet to be shown

    def log_output(self, msg, *args, **kwargs):  # FIXME restore this
        return  # DISABLED FOR NOW
        console_output = self.screen_manager.get_screen(
            "MainPage"
        ).ids.kivy_console.ids.console_output
        console_output.add_text(
            msg
        )

    def _update_preview_image(self, *args, **kwargs):
        # FIXME we must only display image if RECENT ENOUGH!!!
        print(">> We update_preview_image")
        main_page_ids = self.screen_manager.get_screen(
            "MainPage"
        ).ids
        preview_image_widget = main_page_ids.preview_image

        if self.preview_image_path.exists():
            preview_image_widget.source = str(self.preview_image_path)
        else:
            preview_image_widget.source = str(self.fallback_preview_image_path)
        preview_image_widget.reload()  # Necessary to update texture

    # GUI WIDGETS AND PROPERTIES SHORTCUTS #

    @property
    def screen_manager(self):
        if not self.root:
            return  # Early introspection
        return self.root.ids.screen_manager

    @property
    def navigation_drawer(self):
        if not self.root:
            return  # Early introspection
        return self.root.ids.navigation_drawer

    @property
    def selected_keystore_uids(self):
        """Beware, here we lookup not the config file but the in-GUI data!"""
        if not self.root:
            return  # Early introspection
        result = self.screen_manager.get_screen("KeyManagement").selected_keystore_uids
        return result

    @selected_keystore_uids.setter
    def selected_keystore_uids(self, keystore_uids):
        self.screen_manager.get_screen("KeyManagement").selected_keystore_uids = keystore_uids

    @property
    def recording_button(self): # IMPORTANT, expected by generic Screens!
        if not self.root:
            return  # Early introspection
        return self.screen_manager.get_screen("MainPage").ids.recording_button

    def switch_to_screen(self, *args, screen_name):
        self.screen_manager.current = screen_name
        self.navigation_drawer.set_state("screen_name")

    def get_back_to_home_screen(self):
        self.switch_to_screen(screen_name="MainPage")

    # KIVY APP overrides

    def on_config_change(self, config, section, key, value):
        #print("CONFIG CHANGE", section, key, value)
        self._update_app_after_config_change()  # We brutally reload everything, for now

    def get_daemonize_service(self):
        """We let the background service continue when we close the GUI"""
        return True

    def on_start(self):
        super().on_start()

        if False:
            try:
                import logging_tree
                logging_tree.printout()
            except ImportError:
                pass  # Optional debug stuff

        # Inject dependencies of loading screens

        authdevice_store_screen = self.screen_manager.get_screen("KeyManagement")
        authdevice_store_screen.filesystem_keystore_pool = self.filesystem_keystore_pool

        cryptainer_decryption_screen = self.screen_manager.get_screen("CryptainerDecryption")
        cryptainer_decryption_screen.filesystem_keystore_pool = self.filesystem_keystore_pool

        self.selected_keystore_uids = self._load_selected_keystore_uids()
        authdevice_store_screen.bind(on_selected_keyguardians_changed=self._handle_selected_authdevice_changed)

        self._update_app_after_config_change()

        self._insert_app_menu()

        # FIXME AWAITING REPAIR
        Clock.schedule_interval(
            self._update_preview_image, 30  # FIXME repair this!
        )
        self._update_preview_image()  # Immediate call

        ##self.fps_monitor_start()  # FPS display for debugging, requires FpsMonitoring mixin

    def _update_app_after_config_change(self):
        super()._update_app_after_config_change()
        cryptainer_store_screen = self.screen_manager.get_screen("CryptainerManagement")  # FIXME simplify
        cryptainer_store_screen.filesystem_cryptainer_storage = self.get_cryptainer_storage_or_none()  # FIXME SIMPLIFY with App methods ???
        cryptainer_decryption_screen = self.screen_manager.get_screen("CryptainerDecryption")  # FIXME simplify
        cryptainer_decryption_screen.filesystem_cryptainer_storage = self.get_cryptainer_storage_or_none()

        remote_decryption_request_screen = self.screen_manager.get_screen("DecryptionRequestForm")  # FIXME simplify
        remote_decryption_request_screen.filesystem_cryptainer_storage = self.get_cryptainer_storage_or_none()
        #print(">>>>>_update_app_after_config_change", container_store_screen.filesystem_cryptainer_storage)

    def _insert_app_menu(self):
        screen_options = {
            "MainPage": ("home", tr._("Recorder")),
            "KeyManagement": ("key", tr._("Key Guardians")),
            "CryptainerManagement": ("lock", tr._("Video Containers")),
        }
        for screen_name, (icon_name, screen_title) in screen_options.items():
            item_draw = NavigationDrawerItem(icon=icon_name, text=screen_title)
            item_draw.bind(on_release=functools.partial(self.switch_to_screen, screen_name=screen_name))
            self.navigation_drawer.ids.content_drawer.ids.md_list.add_widget(item_draw)

    # FIXME rename these "authdevice" functions
    def _handle_selected_authdevice_changed(self, event, keystore_uids, *args):
        """Save to config file so that the Service can access the new list"""
        self.config["nvr"]["selected_keystore_uids"] = ",".join(keystore_uids)
        self.save_config()

    def get_config_schema_data(self) -> list:
        return [
            {
                "key": "ip_camera_url",
                "type": "string_truncated",
                "title": tr._("IP Camera URL"),
                "desc": tr._("URL to the RTSP stream"),
                "section": "nvr"
            },
            {
                "key": "keyguardian_threshold",
                "type": "numeric",
                "title": tr._("Key guardian threshold"),
                "desc": tr._("Count of key guardians required to decrypt data"),
                "section": "nvr"
            },
            {
                "key": "cryptainer_dir",
                "type": "string_truncated",
                "title": tr._("Containers folder"),
                "desc": tr._("Folder to store containers (defaults to user profile)"),
                "section": "nvr"
            },
            {
                "key": "max_cryptainer_age_day",
                "type": "numeric",
                "title": tr._("Max retention period (days)"),
                "desc": tr._("For how long to keep a container before deletion"),
                "section": "nvr"
            },
            {
                "key": "video_recording_duration_mn",
                "type": "numeric",
                "title": tr._("Video recording duration (mn)"),
                "desc": tr._("How long each video clip must last"),
                "section": "nvr"
            },
            {
                "key": "wagateway_url",
                "type": "string_truncated",
                "title": tr._("Witness Angel Gateway URL"),
                "desc": tr._("Registry of key guardians"),
                "section": "nvr"
            }
        ]

def main():
    WardGuiApp().run()
