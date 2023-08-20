
from kivy.resources import resource_find
import logging
from pathlib import Path
import functools

from kivy.clock import Clock

from wacomponents.application.recorder_gui import WaRecorderGui
from wacomponents.default_settings import IS_RASPBERRY_PI
from wacomponents.devices.epaper import EPAPER_TYPES
from wacomponents.devices.lcd import LCD_TYPES
from wacomponents.screens.base import WAScreenName
from wacomponents.widgets.navigation_drawer import NavigationDrawerItem
from wacomponents.i18n import tr
from wacomponents.locale import LOCALE_DIR as GUILIB_LOCALE_DIR  # DEFAULT LOCALE DIR
from warecorder.warecorder_common_runtime import WarecorderRuntimeSupportMixin

WARECORDER_PACKAGE_DIR = Path(__file__).resolve().parent

# FIXME rename this file as foreground_app

# TODO - add retro "ping" from toolchain when a new record is present

LOCALE_DIR = WARECORDER_PACKAGE_DIR / "locale"
tr.add_locale_dirs(LOCALE_DIR, GUILIB_LOCALE_DIR)

logger = logging.getLogger(__name__)


if False:  #  ACTIVATE TO DEBUG GUI
    from wacomponents.widgets.layout_components import activate_widget_debug_outline
    activate_widget_debug_outline()


