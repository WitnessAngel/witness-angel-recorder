import pprint
import random
import os
from functools import partial
from pathlib import Path
from pathlib import PurePath
from uuid import UUID

# Tweak logging before Kivy breaks it
import logging
logging.basicConfig(level=logging.DEBUG)

from kivy.config import Config
from kivy.properties import StringProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.screenmanager import ScreenManager
from kivy.uix.video import Video
from kivymd.app import MDApp
from kivymd.theming import ThemableBehavior
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import OneLineIconListItem, MDList
from kivymd.uix.screen import Screen
from client.ciphering_toolchain import _generate_encryption_conf, RecordingToolchain, filesystem_key_storage_pool, \
    filesystem_container_storage, rtsp_recordings_folder
from wacryptolib.container import (
    ContainerStorage,
    encrypt_data_into_container,
    decrypt_data_from_container,
    request_decryption_authorizations,
    gather_escrow_dependencies,
    load_container_from_filesystem,
    dump_container_to_filesystem,
    LOCAL_ESCROW_MARKER,
)
from wacryptolib.authentication_device import initialize_authentication_device, list_available_authentication_devices, \
    _get_key_storage_folder_path
from wacryptolib.exceptions import KeyStorageAlreadyExists
from wacryptolib.utilities import generate_uuid0
from wacryptolib.utilities import load_from_json_file, dump_to_json_file

# FIXME this happens too late I guess
Config.set("graphics", "fullscreen", "0")
Config.set("graphics", "show_cursor", "1")

from kivy.uix.settings import SettingsWithTabbedPanel

