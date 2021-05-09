# Tweak logging before Kivy breaks it
import functools
import inspect

import os, sys, logging

from waguilib import kivy_presetup  # Trigger common kivy setup

from pathlib import Path
from uuid import UUID
from logging.handlers import RotatingFileHandler
from waguilib.application import WAGuiApp
from waguilib.widgets.navigation_drawer import ItemDrawer

from kivy.clock import Clock
from kivy.uix.screenmanager import ScreenManager
from kivymd.uix.snackbar import Snackbar

from wanvr.common import WanvrRuntimeSupportMixin
'''
from wanvr.rtsp_recorder.ciphering_toolchain import _generate_encryption_conf, RecordingToolchain, \
    filesystem_key_storage_pool, \
    filesystem_container_storage, rtsp_recordings_folder, preview_image_path, DEFAULT_FILES_ROOT
'''
from waguilib.logging.handlers import safe_catch_unhandled_exception

WANVR_PACKAGE_DIR = Path(__file__).resolve().parent

# FIXME rename this file as foreground_app

# TODO - add retro "ping" from toolchain when a new record is present

class WardGuiApp(WanvrRuntimeSupportMixin, WAGuiApp):  # FIXME rename this

    title = "Witness Angel - NVR"

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

        main_switch = self.screen_manager.get_screen(  # FIXME simplify
                    "MainPage"
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

        # TODO call OSCP starter

    @safe_catch_unhandled_exception
    def _stop_recording(self):
        print(">>> started stopping recording toolchain")
        assert self.recording_toolchain, self.recording_toolchain  # By construction...
        self.recording_toolchain.stop_recording_toolchain_and_wait()
        self.recording_toolchain = None
        print(">>> finished stopping recording toolchain")

    @safe_catch_unhandled_exception
    def switch_callback(self, switch_object, switch_value):  # FIXME RENAME METHOD
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
        return self.screen_manager.get_screen("KeyManagement").selected_authentication_device_uids

    @selected_authentication_device_uids.setter
    def selected_authentication_device_uids(self, device_uids):
        self.screen_manager.get_screen("KeyManagement").selected_authentication_device_uids = device_uids

    @property
    def navigation_drawer(self):
        if not self.root:
            return  # Early introspection
        return self.root.ids.navigation_drawer

    '''
    def build(self):
        pass
    '''
    #def build_config(self, config):
        #print(">> IN build_config")
    #    config.setdefaults("nvr", {})


    def build_settings(self, settings):
        settings_file = self.config_schema_path
        assert settings_file.exists(), settings_file
        settings.add_json_panel("NVR", self.config, filename=settings_file)

    def on_config_change(self, config, section, key, value):
        print("CONFIG CHANGE", section, key, value)

    def log_output(self, msg):
        return  # DISABLED FOR NOW
        console_output = self.screen_manager.get_screen(
            "MainPage"
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
        container_store_screen = self.screen_manager.get_screen("ContainerManagement")  # FIXME simplify
        container_store_screen.filesystem_container_storage = self.filesystem_container_storage
        authentication_device_store_screen = self.screen_manager.get_screen("KeyManagement")
        authentication_device_store_screen.filesystem_key_storage_pool = self.filesystem_key_storage_pool

        authentication_device_store_screen.bind(on_selected_authentication_devices_changed=self.handle_selected_authentication_device_changed)

        self._insert_app_menu()
        self.log_output("Ceci est un message de log ")
        '''
        self.video = Video(source="zoom_0.mp4")
        self.video.state = "stop"
        self.video.allow_stretch = False
        self.root.ids.screen_manager.get_screen("MainMenu").ids.player.add_widget(
            self.video
        )
        '''

        self.selected_authentication_device_uids = self.get_selected_authentication_device_uids()

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
            "KeyManagement"
        ).ids
        Keys_page_ids.device_table.bind(minimum_height=Keys_page_ids.device_table.setter('height'))
        '''

    def _insert_app_menu(self):
        screen_options = {
            "MainPage": ("home", "Main Page"),
            "KeyManagement": ("key", "Key Management"),
            "ContainerManagement": ("lock", "Container Management"),
        }
        for screen_name, (icon_name, screen_title) in screen_options.items():
            item_draw = ItemDrawer(icon=icon_name, text=screen_title)
            item_draw.bind(on_release=functools.partial(self.switch_to_screen, screen_name=screen_name))
            self.navigation_drawer.ids.content_drawer.ids.md_list.add_widget(item_draw)
            
    '''
    def on_stop(self):
        print(">>>>>> ON STOP CALLED")
        if self.recording_toolchain:
            self._stop_recording()  # We don't care about GUI controls since we exit anyway...
    '''

    def update_preview_image(self, *args, **kwargs):
        print("We update_preview_image")
        main_page_ids = self.screen_manager.get_screen(
            "MainPage"
        ).ids
        preview_image_widget = main_page_ids.preview_image

        if self.preview_image_path.exists():
            preview_image_widget.source = str(self.preview_image_path)
            preview_image_widget.reload()  # Necessary to update texture
        else:
            preview_image_widget.source = str(self.fallback_preview_image_path)

    def switch_to_screen(self, *args, screen_name):
        self.screen_manager.current = screen_name
        self.navigation_drawer.set_state("screen_name")

    #def close_dialog(self, *args, **kwargs):
    #    self.dialog.dismiss()

    def handle_selected_authentication_device_changed(self, event, device_uids, *args):
        self.config["nvr"]["selected_authentication_device_uids"] = ",".join(device_uids)
        self.save_config()

    '''
    def check_box_container_checked(self, radio_box_checked, value):
        containers_page_ids = self.root.ids.screen_manager.get_screen(
            "ContainerManagement"
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
