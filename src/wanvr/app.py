# Tweak logging before Kivy breaks it
import inspect

import os, sys, logging

from waguilib.widgets.navigation_drawer import ItemDrawer

'''
if sys.platform == "win32":
    os.environ["KIVY_GL_BACKEND"] = "angle_sdl2"

os.environ["KIVY_NO_CONSOLELOG"] = "1"
#ogging.root.setLevel(logging.DEBUG)
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("wacryptolib").setLevel(logging.DEBUG)
logging.getLogger("wanvr").setLevel(logging.DEBUG)
REAL_ROOT_LOGGER = logging.root
'''

import pprint
import random
from functools import partial
from pathlib import Path
from uuid import UUID
from logging.handlers import RotatingFileHandler
from waguilib.application import WAGuiApp

# SETUP INITIAL STATE OF THE WINDOW
from kivy.config import Config
Config.set('graphics', 'top', '50')
Config.set('graphics', 'left', '50')
Config.set('graphics', 'position', 'custom')
# FIXME this happens too late I guess
#Config.set("graphics", "fullscreen", "0")
#Config.set("graphics", "show_cursor", "1")

from kivy.core.window import Window

Window.minimum_width, Window.minimum_height = Window.size = (500, 380)

from kivy.clock import Clock
from kivy.config import Config
from kivy.properties import StringProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.screenmanager import ScreenManager
from kivy.uix.textinput import TextInput
from kivymd.uix.textfield import MDTextField
from kivymd.app import MDApp
from kivymd.theming import ThemableBehavior
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import OneLineIconListItem, MDList
from kivymd.uix.screen import Screen
from kivymd.uix.snackbar import Snackbar
from wanvr.rtsp_recorder.ciphering_toolchain import _generate_encryption_conf, RecordingToolchain, \
    filesystem_key_storage_pool, \
    filesystem_container_storage, rtsp_recordings_folder, preview_image_path, decrypted_records_folder, \
    DEFAULT_FILES_ROOT
from wacryptolib.container import (
    ContainerStorage,
    encrypt_data_into_container,
    gather_escrow_dependencies,
    load_container_from_filesystem,
    dump_container_to_filesystem,
)
from wacryptolib.authentication_device import list_available_authentication_devices, \
    _get_key_storage_folder_path
from wacryptolib.exceptions import KeyStorageAlreadyExists
from wacryptolib.utilities import generate_uuid0
from waguilib.logging.handlers import CallbackHandler, safe_catch_unhandled_exception

from waguilib.importable_settings import INTERNAL_APP_ROOT


from kivy.uix.settings import SettingsWithTabbedPanel


WANVR_PACKAGE_DIR = Path(__file__).resolve().parent


class MainWindow(Screen):
    pass
    """
    def __init__(self, **kwargs):
        self.title = "Witness Angel - WardProject"

        super(MainWindow, self).__init__(**kwargs)
    """

class WindowManager(ScreenManager):
    pass


# TODO - add retro "ping" from toolchain when a new record is present

