from kivy.properties import StringProperty
from kivy.resources import resource_find

from waguilib import kivy_presetup  # Trigger common kivy setup
from waguilib.widgets.popups import display_info_toast

del kivy_presetup

import logging
from pathlib import Path
import functools

from kivy.clock import Clock
from kivymd.uix.snackbar import Snackbar

from waguilib.application import WAGuiApp
from waguilib.widgets.navigation_drawer import ItemDrawer
from waguilib.i18n import tr
from waguilib.locale import LOCALE_DIR as GUILIB_LOCALE_DIR  # DEFAULT LOCALE DIR
from wanvr.common import WanvrRuntimeSupportMixin

WANVR_PACKAGE_DIR = Path(__file__).resolve().parent

# FIXME rename this file as foreground_app

# TODO - add retro "ping" from toolchain when a new record is present

LOCALE_DIR = WANVR_PACKAGE_DIR / "locale"
tr.add_locale_dirs(LOCALE_DIR, GUILIB_LOCALE_DIR)

logger = logging.getLogger(__name__)


if False:  #  ACTIVATE TO DEBUG GUI
    from waguilib.widgets.layout_helpers import activate_widget_debug_outline
    activate_widget_debug_outline()


class WardGuiApp(WanvrRuntimeSupportMixin, WAGuiApp):  # FIXME rename this

    title = tr._("Witness Angel - Network Video Recorder")
    title_conf_panel = tr._("Recorder settings")

    icon = resource_find("icons/witness_angel_logo_blue_32x32.png")

    app_logo_path = WANVR_PACKAGE_DIR.joinpath("logo-wa.png")
    fallback_preview_image_path = app_logo_path  # If no recording exists yet to be shown

    def build(self):  # FIXME deduplicate!!!
        self.theme_cls.primary_palette = "Blue"
        #self.theme_cls.theme_style = "Dark"  # or "Light"
        self.theme_cls.primary_hue = "900"  # "500"

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

        try:
            import logging_tree
            logging_tree.printout()
        except ImportError:
            pass  # Optional debug stuff

        # Inject dependencies of loading screens

        authdevice_store_screen = self.screen_manager.get_screen("KeyManagement")
        authdevice_store_screen.filesystem_keystore_pool = self.filesystem_keystore_pool

        self.selected_keystore_uids = self._load_selected_keystore_uids()
        authdevice_store_screen.bind(on_selected_authdevices_changed=self._handle_selected_authdevice_changed)

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
        cryptainer_store_screen.filesystem_cryptainer_storage = self.get_readonly_cryptainer_storage_or_none()
        #print(">>>>>_update_app_after_config_change", container_store_screen.filesystem_cryptainer_storage)

    def _insert_app_menu(self):
        screen_options = {
            "MainPage": ("home", tr._("Main Page")),
            "KeyManagement": ("key", tr._("Key Management")),
            "CryptainerManagement": ("lock", tr._("Container Management")),
        }
        for screen_name, (icon_name, screen_title) in screen_options.items():
            item_draw = ItemDrawer(icon=icon_name, text=screen_title)
            item_draw.bind(on_release=functools.partial(self.switch_to_screen, screen_name=screen_name))
            self.navigation_drawer.ids.content_drawer.ids.md_list.add_widget(item_draw)

    # FIXME rename these "authdevice" functions
    def _handle_selected_authdevice_changed(self, event, keystore_uids, *args):
        """Save to config file so that the Service can access the new list"""
        self.config["nvr"]["selected_keystore_uids"] = ",".join(keystore_uids)
        self.save_config()


def main():
    WardGuiApp().run()