from settingsjson import settings_json  # FIXME weird


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

    dialog = None  # Any current modal dialog must be stored here

    use_kivy_settings = False
    settings_cls = SettingsWithTabbedPanel

    def __init__(self, **kwargs):
        self.title = "Witness Angel - WardProject"
        super(WARD_GUIApp, self).__init__(**kwargs)

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

    def switch_callback(self, switch_object, switch_value):

        if switch_value:
            container_conf = _generate_encryption_conf(  # FIXME call this for EACH CONTAINER!!
                    shared_secret_threshold=self.get_shared_secret_threshold(),
                    authentication_devices_used=self.selected_authentication_device_uids
            )
            recording_toolchain = RecordingToolchain(
                recordings_folder=rtsp_recordings_folder,
                conf=container_conf,
                key_type="RSA_OAEP",
                camera_url=self.get_url_camera(),  # FIXME rename
                recording_time=20,  # Fixme say "seconds"
                segment_time=5,  # Fixme say "seconds"
            )
            recording_toolchain.launch_recording_toolchain()
            self.recording_toolchain = recording_toolchain
        else:
            assert self.recording_toolchain, self.recording_toolchain  # By construction...
            self.recording_toolchain.stop_recording_toolchain_and_wait()

    def build(self):
        pass

    def build_config(self, config):
        config.setdefaults(
            "example",
            {
                "urlcamera": "/sme/path",
                "number_escrow": 9,
                "min_number_shares": 7,
                "retention_days": 10,
                ### "recordingdirectory": "/dir_rec-parent/dir_rec",
            },
        )

    def get_shared_secret_threshold(self):
        return int(self.config.get("example", "min_number_shares"))

    def get_url_camera(self):
        return self.config.get("example", "urlcamera")

    def build_settings(self, settings):
        settings.add_json_panel("Witness Angel", self.config, data=settings_json)

    def on_config_change(self, config, section, key, value):
        print("CONFIG CHANGE", section, key, value)

    def log_output(self, msg):
        console_output = self.root.ids.screen_manager.get_screen(
            "MainMenu"
        ).ids.kivy_console.ids.console_output
        console_output.add_text(
            msg
        )

    def on_start(self):
        import logging_tree
        logging_tree.printout()

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
        selected_authentication_device_uids = self.config["example"].get("selected_authentication_device_uids", "").split(",")

        available_authentication_device_uids = filesystem_key_storage_pool.list_imported_key_storage_uids()

        #Check integrity of escrow selection
        selected_authentication_device_uids = [
            x for x in selected_authentication_device_uids
            if UUID(x) in available_authentication_device_uids
        ]
        print("> Initial selected_authentication_device_uids", selected_authentication_device_uids)
        self.selected_authentication_device_uids = selected_authentication_device_uids

        # create container for tests
        # self.create_containers_for_test()

        # NOW only we refresh authentication devices panel
        self.get_detected_devices()  # FIXME rename

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

    def get_detected_container(self):
        containers_page_ids = self.root.ids.screen_manager.get_screen(
            "Container_management"
        ).ids

        container_names = filesystem_container_storage.list_container_names(as_sorted=True)

        if not container_names:
            container_display = Button(
                text="No container found",
                background_color=(1, 0, 0, 0.01),
                font_size="28sp",
                color=[0, 1, 0, 1],
            )
            containers_page_ids.table.clear_widgets()
            display_layout = BoxLayout(orientation="horizontal")
            display_layout.add_widget(container_display)
            containers_page_ids.table.add_widget(display_layout)
            return

        self.check_box_container_uuid_dict = {}
        self.btn_container_uuid_dict = {}
        containers_page_ids.table.clear_widgets()

        self.container_checkboxes = []

        for index, container_name in enumerate(container_names, start=1):

                my_check_box = CheckBox(active=False, size_hint=(0.2, 0.2))
                my_check_box._container_name = container_name
                #my_check_box.bind(active=self.check_box_container_checked)
                self.container_checkboxes.append(my_check_box)

                my_check_btn = Button(
                    text=" Container n° %s:  %s"
                    % (index, container_name),
                    size_hint=(0.8, 0.2),
                    background_color=(1, 1, 1, 0.01),
                    on_press=partial(self.show_container_details, container_name=container_name),
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
                layout = BoxLayout(
                    orientation="horizontal",
                    pos_hint={"center": 1, "top": 1},
                    padding=[140, 0],
                )
                layout.add_widget(my_check_box)
                layout.add_widget(my_check_btn)
                containers_page_ids.table.add_widget(layout)

        print("self.container_checkboxes", self.container_checkboxes)

    def get_selected_container_names(self):

        containers_page_ids = self.root.ids.screen_manager.get_screen(
            "Container_management"
        ).ids

        container_names = []

        for row in containers_page_ids.table.children:
            checkbox = row.children[-1]  # Order is reversed compared to adding
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
                " Key n° %s, keychain_uid: ...%s, type: %s, private_key:    %s\n"
                % (
                    index,
                    uuid_suffix,
                    keypair_identifier["key_type"],
                    private_key_present_str,
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

        Keys_page_ids.table.clear_widgets()  # FIXME naming

        key_storage_metadata = filesystem_key_storage_pool.list_imported_key_storage_metadata()

        if not key_storage_metadata:
            self.display_message_no_device_found()
            return

        self.chbx_lbls = {}  # FIXME: lbls ?
        self.btn_lbls = {}  # FIXME: lbls ?

        for (index, (device_uid, metadata)) in enumerate(sorted(key_storage_metadata.items()), start=1):
            uuid_suffix = str(device_uid).split("-")[-1]
            print("COMAPRING", str(device_uid), self.selected_authentication_device_uids)
            my_check_box = CheckBox(
                active=(str(device_uid) in self.selected_authentication_device_uids),
                size_hint=(0.2, 0.2),
                on_release=self.check_box_authentication_device_checked,
            )
            my_check_btn = Button(
                text=" key N°:  %s        User:  %s      |      UUID device:  %s " % (index, metadata["user"], uuid_suffix),
                size_hint=(0.8, 0.2),
                background_color=(1, 1, 1, 0.01),
                on_press=partial(self.info_keys_stored, device_uid=device_uid, user=metadata["user"])
            )
            self.chbx_lbls[my_check_box] = str(device_uid)
            self.btn_lbls[my_check_btn] = str(device_uid)
            layout = BoxLayout(
                orientation="horizontal",
                pos_hint={"center": 1, "top": 1},
                padding=[140, 0]
            )
            layout.add_widget(my_check_box)
            layout.add_widget(my_check_btn)
            Keys_page_ids.table.add_widget(layout)

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
        keys_page_ids.table.clear_widgets()
        Display_layout = BoxLayout(orientation="horizontal", padding=[140, 0])
        Display_layout.add_widget(devices_display)
        keys_page_ids.table.add_widget(Display_layout)

    def check_box_authentication_device_checked(self, check_box_checked):
        """
        Display the device checked
        """
        if self.chbx_lbls[check_box_checked] in self.selected_authentication_device_uids:
            self.selected_authentication_device_uids.remove(self.chbx_lbls[check_box_checked])
        else:
            self.selected_authentication_device_uids.append(self.chbx_lbls[check_box_checked])
        self.config["example"]["selected_authentication_device_uids"] = ",".join(self.selected_authentication_device_uids)
        self.config.write()
        print("self.selected_authentication_device_uids", self.selected_authentication_device_uids)

    def show_container_details(self, btn_selected, container_name):
        """
        Display the contents of container
        """
        try:
            container = filesystem_container_storage.load_container_from_storage(container_name)
            container_repr = pprint.pformat(container)[:1000]  # LIMIT else pygame.error: Width or height is too large
        except Exception as exc:
            container_repr = repr(exc)

        self.open_container_details_dialog(container_repr, info_container=container_name)

    def open_container_details_dialog(self, message, info_container):
        self.dialog = MDDialog(
            title=" %s" % info_container,
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
            title="Delete containers confirmation",
            text=message,
            size_hint=(0.8, 1),
            buttons=[
                MDFlatButton(
                    text="Confirm delete", on_release=partial(self.close_dialog_delete_container, container_names=container_names)
                ),
                MDFlatButton(text="Cancel", on_release=self.close_dialog),
            ],
        )
        self.dialog.open()

    def close_dialog_delete_container(self, obj, container_names):

        for container_name in container_names:
            filesystem_container_storage.delete_container(container_name)

        self.get_detected_container()  # FIXME rename
        self.dialog.dismiss()

    def open_dialog_decipher_container(self):

        container_names = self.get_selected_container_names()
        if not container_names:
            return

        message = "Are you sure you want to decrypt %s container(s)?" % len(container_names)

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
        self.dialog = MDDialog(
            title=" Decipher containers confirmation ",
            type="custom",
            content_cls=Content(),#entering the passphrase
            text=message,
            size_hint=(0.8, 1),
            buttons=[
                MDFlatButton(
                    text="Confirm decipher",
                    on_release=partial(self.close_dialog_decipher_container, container_names=container_names),
                ),
                MDFlatButton(text="Cancel", on_release=self.close_dialog),
            ],
        )

        self.dialog.open()

    def close_dialog_decipher_container(self, obj, container_names):

        input = self.dialog.content_cls.ids.pass_text.text

        for container_name in container_names:
            container = filesystem_container_storage.decrypt_container_from_storage(container_name)


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
        file_system_key_storage_pool = FilesystemKeyStoragePool(
            "D:/Users/manon/Documents/GitHub/witness-ward-client/src/GUI/.keys_storage_ward"
        )
        decryption_authorizations = request_decryption_authorizations(
            escrow_dependencies=escrow_dependencies,
            key_storage_pool=file_system_key_storage_pool,
            request_message="Need decryptions"
        )
        for container in containers:
            decrypt_data_from_container(container=container)
        self.dialog.dismiss()

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


WARD_GUIApp().run()