class WardGuiApp(WAGuiApp):  # FIXME rename this

    title = "Witness Angel - NVR"
    _config_file_basename = "wanvr_config.ini"

    #app_config_file = INTERNAL_APP_ROOT / "wanvr_config.ini"  # Might no exist yet
    #default_config_template: str = WANVR_PACKAGE_DIR.joinpath("wardgui.ini")
    #default_config_schema: str = WANVR_PACKAGE_DIR.joinpath("user_settings_schema.json")
    #wip_recording_marker: str = None

    dialog = None  # Any current modal dialog must be stored here

    app_logo_path = WANVR_PACKAGE_DIR.joinpath("logo-wa.png")
    fallback_preview_image_path = app_logo_path

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        """
        self.CONFIG = dict(
            data_encryption_strata=[
                dict(
                    data_encryption_algo="AES_CBC",
                    key_encryption_strata=[
                        dict(
                            key_encryption_algo="RSA_OAEP",
                            key_escrow=LOCAL_ESCROW_MARKER,
                        )
                    ],
                    data_signatures=[
                        dict(
                            message_prehash_algo="SHA256",
                            signature_algo="DSA_DSS",
                            signature_escrow=LOCAL_ESCROW_MARKER,
                        )
                    ],
                )
            ]
        )
        """
        self.recording_toolchain = None

    def _start_recording(self):

        main_switch = self.root.ids.screen_manager.get_screen(  # FIXME simplify
                    "MainMenu"
                ).ids.switch

        shared_secret_threshold = self.get_shared_secret_threshold()

        if shared_secret_threshold >= len(self.selected_authentication_device_uids):
            Snackbar(
                text="Configuration error, first import and select enough key devices, and set the 'threshold' setting accordingly.",
                font_size="12sp",
                duration=5,
                #button_text="BUTTON",
                #button_callback=app.callback
            ).show()
            main_switch.active = False
            return

        # FIXME display popup if WRONG PARAMS!!!

        assert not self.recording_toolchain, self.recording_toolchain  # By construction...
        container_conf = _generate_encryption_conf(  # FIXME call this for EACH CONTAINER!!
                shared_secret_threshold=shared_secret_threshold,
                authentication_devices_used=self.selected_authentication_device_uids
        )
        recording_toolchain = RecordingToolchain(
            recordings_folder=rtsp_recordings_folder,
            conf=container_conf,
            key_type="RSA_OAEP",
            camera_url=self.get_url_camera(),  # FIXME rename
            recording_time=20,  # Fixme say "seconds"
            segment_time=None,
        )
        print(">>> started launching recording toolchain")
        recording_toolchain.launch_recording_toolchain()
        self.recording_toolchain = recording_toolchain
        print(">>> finished launching recording toolchain")

    @safe_catch_unhandled_exception
    def _stop_recording(self):
        print(">>> started stopping recording toolchain")
        assert self.recording_toolchain, self.recording_toolchain  # By construction...
        self.recording_toolchain.stop_recording_toolchain_and_wait()
        self.recording_toolchain = None
        print(">>> finished stopping recording toolchain")

    @safe_catch_unhandled_exception
    def switch_callback(self, switch_object, switch_value):
        # We just swallow incoherent signals
        if switch_value:
            if not self.recording_toolchain:
                self._start_recording()
        else:
            if self.recording_toolchain:
                self._stop_recording()

    @property
    def screen_manager(self):
        if not self.root:
            return  # Early introspection
        return self.root.ids.screen_manager

    @property
    def selected_authentication_device_uids(self):
        if not self.root:
            return  # Early introspection
        return self.screen_manager.get_screen("Keys_management").selected_authentication_device_uids

    @selected_authentication_device_uids.setter
    def selected_authentication_device_uids(self, device_uids):
        self.screen_manager.get_screen("Keys_management").selected_authentication_device_uids = device_uids

    @property
    def nav_drawer(self):
        if not self.root:
            return  # Early introspection
        return self.root.ids.nav_drawer

    def build(self):
        pass

    #def build_config(self, config):
        #print(">> IN build_config")
    #    config.setdefaults("nvr", {})

    def get_shared_secret_threshold(self):
        return int(self.config.get("nvr", "shared_secret_threshold"))

    def get_url_camera(self):
        return self.config.get("nvr", "ip_camera_url")

    def build_settings(self, settings):
        settings_file = self.config_schema_path
        assert settings_file.exists(), settings_file
        settings.add_json_panel("NVR", self.config, filename=settings_file)

    def on_config_change(self, config, section, key, value):
        print("CONFIG CHANGE", section, key, value)

    def log_output(self, msg):
        return  # DISABLED FOR NOW
        console_output = self.root.ids.screen_manager.get_screen(
            "MainMenu"
        ).ids.kivy_console.ids.console_output
        console_output.add_text(
            msg
        )

    def on_start(self):

        try:
            import logging_tree
            logging_tree.printout()
        except ImportError:
            pass  # Optional debug stuff


        # Inject dependencies of loading screens
        container_store_screen = self.root.ids.screen_manager.get_screen("Container_management")  # FIXME simplify
        container_store_screen.filesystem_container_storage = filesystem_container_storage
        authentication_device_store_screen = self.root.ids.screen_manager.get_screen("Keys_management")
        authentication_device_store_screen.filesystem_key_storage_pool = filesystem_key_storage_pool

        authentication_device_store_screen.bind(on_selected_authentication_devices_changed=self.handle_selected_authentication_device_changed)

        log_path = DEFAULT_FILES_ROOT / "log.txt"
        logging.root.addHandler(RotatingFileHandler(log_path, maxBytes=10*(1024**2), backupCount=10))

        self.draw_menu("MainMenu")
        self.log_output("Ceci est un message de log ")
        '''
        self.video = Video(source="zoom_0.mp4")
        self.video.state = "stop"
        self.video.allow_stretch = False
        self.root.ids.screen_manager.get_screen("MainMenu").ids.player.add_widget(
            self.video
        )
        '''

        # Beware these are STRINGS
        selected_authentication_device_uids = self.config["nvr"].get("selected_authentication_device_uids", "").split(",")

        available_authentication_device_uids = filesystem_key_storage_pool.list_imported_key_storage_uids()

        #Check integrity of escrow selection
        selected_authentication_device_uids = [
            x for x in selected_authentication_device_uids
            if x and (UUID(x) in available_authentication_device_uids)
        ]
        print("> Initial selected_authentication_device_uids", selected_authentication_device_uids)
        self.selected_authentication_device_uids = selected_authentication_device_uids

        # create container for tests
        # self.create_containers_for_test()

        # NOW only we refresh authentication devices panel
        #self.get_detected_devices()  # FIXME rename

        Clock.schedule_interval(
            self.update_preview_image, 30
        )

        ##self.fps_monitor_start()  # FPS display for debugging
        '''
        Keys_page_ids = self.root.ids.screen_manager.get_screen(  # FIXME factorize
            "Keys_management"
        ).ids
        Keys_page_ids.device_table.bind(minimum_height=Keys_page_ids.device_table.setter('height'))
        '''

    def on_stop(self):
        print(">>>>>> ON STOP CALLED")
        if self.recording_toolchain:
            self._stop_recording()  # We don't care about GUI controls since we exit anyway...


    def update_preview_image(self, *args, **kwargs):
        print("We update_preview_image")
        main_page_ids = self.root.ids.screen_manager.get_screen(
            "MainMenu"
        ).ids
        preview_image_widget = main_page_ids.preview_image

        if preview_image_path.exists():
            preview_image_widget.source = str(preview_image_path)
            preview_image_widget.reload()  # Necessary to update texture
        else:
            preview_image_widget.source = str(self.fallback_preview_image_path)


    def draw_menu(self, ecran):
        icons_item = {
            "home": "Main page",
            "key": "Keys management",
            "lock": "Container management",
        }
        for icon_name in icons_item.keys():
            item_draw = ItemDrawer(icon=icon_name, text=icons_item[icon_name])
            item_draw.bind(on_release=self.destination)
            self.root.ids.nav_drawer.ids.content_drawer.ids.md_list.add_widget(item_draw)

    def destination(self, item_drawer):

        if item_drawer.text == "Main page":
            destination = "MainMenu"

        elif item_drawer.text == "Keys management":
            destination = "Keys_management"

        elif item_drawer.text == "Container management":
            destination = "Container_management"
            #self.get_detected_container()

        self.root.ids.screen_manager.current = destination
        self.root.ids.nav_drawer.set_state("close")

    #def close_dialog(self, *args, **kwargs):
    #    self.dialog.dismiss()

    def handle_selected_authentication_device_changed(self, event, device_uids, *args):
        self.config["nvr"]["selected_authentication_device_uids"] = ",".join(device_uids)
        self.config.write()

    '''
    def check_box_container_checked(self, radio_box_checked, value):
        containers_page_ids = self.root.ids.screen_manager.get_screen(
            "Container_management"
        ).ids
        for chbx in self.check_box_container_uuid_dict:
            if chbx.active:
                containers_page_ids.delete.disabled = False
                containers_page_ids.decipher.disabled = False
                break
            else:
                containers_page_ids.delete.disabled = True
                containers_page_ids.decipher.disabled = True


    def _OBSOLETE_import_keys(self, src, dst):  # FIXME: rename this func : move_keys_directory ?
        """
        copy the keys of a src directory and put it in the a dst directory

        """
        target_key_storage = FilesystemKeyStorage(dst)
        list_keypair_identifiers_destination = target_key_storage.list_keypair_identifiers()
        source_key_storage = FilesystemKeyStorage(src)
        list_keypair_identifiers_source = source_key_storage.list_keypair_identifiers()

        for key in list_keypair_identifiers_source:
            if key not in list_keypair_identifiers_destination:
                public_key = source_key_storage.get_public_key(
                    keychain_uid=key["keychain_uid"], key_type=key["key_type"]
                )
                if key["private_key_present"]:
                    private_key = source_key_storage.get_private_key(
                        keychain_uid=key["keychain_uid"], key_type=key["key_type"]
                    )
                target_key_storage.set_keys(
                    keychain_uid=key["keychain_uid"],
                    key_type="RSA_OAEP",
                    public_key=public_key,
                    private_key=private_key,
                )




    def ____create_containers_for_test(self):
        """
        Create 7 containers for the test
        """

        data = b"abc"

        keychain_uid = generate_uuid0()
        metadata = random.choice([None, dict(a=[123])])

        if not Path(".container_storage_ward").exists():
            Path(".container_storage_ward").mkdir()
        for i in range(1, 7):
            container = encrypt_data_into_container(
                data=data,
                conf=self.CONFIG,
                keychain_uid=keychain_uid,
                metadata=metadata,
            )

            container_filepath = Path(".container_storage_ward").joinpath(
                "mycontainer" + str(i) + ".crypt"
            )
            dump_container_to_filesystem(
                container_filepath, container=container, offload_data_ciphertext=False
            )

    def _OBSOLETE_list_containers_for_test(self):
        """
        Return a list of container and container name pair
        """

        con_stor1 = ContainerStorage(
            default_encryption_conf=self.CONFIG, containers_dir=Path(".container_storage_ward")
        )

        list_container_name = con_stor1.list_container_names(as_sorted=True)
        containers_list = []
        for container_name in list_container_name:
            container_filepath = Path(".container_storage_ward").joinpath(
                container_name
            )
            container = load_container_from_filesystem(container_filepath)
            container_and_name_container_pair = [container, container_name]
            containers_list.append(container_and_name_container_pair)
        return containers_list
    '''

def main():
    WardGuiApp().run()
