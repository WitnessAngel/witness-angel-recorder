from kivy.uix.screenmanager import ScreenManager
from kivymd.uix.screen import Screen
from kivy.properties import StringProperty, ListProperty
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout

from kivymd.app import MDApp
from kivymd.theming import ThemableBehavior
from kivymd.uix.list import OneLineIconListItem, MDList
from kivy.uix.checkbox import CheckBox
from pathlib import Path
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from pathlib import PurePath
from kivy.uix.video import Video
from wacryptolib.container import (
    ContainerStorage,
    encrypt_data_into_container,
    load_container_from_filesystem,
    dump_container_to_filesystem,
)
from wacryptolib.utilities import generate_uuid0
import random
from wacryptolib.escrow import LOCAL_ESCROW_MARKER
from wacryptolib.key_device import list_available_key_devices
from wacryptolib.key_storage import FilesystemKeyStorage
from wacryptolib.utilities import load_from_json_file, dump_to_json_file

from kivy.config import Config

Config.set("graphics", "fullscreen", "0")
Config.set("graphics", "show_cursor", "1")

from kivy.uix.settings import SettingsWithTabbedPanel

from settingsjson import settings_json


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
    def __init__(self, **kwargs):
        self.title = "Witness Angel - WardProject"

        super(MainWindow, self).__init__(**kwargs)


class SecondWindow(Screen):
    pass


class ThirdWindow(Screen):
    pass


class WindowManager(ScreenManager):
    pass


class Content(BoxLayout):
    pass


