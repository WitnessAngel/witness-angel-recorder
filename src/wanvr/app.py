# Tweak logging before Kivy breaks it
import os, sys, logging

if sys.platform == "win32":
    os.environ["KIVY_GL_BACKEND"] = "angle_sdl2"

os.environ["KIVY_NO_CONSOLELOG"] = "1"
#ogging.root.setLevel(logging.DEBUG)
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("wacryptolib").setLevel(logging.DEBUG)
logging.getLogger("wanvr").setLevel(logging.DEBUG)
REAL_ROOT_LOGGER = logging.root

import pprint
import random
from functools import partial
from pathlib import Path
from uuid import UUID
from logging.handlers import RotatingFileHandler

from kivy.config import Config
Config.set('graphics', 'top', '50')
Config.set('graphics', 'left', '50')
Config.set('graphics', 'position', 'custom')

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
    safe_catch_unhandled_exception, DEFAULT_FILES_ROOT
from wacryptolib.container import (
    ContainerStorage,
    encrypt_data_into_container,
    decrypt_data_from_container,
    request_decryption_authorizations,
    gather_escrow_dependencies,
    load_container_from_filesystem,
    dump_container_to_filesystem,
)
from wacryptolib.authentication_device import list_available_authentication_devices, \
    _get_key_storage_folder_path
from wacryptolib.exceptions import KeyStorageAlreadyExists
from wacryptolib.utilities import generate_uuid0

# FIXME this happens too late I guess
Config.set("graphics", "fullscreen", "0")
Config.set("graphics", "show_cursor", "1")

from kivy.uix.settings import SettingsWithTabbedPanel


PACKAGE_ROOT = Path(__file__).parent


class ContentNavigationDrawer(BoxLayout):
    pass


class ItemDrawer(OneLineIconListItem):
    icon = StringProperty()
    text_color = ListProperty((0, 0, 0, 1))


class DrawerList(ThemableBehavior, MDList):
    def set_color_item(self, instance_item):
        """
        Called when tap on a menu item.
        """
        for item in self.children:
            if instance_item.text == item.text:
                item.text_color = (0.1372, 0.2862, 0.5294, 1)
            else:
                item.text_color = (0, 0, 0, 1)


class MainWindow(Screen):
    pass
    """
    def __init__(self, **kwargs):
        self.title = "Witness Angel - WardProject"

        super(MainWindow, self).__init__(**kwargs)
    """

class SecondWindow(Screen):
    pass


class ThirdWindow(Screen):
    pass


class WindowManager(ScreenManager):
    pass


class PassphrasesDialogContent(BoxLayout):
    pass


# TODO - add retro "ping" from toolchain when a new record is present