class WardGuiApp(WarecorderRuntimeSupportMixin, WaRecorderGui):

    title_app_window = tr._("Witness Angel - Recorder")
    title_conf_panel = tr._("Recorder settings")

    kv_file = str(WARECORDER_PACKAGE_DIR / "warecorder_gui.kv")
    icon = resource_find("icons/witness_angel_logo_blue_32x32.png")

    app_logo_path = WARECORDER_PACKAGE_DIR.joinpath("warecorder_desktop_icon_512x512.png")  # E.g. for side menu
    fallback_preview_image_path = app_logo_path  # If no recording exists yet to be shown

    def log_output(self, msg, *args, **kwargs):  # FIXME restore this
        return  # DISABLED FOR NOW
        console_output = self.screen_manager.get_screen(
            WAScreenName.recorder_homepage
        ).ids.kivy_console.ids.console_output
        console_output.add_text(
            msg
        )

    def _update_preview_image(self, *args, **kwargs):
        # TODO we should only display image if RECENT ENOUGH!!!
        logger.debug("Updating preview image in GUI screen")
        main_page_ids = self.screen_manager.get_screen(
            WAScreenName.recorder_homepage
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
        result = self.screen_manager.get_screen(WAScreenName.foreign_keystore_management).selected_keystore_uids
        return result

    @selected_keystore_uids.setter
    def selected_keystore_uids(self, keystore_uids):
        self.screen_manager.get_screen(WAScreenName.foreign_keystore_management).selected_keystore_uids = keystore_uids

    @property
    def recording_button(self): # IMPORTANT, expected by generic Screens!
        if not self.root:
            return  # Early introspection
        return self.screen_manager.get_screen(WAScreenName.recorder_homepage).ids.recording_button

    def switch_to_screen(self, *args, screen_name):
        self.screen_manager.current = screen_name
        self.navigation_drawer.set_state("screen_name")

    def get_back_to_home_screen(self):
        self.switch_to_screen(screen_name=WAScreenName.recorder_homepage)

    # KIVY APP overrides

    def on_config_change(self, config, section, key, value):
        #print("CONFIG CHANGE", section, key, value)
        self._update_app_after_config_change()  # We brutally reload everything, for now

    def should_daemonize_service(self):
        """We let the background service continue when we close the GUI"""
        return True

    def on_start(self):
        super().on_start()

        if False:
            # Enable to display final logging config
            try:
                import logging_tree
                logging_tree.printout()
            except ImportError:
                pass  # Optional debug stuff

        # Inject dependencies of loading screens

        authdevice_store_screen = self.screen_manager.get_screen(WAScreenName.foreign_keystore_management)
        authdevice_store_screen.filesystem_keystore_pool = self.filesystem_keystore_pool

        cryptainer_decryption_screen = self.screen_manager.get_screen(WAScreenName.cryptainer_decryption_process)
        cryptainer_decryption_screen.filesystem_keystore_pool = self.filesystem_keystore_pool

        decryption_request_screen = self.screen_manager.get_screen(WAScreenName.claimant_revelation_request_creation_form)
        decryption_request_screen.filesystem_keystore_pool = self.filesystem_keystore_pool

        self.selected_keystore_uids = self._load_selected_keystore_uids()
        authdevice_store_screen.bind(on_selected_keyguardians_changed=self._handle_selected_authdevice_changed)

        self._update_app_after_config_change()  # Force advanced setup of Screens

        self._reset_app_menu()

        # FIXME AWAITING REPAIR
        Clock.schedule_interval(
            self._update_preview_image, 15  # FIXME repair this!
        )
        self._update_preview_image()  # Immediate call

        ##self.fps_monitor_start()  # FPS display for debugging, requires FpsMonitoring mixin

        # HACK SHORTCUT if needed
        #self.root.ids.screen_manager.current = WAScreenName.claimant_revelation_request_management

    def _update_app_after_config_change(self):
        super()._update_app_after_config_change()

        cryptainer_storage = self.get_cryptainer_storage_or_none()

        cryptainer_store_screen = self.screen_manager.get_screen(WAScreenName.cryptainer_storage_management)  # FIXME simplify
        cryptainer_store_screen.filesystem_cryptainer_storage = cryptainer_storage  # FIXME SIMPLIFY with App methods ???
        cryptainer_decryption_screen = self.screen_manager.get_screen(WAScreenName.cryptainer_decryption_process)  # FIXME simplify
        cryptainer_decryption_screen.filesystem_cryptainer_storage = cryptainer_storage

        remote_decryption_request_screen = self.screen_manager.get_screen(WAScreenName.claimant_revelation_request_creation_form)  # FIXME simplify
        remote_decryption_request_screen.filesystem_cryptainer_storage = cryptainer_storage
        #print(">>>>>_update_app_after_config_change", container_store_screen.filesystem_cryptainer_storage)

    def _reset_app_menu(self):
        self.navigation_drawer.ids.content_drawer.ids.md_list.clear_widgets()

        screen_options = {
            WAScreenName.recorder_homepage: ("home", tr._("Recorder")),
            WAScreenName.foreign_keystore_management: ("key", tr._("Key Guardians")),
            WAScreenName.cryptainer_storage_management: ("lock", tr._("Containers")),
        }
        for screen_name, (icon_name, screen_title) in screen_options.items():
            item_draw = NavigationDrawerItem(icon=icon_name, text=screen_title)
            item_draw.bind(on_release=functools.partial(self.switch_to_screen, screen_name=screen_name))
            self.navigation_drawer.ids.content_drawer.ids.md_list.add_widget(item_draw)

    # FIXME rename these "authdevice" functions
    def _handle_selected_authdevice_changed(self, event, keystore_uids, *args):
        """Save to config file so that the Service can access the new list"""
        self.config["keyguardian"]["selected_keyguardians"] = ",".join(keystore_uids)
        self.save_config()

    def on_language_change(self, lang_code):
        super().on_language_change(lang_code)
        self._reset_app_menu()

    def get_config_schema_data(self) -> list:
        config_schema = []

        config_schema += [
            {
                "type": "title",
                "title": tr._("Sensors")
            },
        ]

        if IS_RASPBERRY_PI:
            config_schema += [
                {
                    "key": "enable_local_camera",
                    "type": "bool",
                    "title": tr._("Local camera"),
                    "desc": tr._("Enable attached camera"),
                    "section": "sensor"
                },
                {
                    "key": "local_camera_rotation",
                    "type": "options",
                    "title": tr._("Local camera rotation"),
                    "desc": tr._("Rotation angle of camera (Picamera only)"),
                    "options": ["0", "90", "180", "270"],
                    "section": "sensor"
                },
                {
                    "key": "enable_local_microphone",
                    "type": "bool",
                    "title": tr._("Local microphone"),
                    "desc": tr._("Enable attached microphone"),
                    "section": "sensor"
                },
                {
                    "key": "compress_local_microphone_recording",
                    "type": "bool",
                    "title": tr._("Compress audio"),
                    "desc": tr._("Encode audio recording"),
                    "section": "sensor"
                },
                {
                    "key": "enable_local_camera_microphone_muxing",
                    "type": "bool",
                    "title": tr._("Mux recordings"),
                    "desc": tr._("Merge local video and audio (requires libcamera)"),
                    "section": "sensor"
                }
            ]

        config_schema += [
            {
                "key": "enable_ip_camera",
                "type": "bool",
                "title": tr._("IP camera"),
                "desc": tr._("Enable network camera"),
                "section": "sensor"
            },
            {
                "key": "ip_camera_url",
                "type": "string_truncated",
                "title": tr._("IP Camera URL"),
                "desc": tr._("RTSP stream address"),
                "section": "sensor"
            },
            {
                "key": "recording_duration_mn",
                "type": "numeric",
                "title": tr._("Media recording duration (mn)"),
                "desc": tr._("How long each audio/video clip must last"),
                "section": "sensor"
            },
            # ---
            {
                "type": "title",
                "title": tr._("Key guardians")
            },
            {
                "key": "keyguardian_threshold",
                "type": "numeric",
                "title": tr._("Key guardian threshold"),
                "desc": tr._("Count of key guardians required to decrypt data"),
                "section": "keyguardian"
            },
            # ---
            {
                "type": "title",
                "title": tr._("Storage")
            },
            {
                "key": "cryptainer_dir",
                "type": "string_truncated",
                "title": tr._("Container folder"),
                "desc": tr._("Folder to store containers (defaults to user profile)"),
                "section": "storage"
            },
            {
                "key": "max_cryptainer_age_day",
                "type": "numeric",
                "title": tr._("Max retention period (days)"),
                "desc": tr._("For how long to keep a container before deletion"),
                "section": "storage"
            },
        ]

        if IS_RASPBERRY_PI:
            config_schema += [
                {
                    "type": "title",
                    "title": tr._("Peripherals")
                },
                {
                    "key": "epaper_type",
                    "type": "options",
                    "title": tr._("E-paper type"),
                    "desc": tr._("Optional E-ink display"),
                    "options": [""] + EPAPER_TYPES,
                    "section": "peripheral"
                },
                {
                    "key": "lcd_type",
                    "type": "options",
                    "title": tr._("LCD type"),
                    "desc": tr._("Optional LCD display"),
                    "options": [""] + LCD_TYPES,
                    "section": "peripheral"
                },
                {
                    "key": "enable_screen_buttons",
                    "type": "bool",
                    "title": tr._("Screen buttons"),
                    "desc": tr._("Enable epaper/lcd screen buttons"),
                    "section": "peripheral"
                },
                {
                    "key": "enable_button_shim",
                    "type": "bool",
                    "title": tr._("5 buttons shim"),
                    "desc": tr._("Enable Pimoroni buttonshim device (requires e-paper too)"),
                    "section": "peripheral"
                },
            ]

        config_schema += [
            {
                "type": "title",
                "title": tr._("Network")
            },
            {
                "key": "wagateway_url",
                "type": "string_truncated",
                "title": tr._("Witness Angel Gateway URL"),
                "desc": tr._("Registry of key guardians"),
                "section": "network"
            },
            # ---
            {
                "type": "title",
                "title": tr._("Advanced")
            }
        ]

        if IS_RASPBERRY_PI:
            config_schema += [
                {
                    "key": "live_preview_interval_s",
                    "type": "numeric",
                    "title": tr._("Live preview interval"),
                    "desc": tr._("How many seconds between live previews of Picamera (0 to disable)"),
                    "section": "sensor"
                },
                {
                    "key": "libcameravid_video_parameters",
                    "type": "string_truncated",
                    "title": tr._("Libcameravid video params"),
                    "desc": tr._("Replace libcameravid video parameters"),
                    "section": "sensor"
                },
                {
                    "key": "libcameravid_audio_parameters",
                    "type": "string_truncated",
                    "title": tr._("Libcameravid audio params"),
                    "desc": tr._("Replace libcameravid audio parameters"),
                    "section": "sensor"
                },
                {
                    "key": "raspivid_parameters",
                    "type": "string_truncated",
                    "title": tr._("Raspivid params"),
                    "desc": tr._("Replace raspivid parameters"),
                    "section": "sensor"
                },
                {
                    "key": "picamera_parameters",
                    "type": "string_truncated",
                    "title": tr._("Picamera params"),
                    "desc": tr._("Json object to replace picamera parameters"),
                    "section": "sensor"
                },
                {
                    "key": "arecord_parameters",
                    "type": "string_truncated",
                    "title": tr._("Arecord params"),
                    "desc": tr._("Replace arecord parameters"),
                    "section": "sensor"
                },
                {
                    "key": "arecord_output_format",
                    "type": "string_truncated",
                    "title": tr._("Arecord format"),
                    "desc": tr._("Replace arecord output format (default: wav)"),
                    "section": "sensor"
                },
                {
                    "key": "ffmpeg_alsa_parameters",
                    "type": "string_truncated",
                    "title": tr._("Ffmpeg alsa params"),
                    "desc": tr._("Replace ffmpeg alsa parameters"),
                    "section": "sensor"
                },
                {
                    "key": "ffmpeg_alsa_output_format",
                    "type": "string_truncated",
                    "title": tr._("Ffmpeg alsa format"),
                    "desc": tr._("Replace ffmpeg alsa output format (default: mp3)"),
                    "section": "sensor"
                },
            ]

        config_schema += [
            {
                "key": "ffmpeg_rtsp_parameters",
                "type": "string_truncated",
                "title": tr._("FFmpeg rtsp params"),
                "desc": tr._("Replace ffmpeg rtsp audio/video parameters"),
                "section": "sensor"
            },
            {
                "key": "ffmpeg_rtsp_output_format",
                "type": "string_truncated",
                "title": tr._("Ffmpeg rtsp format"),
                "desc": tr._("Replace ffmpeg rtsp output format (default: mp4)"),
                "section": "sensor"
            },
        ]

        return config_schema


def main():
    WardGuiApp().run()