class WARD_GUIApp(MDApp):
    def __init__(self, **kwargs):
        self.title = "Witness Angel - WardProject"
        super(WARD_GUIApp, self).__init__(**kwargs)
        self.settings_cls = SettingsWithTabbedPanel
        self.use_kivy_settings = False
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

    def switch_callback(self, switchObject, switchValue):

        video_widget = self.video
        if switchValue:
            video_widget.state = "play"
        else:
            video_widget.state = "stop"

    def build(self):
        pass

    def build_config(self, config):
        config.setdefaults(
            "example",
            {
                "urlcamera": "/sme/path",
                "number_escrow": 10,
                "min_number_shares": 10,
                "retention_days": 10,
                "recordingdirectory": "/dir_rec-parent/dir_rec",
            },
        )

    def build_settings(self, settings):
        settings.add_json_panel("Witness Angel", self.config, data=settings_json)

    def on_config_change(self, config, section, key, value):
        print(config, section, key, value)

    def log_output(self, msg):
        console_output = self.root.ids.screen_manager.get_screen(
            "MainMenu"
        ).ids.kivy_console.ids.console_output
        # to simulate log
        for i in range(100):
            console_output.add_text(
                msg
                + " "
                + str(i + 1)
                + " "
                + msg
                + msg
                + " "
                + str(i + 1)
                + " "
                + msg
                + msg
                + " "
                + str(i + 1)
                + " "
                + msg
            )

    def on_start(self):
        self.draw_menu("MainMenu")
        self.log_output("Ceci est un message de log ")
        self.video = Video(source="zoom_0.mp4")
        self.video.state = "stop"
        self.video.allow_stretch = False
        self.root.ids.screen_manager.get_screen("MainMenu").ids.player.add_widget(
            self.video
        )
        # create container for tests
        self.create_containers_for_test()

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

    def get_detected_container(self):
        """

        """
        containers_page_ids = self.root.ids.screen_manager.get_screen(
            "Container_management"
        ).ids
        if not Path(r".container_storage_ward").exists():
            # "no container found"
            container_display = Button(
                text=" no container found ",
                background_color=(1, 0, 0, 0.01),
                font_size="28sp",
                color=[0, 1, 0, 1],
            )

            containers_page_ids.table.clear_widgets()
            display_layout = BoxLayout(orientation="horizontal")
            display_layout.add_widget(container_display)
            containers_page_ids.table.add_widget(display_layout)
        else:
            container_local_list = (
                self.list_containers_for_test()
            )  # list of container and name of container
            self.check_box_container_uuid_dict = {}
            self.btn_container_uuid_dict = {}
            index = 0
            containers_page_ids.table.clear_widgets()
            for container in container_local_list:
                print(container[0]["container_uid"])
                container_uid = str(container[0]["container_uid"])
                container_uuid = container_uid.split("-")
                start_of_uuid = container_uuid[0].lstrip()
                start_of_UUID = start_of_uuid.rstrip()
                self.my_check_box = CheckBox(active=False, size_hint=(0.2, 0.2))
                self.my_check_box.bind(active=self.check_box_container_checked)
                self.my_check_btn = Button(
                    text=" Container N°:  %s        %s      |      ID container :  %s "
                    % ((str(index + 1)), "", start_of_UUID),
                    size_hint=(0.8, 0.2),
                    background_color=(1, 1, 1, 0.01),
                    on_press=self.show_container_details,
                )
                self.check_box_container_uuid_dict[self.my_check_box] = [
                    str(container[0]["container_uid"]),
                    str(container[1]),
                ]
                self.btn_container_uuid_dict[self.my_check_btn] = [
                    str(container[0]["container_uid"]),
                    str(container[1]),
                ]
                self.layout = BoxLayout(
                    orientation="horizontal",
                    pos_hint={"center": 1, "top": 1},
                    padding=[140, 0],
                )
                self.layout.add_widget(self.my_check_box)
                self.layout.add_widget(self.my_check_btn)
                containers_page_ids.table.add_widget(self.layout)
                index += 1

    def info_keys_stored(self, btn_selected):

        """
        display the information of the keys stored in the selected usb

        """

        # get num of key device and user info
        info_usb_user = btn_selected.text.split("|      UUID device:")[0]
        # search for files that match with the selected device_uuid
        files = [
            f
            for f in Path(r".keys_storage_ward").iterdir()
            if str(PurePath(f).name) == str(self.btn_lbls[btn_selected])
        ]

        for usb_dir in files:
            object_FilesystemKeyStorage = FilesystemKeyStorage(usb_dir)
            public_key_list = object_FilesystemKeyStorage.list_keys()
            message = ""
            private_key_present = ""
            for index, key in enumerate(public_key_list):
                if key["private_key_present"]:
                    private_key_present = "X"
                message += (
                    " key  N°:  %s        keychain_uid:  %s      type:    %s    private_key:    %s\n"
                    % (
                        str(index + 1),
                        (str(key["keychain_uid"]).split("-"))[0],
                        str(key["key_type"]),
                        private_key_present,
                    )
                )
            self.open_dialog_display_keys_in_key_device(message, info_usb_user)

    def open_dialog_display_keys_in_key_device(self, message, info_usb_user):

        self.dialog = MDDialog(
            title="%s" % info_usb_user,
            text=message,
            size_hint=(0.8, 1),
            buttons=[MDFlatButton(text="Close", on_release=self.close_dialog)],
        )
        self.dialog.open()

    def close_dialog(self, obj):
        self.dialog.dismiss()

    def check_box_key_device_checked(self, check_box_checked):
        print(self.chbx_lbls[check_box_checked])

    def check_box_container_checked(self, radio_box_checked, value):
        containers_page_ids = self.root.ids.screen_manager.get_screen(
            "Container_management"
        ).ids
        print(self.check_box_container_uuid_dict[radio_box_checked])
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
        loop through the “key_devices” present,
        and for those who are initialize, copy (with different KeyStorage for each folder)
        their content in a <KEYS_ROOT> / <device_uid> / folder (taking the device_uid from metadata.json)
        """
        list_devices = list_available_key_devices()
        for index, key_device in enumerate(list_devices):
            if str(key_device["is_initialized"]) == "True":
                if not Path(".keys_storage_ward").exists():
                    Path(".keys_storage_ward").mkdir()
                device_dir = str(key_device["device_uid"])
                file_metadata = Path(".keys_storage_ward").joinpath(
                    device_dir, ".metadata.json"
                )
                metadata_file_path = Path(key_device["path"]).joinpath(
                    ".key_storage", ".metadata.json"
                )
                if not Path(file_metadata.parent).exists():
                    Path(file_metadata.parent).mkdir()
                metadata = load_from_json_file(metadata_file_path)
                print(metadata)
                dump_to_json_file(file_metadata, metadata)
                dst = Path(".keys_storage_ward").joinpath(device_dir)
                key_pairs_dir = Path(key_device["path"]).joinpath(
                    ".key_storage", "crypto_keys"
                )
                # copy contents keys of key_pairs_dir to dst(copy key storage to <KEYS_ROOT>/<device_uid>)
                self._import_keys(key_pairs_dir, dst)
        # update the display of key_device saved in the local folder .keys_storage_ward
        self.get_detected_devices()

    def _import_keys(self, src, dst):
        """
        copy the keys of a src directory and put it in the a dst directory

        """
        target_key_storage = FilesystemKeyStorage(dst)
        list_keys_destination = target_key_storage.list_keys()
        source_key_storage = FilesystemKeyStorage(src)
        list_keys_source = source_key_storage.list_keys()

        for key in list_keys_source:
            if key not in list_keys_destination:
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

    def get_detected_devices(self):
        """
        loop through the KEYS_ROOT / files, and read their metadata.json,
        to display in the interface their USER and the start of their UUID

        KEYS_ROOT = “~/.keys_storage_ward/”
        """
        containers_page_ids = self.root.ids.screen_manager.get_screen(
            "Keys_management"
        ).ids
        if not Path(r".keys_storage_ward").exists():
            # "no key found"
            devices_display = Button(
                text=" no key found ",
                background_color=(1, 0, 0, 0.01),
                font_size="28sp",
                color=[0, 1, 0, 1],
            )
            containers_page_ids.table.clear_widgets()
            Display_layout = BoxLayout(orientation="horizontal", padding=[140, 0])
            Display_layout.add_widget(devices_display)
            containers_page_ids.table.add_widget(Display_layout)
        else:
            result = [f for f in Path(r".keys_storage_ward").iterdir()]
            index = 0
            containers_page_ids.table.clear_widgets()
            self.chbx_lbls = {}
            self.btn_lbls = {}
            for dir_key_sorage in result:
                file_metadata = Path(dir_key_sorage).joinpath(".metadata.json")
                metadata = load_from_json_file(file_metadata)
                device_uid = str(metadata["device_uid"])
                uuid = device_uid.split("-")
                start_of_uuid = uuid[0].lstrip()
                start_of_UUID = start_of_uuid.rstrip()
                self.my_check_box = CheckBox(
                    active=False,
                    size_hint=(0.2, 0.2),
                    on_release=self.check_box_key_device_checked,
                )
                self.my_check_btn = Button(
                    text=" key N°:  %s        User:  %s      |      UUID device:  %s "
                    % ((str(index + 1)), str(metadata["user"]), start_of_UUID),
                    size_hint=(0.8, 0.2),
                    background_color=(1, 1, 1, 0.01),
                    on_press=self.info_keys_stored,
                )
                self.chbx_lbls[self.my_check_box] = str(metadata["device_uid"])
                self.btn_lbls[self.my_check_btn] = str(metadata["device_uid"])
                self.layout = BoxLayout(
                    orientation="horizontal",
                    pos_hint={"center": 1, "top": 1},
                    padding=[140, 10],
                    spacing=[0, 10],
                )
                self.layout.add_widget(self.my_check_box)
                self.layout.add_widget(self.my_check_btn)
                containers_page_ids.table.add_widget(self.layout)
                index += 1

    def check_box_key_device_checked(self, check_box_checked):
        """
        Display the device checked
        """
        print(self.chbx_lbls[check_box_checked])

    def show_container_details(self, btn_selected):

        """
        Display the contents of container
        """
        info_container = btn_selected.text.split("|      ID container :")[0]
        num_container = info_container.split("N°:")[1]
        num_container = num_container.lstrip()
        num_container = num_container.rstrip()

        container_selected_and_container_name = self.btn_container_uuid_dict[
            btn_selected
        ]
        container_dir = Path(".container_storage_ward").joinpath(
            container_selected_and_container_name[1]
        )
        message = load_container_from_filesystem(container_dir)
        self.open_container_details_dialog(str(message), info_container)

    def open_container_details_dialog(self, message, info_container_and_user):
        self.dialog = MDDialog(
            title=" %s" % info_container_and_user,
            text=message,
            size_hint=(0.8, 1),
            buttons=[MDFlatButton(text="Close", on_release=self.close_dialog)],
        )
        self.dialog.open()

    def open_dialog_delete_container(self):
        self.count_container_checked = 0
        self.list_chbx_active = []
        for chbx in self.check_box_container_uuid_dict:
            if chbx.active:
                self.list_chbx_active.append(chbx)
                self.count_container_checked += 1

        # len(self.list_chbx_active)
        if len(self.list_chbx_active) == 1:
            messge = " do you want to delete these container?"
        elif len(self.list_chbx_active) > 1:
            messge = (
                " do you want to delete these %d containers"
                % self.count_container_checked
            )
        self.dialog = MDDialog(
            title=" Delete containers confirmation ",
            text=messge,
            size_hint=(0.8, 1),
            buttons=[
                MDFlatButton(
                    text="Confirm delete", on_release=self.close_dialog_delete_container
                ),
                MDFlatButton(text="Cancel", on_release=self.close_dialog),
            ],
        )
        self.dialog.open()

    def close_dialog_delete_container(self, obj):
        for chbx in self.list_chbx_active:

            container_selected = self.check_box_container_uuid_dict[chbx]
            print("delete container | with ID_container %s", container_selected)
            con_stor1 = ContainerStorage(
                encryption_conf=self.CONFIG,
                containers_dir=Path(".container_storage_ward"),
            )

            con_stor1._delete_container(container_selected[1])
        self.get_detected_container()
        self.dialog.dismiss()

    def open_dialog_decipher_container(self):
        count_container_checked = 0
        for chbx in self.check_box_container_uuid_dict:
            if chbx.active:
                count_container_checked += 1

        if count_container_checked == 1:
            messge = " do you want to decipher these container?"
        elif count_container_checked > 1:
            messge = (
                " Do you want to decipher these %d containers" % count_container_checked
            )

        self.dialog = MDDialog(
            title=" Decipher containers confirmation ",
            type="custom",
            content_cls=Content(),
            text=messge,
            size_hint=(0.8, 1),
            buttons=[
                MDFlatButton(
                    text="Confirm  decipher",
                    on_release=self.close_dialog_decipher_container,
                ),
                MDFlatButton(text="Cancel", on_release=self.close_dialog),
            ],
        )

        self.dialog.open()

    def close_dialog_decipher_container(self, obj):

        input = self.dialog.content_cls.ids.pass_text.text

        print("The written sentence is passphrase : %s" % input)

        for chbx in self.check_box_container_uuid_dict:
            if chbx.active:
                print(
                    "Decipher container | with ID_container %s",
                    self.check_box_container_uuid_dict[chbx],
                )
        self.dialog.dismiss()

    def create_containers_for_test(self):
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

    def list_containers_for_test(self):
        """
        Return a list of container and container name pair
        """

        con_stor1 = ContainerStorage(
            encryption_conf=self.CONFIG, containers_dir=Path(".container_storage_ward")
        )

        list_container_name = con_stor1.list_container_names(as_sorted=True)
        print(list_container_name)  # returns an empty list?!
        containers_list = []
        for container_name in list_container_name:
            container_filepath = Path(".container_storage_ward").joinpath(
                container_name
            )
            container = load_container_from_filesystem(container_filepath)
            container_and_name_container_pair = [container, container_name]
            containers_list.append(container_and_name_container_pair)
        return containers_list


WARD_GUIApp().run()