class WardGuiApp(MDApp):

    dialog = None  # Any current modal dialog must be stored here

    use_kivy_settings = False
    settings_cls = SettingsWithTabbedPanel

    app_logo_path = PACKAGE_ROOT.joinpath("logo-wa.png")
    fallback_image_path = app_logo_path

    def __init__(self, **kwargs):
        self.title = "Witness Angel - WardProject"
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
        self.selected_authentication_device_uids = []
        self.recording_toolchain = None

    def _start_recording(self):

        main_switch = self.root.ids.screen_manager.get_screen(
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
            recording_time=60*60,  # Fixme say "seconds"
            segment_time=15*60,  # Fixme say "seconds"
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
        return self.root.ids.screen_manager

    @property
    def nav_drawer(self):
        return self.root.ids.nav_drawer

    def build(self):
        pass

    def build_config(self, config):
        #print(">> IN build_config")
        config.setdefaults("nvr", {})

    def get_shared_secret_threshold(self):
        return int(self.config.get("nvr", "shared_secret_threshold"))

    def get_url_camera(self):
        return self.config.get("nvr", "ip_camera_url")

    def build_settings(self, settings):
        settings_file = PACKAGE_ROOT / "user_settings_schema.json"
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

        log_path = DEFAULT_FILES_ROOT / "log.txt"
        REAL_ROOT_LOGGER.addHandler(RotatingFileHandler(log_path, maxBytes=10*(1024**2), backupCount=10))

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
        self.get_detected_devices()  # FIXME rename

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
            preview_image_widget.source = str(self.fallback_image_path)


    def draw_menu(self, ecran):
        icons_item = {
            "home": "Main page",
            "key": "Keys management",
            "lock": "Container management",
        }
        for icon_name in icons_item.keys():
            item_draw = ItemDrawer(icon=icon_name, text=icons_item[icon_name])
            item_draw.bind(on_release=self.destination)
            self.root.ids.content_drawer.ids.md_list.add_widget(item_draw)

    def destination(self, item_drawer):

        if item_drawer.text == "Main page":
            destination = "MainMenu"

        elif item_drawer.text == "Keys management":
            destination = "Keys_management"

        elif item_drawer.text == "Container management":
            destination = "Container_management"
            self.get_detected_container()

        self.root.ids.screen_manager.current = destination
        self.root.ids.nav_drawer.set_state("close")

    @safe_catch_unhandled_exception
    def get_detected_container(self):
        containers_page_ids = self.root.ids.screen_manager.get_screen(
            "Container_management"
        ).ids

        container_names = filesystem_container_storage.list_container_names(as_sorted=True)

        containers_page_ids.container_table.clear_widgets()

        if not container_names:
            container_display = Button(
                text="No container found",
                background_color=(1, 0, 0, 0.01),
                font_size="28sp",
                color=[0, 1, 0, 1],
            )
            display_layout = BoxLayout(orientation="horizontal")
            display_layout.add_widget(container_display)
            containers_page_ids.container_table.add_widget(display_layout)
            return

        self.check_box_container_uuid_dict = {}
        self.btn_container_uuid_dict = {}

        self.container_checkboxes = []

        for index, container_name in enumerate(container_names, start=1):

            my_check_box = CheckBox(active=False,
                                    size_hint=(0.1, None), height=40)
            my_check_box._container_name = container_name
            #my_check_box.bind(active=self.check_box_container_checked)
            self.container_checkboxes.append(my_check_box)

            my_check_btn = Button(
                text="N° %s:  %s"
                % (index, container_name),
                size_hint=(0.9, None),
                background_color=(1, 1, 1, 0.01),
                on_release=partial(self.show_container_details, container_name=container_name),
                height=40,
            )
            '''
            self.check_box_container_uuid_dict[my_check_box] = [
                str(container[0]["container_uid"]),
                str(container[1]),
            ]
            self.btn_container_uuid_dict[my_check_btn] = [
                str(container[0]["container_uid"]),
                str(container[1]),
            ]
            '''
            """
            layout = BoxLayout(
                orientation="horizontal",
                pos_hint={"center": 1, "top": 1},
                padding=[20, 0],
            )
            layout.add_widget(my_check_box)
            layout.add_widget(my_check_btn)
            """
            containers_page_ids.container_table.add_widget(my_check_box)
            containers_page_ids.container_table.add_widget(my_check_btn)

        #print("self.container_checkboxes", self.container_checkboxes)

    def get_selected_container_names(self):

        containers_page_ids = self.root.ids.screen_manager.get_screen(
            "Container_management"
        ).ids

        container_names = []

        checkboxes = list(reversed(containers_page_ids.container_table.children))[::2]

        for checkbox in checkboxes:
            if checkbox.active:
                container_names.append(checkbox._container_name)

        print("container_names", container_names)
        return container_names

    def info_keys_stored(self, btn_selected, device_uid, user):

        """
        display the information of the keys stored in the selected usb

        """
        imported_key_storage = filesystem_key_storage_pool.get_imported_key_storage(key_storage_uid=device_uid)
        keypair_identifiers = imported_key_storage.list_keypair_identifiers()

        message = ""
        for index, keypair_identifier in enumerate(keypair_identifiers, start=1):

            private_key_present_str = "Yes" if keypair_identifier["private_key_present"] else "No"
            uuid_suffix = str(keypair_identifier["keychain_uid"]).split("-")[-1]

            message += (
                " Key n° %s, Uid: ...%s, type: %s\n" #, has_private_key:    %s\n"
                % (
                    index,
                    uuid_suffix,
                    keypair_identifier["key_type"],
                    #private_key_present_str,
                )
                )
        self.open_dialog_display_keys_in_authentication_device(message, user=user)

    def open_dialog_display_keys_in_authentication_device(self, message, user):
        self.dialog = MDDialog(
            title="Imported authentication device of user %s" % user,
            text=message,
            size_hint=(0.8, 1),
            buttons=[MDFlatButton(text="Close", on_release=self.close_dialog)],
        )
        self.dialog.open()

    def close_dialog(self, *args, **kwargs):
        self.dialog.dismiss()

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

    def import_keys(self):
        """
        loop through the “authentication_devices” present,
        and for those who are initialize, copy (with different KeyStorage for each folder)
        their content in a <KEYS_ROOT> / <device_uid> / folder (taking the device_uid from metadata.json)
        """
        # list_devices = list_available_authentication_devices()
        # print(list_devices)
        # for index, authentication_device in enumerate(list_devices):
        #print(">>>>>>>>>> import_keys started")
        authentication_devices = list_available_authentication_devices()

        print("DETECTED AUTH DEVICES", authentication_devices)

        for authentication_device in authentication_devices:
            #print(">>>>>>>>>> importing,", authentication_device)
            if not authentication_device["is_initialized"]:
                continue
            key_storage_folder_path = _get_key_storage_folder_path(authentication_device)
            try:
                filesystem_key_storage_pool.import_key_storage_from_folder(key_storage_folder_path)
            except KeyStorageAlreadyExists:
                pass  # We tried anyway, since some "update" mevhanics might be setup one day

        # update the display of authentication_device saved in the local folder .keys_storage_ward
        self.get_detected_devices()

    '''
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
    '''

    def get_detected_devices(self):
        """
        loop through the KEYS_ROOT / files, and read their metadata.json,
        to display in the interface their USER and the start of their UUID

        KEYS_ROOT = “~/.keys_storage_ward/”
        """
        print(">> we refresh auth devices panel")
        Keys_page_ids = self.root.ids.screen_manager.get_screen(
            "Keys_management"
        ).ids

        Keys_page_ids.device_table.clear_widgets()  # FIXME naming

        key_storage_metadata = filesystem_key_storage_pool.list_imported_key_storage_metadata()

        if not key_storage_metadata:
            self.display_message_no_device_found()
            return

        self.chbx_lbls = {}  # FIXME: lbls ?
        self.btn_lbls = {}  # FIXME: lbls ?

        for (index, (device_uid, metadata)) in enumerate(sorted(key_storage_metadata.items()), start=1):
            uuid_suffix = str(device_uid).split("-")[-1]
            #print("COMPARING", str(device_uid), self.selected_authentication_device_uids)
            my_check_box = CheckBox(
                active=(str(device_uid) in self.selected_authentication_device_uids),
                size_hint=(0.15, None),
                on_release=self.check_box_authentication_device_checked,
                height=40,
            )
            my_check_btn = Button(
                text="Key n°%s, User %s, Uid %s" % (index, metadata["user"], uuid_suffix),
                size_hint=(0.85, None),
                background_color=(0, 1, 1, 0.1),
                on_release=partial(self.info_keys_stored, device_uid=device_uid, user=metadata["user"]),
                height=40,
            )
            self.chbx_lbls[my_check_box] = str(device_uid)
            self.btn_lbls[my_check_btn] = str(device_uid)
           # device_row = BoxLayout(
            #    orientation="horizontal",
                #pos_hint={"center": 1, "top": 1},
                #padding=[20, 0],
           #)
            Keys_page_ids.device_table.add_widget(my_check_box)
            Keys_page_ids.device_table.add_widget(my_check_btn)
            #Keys_page_ids.device_table.add_widget(device_row)

        """
                file_metadata = Path(dir_key_sorage).joinpath(".metadata.json")
                if file_metadata.exists():

                    metadata = load_from_json_file(file_metadata)
                    device_uid = str(metadata["device_uid"])
                    uuid = device_uid.split("-")
                    start_of_uuid = uuid[0].lstrip()
                    start_of_UUID = start_of_uuid.rstrip()
                    my_check_box = CheckBox(#start
                        active=False,
                        size_hint=(0.2, 0.2),
                        on_release=self.check_box_authentication_device_checked,
                    )
                    my_check_btn = Button(
                        text=" key N°:  %s        User:  %s      |      UUID device:  %s "
                        % ((str(index + 1)), str(metadata["user"]), start_of_UUID),
                        size_hint=(0.8, 0.2),
                        background_color=(1, 1, 1, 0.01),
                        on_press=self.info_keys_stored,
                    )
                    self.chbx_lbls[my_check_box] = str(metadata["device_uid"])
                    self.btn_lbls[my_check_btn] = str(metadata["device_uid"])
                    layout = BoxLayout(
                        orientation="horizontal",
                        pos_hint={"center": 1, "top": 1},
                        padding=[140, 0]
                    )
                    layout.add_widget(my_check_box)
                    layout.add_widget(my_check_btn)
                    Keys_page_ids.table.add_widget(layout)
                    index += 1
                else:
                    self.display_message_no_device_found()
        """

    def display_message_no_device_found(self):
        keys_page_ids = self.root.ids.screen_manager.get_screen(
            "Keys_management"
        ).ids
        devices_display = Button(
            text="No imported autentication device found ",
            background_color=(1, 0, 0, 0.01),
            font_size="28sp",
            color=[0, 1, 0, 1],
        )
        keys_page_ids.device_table.clear_widgets()
        Display_layout = BoxLayout(orientation="horizontal", padding=[140, 0])
        Display_layout.add_widget(devices_display)
        keys_page_ids.device_table.add_widget(Display_layout)

    def check_box_authentication_device_checked(self, check_box_checked):
        """
        Display the device checked
        """
        if self.chbx_lbls[check_box_checked] in self.selected_authentication_device_uids:
            self.selected_authentication_device_uids.remove(self.chbx_lbls[check_box_checked])
        else:
            self.selected_authentication_device_uids.append(self.chbx_lbls[check_box_checked])
        self.config["nvr"]["selected_authentication_device_uids"] = ",".join(self.selected_authentication_device_uids)
        self.config.write()
        print("self.selected_authentication_device_uids", self.selected_authentication_device_uids)

    def show_container_details(self, btn_selected, container_name):
        """
        Display the contents of container
        """
        try:
            container = filesystem_container_storage.load_container_from_storage(container_name)
            all_dependencies = gather_escrow_dependencies([container])
            interesting_dependencies = [d[0] for d in list(all_dependencies["encryption"].values())]
            container_repr = pprint.pformat(interesting_dependencies, indent=2)[:800]  # LIMIT else pygame.error: Width or height is too large
        except Exception as exc:
            container_repr = repr(exc)

        self.open_container_details_dialog(container_repr, info_container=container_name)

    def open_container_details_dialog(self, message, info_container):
        self.dialog = MDDialog(
            title=str(info_container),
            text=message,
            size_hint=(0.8, 1),
            buttons=[MDFlatButton(text="Close", on_release=self.close_dialog)],
        )
        self.dialog.open()

    def open_dialog_delete_container(self):

        container_names = self.get_selected_container_names()
        if not container_names:
            return

        message = "Are you sure you want to delete %s container(s)?" % len(container_names)
        """
        self.list_chbx_active = []
        for chbx in self.check_box_container_uuid_dict:
            if chbx.active:
                self.list_chbx_active.append(chbx)

        count_container_checked =len(self.list_chbx_active)
        if count_container_checked == 1:
            messge = " do you want to delete these container?"
        elif count_container_checked > 1:
            messge = (
                " do you want to delete these %d containers"
                % count_container_checked
            )
        """
        self.dialog = MDDialog(
            title="Container deletion confirmation",
            text=message,
            size_hint=(0.8, 1),
            buttons=[
                MDFlatButton(
                    text="Confirm deletion", on_release=partial(self.close_dialog_delete_container, container_names=container_names)
                ),
                MDFlatButton(text="Cancel", on_release=self.close_dialog),
            ],
        )
        self.dialog.open()

    def close_dialog_delete_container(self, obj, container_names):

        for container_name in container_names:
            try:
                filesystem_container_storage.delete_container(container_name)
            except FileNotFoundError:
                pass  # File has probably been puregd already

        self.get_detected_container()  # FIXME rename
        self.dialog.dismiss()

    def open_dialog_decipher_container(self):

        container_names = self.get_selected_container_names()
        if not container_names:
            return

        message = "Decrypt %s container(s)?" % len(container_names)

        """
        self.list_chbx_active = []
        for chbx in self.check_box_container_uuid_dict:
            if chbx.active:
                self.list_chbx_active.append(chbx)

        count_container_checked = len(self.list_chbx_active)

        if count_container_checked == 1:
            messge = " do you want to decipher these container?"
        elif count_container_checked > 1:
            messge = (
                    " Do you want to decipher these %d containers" % count_container_checked
            )
        """

        key_storage_metadata = filesystem_key_storage_pool.list_imported_key_storage_metadata()

        containers = [filesystem_container_storage.load_container_from_storage(x) for x in container_names]
        dependencies = gather_escrow_dependencies(containers)

        relevant_authentication_device_uids = [escrow[0]["authentication_device_uid"] for escrow in dependencies["encryption"].values()]

        relevant_key_storage_metadata = sorted([y for (x,y) in key_storage_metadata.items()
                                                if x in relevant_authentication_device_uids], key = lambda d: d["user"])

        print("--------------")
        pprint.pprint(relevant_key_storage_metadata)


        content = PassphrasesDialogContent()

        for metadata in relevant_key_storage_metadata:
            hint_text="Passphrase for user %s (hint: %s)" % (metadata["user"], metadata["passphrase_hint"])
            _widget = TextInput(hint_text=hint_text)

            '''MDTextField(hint_text="S SSSSSSSS z z",
                              helper_text="Passphrase for user %s (hint: %s)" % (metadata["user"], metadata["passphrase_hint"]),
                              helper_text_mode="on_focus",
                              **{                    "color_mode": 'custom',
                                                  "line_color_focus": (0.4, 0.5, 1, 1),
                                                  "mode": "fill",
                                                  "fill_color": (0.3, 0.3, 0.3, 0.4),
                                                  "current_hint_text_color": (0.1, 1, 0.2, 1)})'''
            content.add_widget(_widget)

        self.dialog = MDDialog(
            title=message,
            type="custom",
            content_cls=content,
            #text=message,
            size_hint=(0.8, 1),
            buttons=[
                MDFlatButton(
                    text="Launch decryption",
                    on_release=partial(self.close_dialog_decipher_container, container_names=container_names),
                ),
                MDFlatButton(text="Cancel", on_release=self.close_dialog),
            ],
        )

        self.dialog.open()

    def close_dialog_decipher_container(self, obj, container_names):
        self.dialog.dismiss()

        inputs = list(reversed(self.dialog.content_cls.children))
        passphrases = [i.text for i in inputs]
        passphrase_mapper = {None: passphrases}  # For now we regroup all passphrases together

        errors = []

        for container_name in container_names:
            try:
                result = filesystem_container_storage.decrypt_container_from_storage(container_name, passphrase_mapper=passphrase_mapper)
                target_path = decrypted_records_folder / (Path(container_name).with_suffix(""))
                target_path.write_bytes(result)
                print(">> Successfully exported data file to %s" % target_path)
            except Exception as exc:
                errors.append(exc)

        if errors:
            message = "Errors happened during decryption, see logs"
        else:
            message = "Decryption successful, see export folder for results"

        Snackbar(
            text=message,
            font_size="12sp",
            duration=5,
        ).show()

        """
        print("The written sentence is passphrase : %s" % input)
        containers = []
        for chbx in self.check_box_container_uuid_dict:
            if chbx.active:
                print(
                    "Decipher container | with ID_container %s",
                    self.check_box_container_uuid_dict[chbx],
                )
                container = load_container_from_filesystem(
                    container_filepath=Path(
                        ".container_storage_ward".format(self.check_box_container_uuid_dict[chbx][1])
                    )
                )
                containers.append(container)
        escrow_dependencies = gather_escrow_dependencies(containers=containers)

        decryption_authorizations = request_decryption_authorizations(
            escrow_dependencies=escrow_dependencies,
            key_storage_pool=filesystem_key_storage_pool,
            request_message="Need decryptions"
        )
        for container in containers:
            decrypt_data_from_container(container=container)
            """


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


def main():
    WardGuiApp().run()
