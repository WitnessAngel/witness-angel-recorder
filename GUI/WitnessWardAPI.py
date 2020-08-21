from kivy.uix.screenmanager import ScreenManager
from kivymd.uix.screen import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ListProperty
from kivy.uix.button import Button
from kivymd.app import MDApp
from kivymd.theming import ThemableBehavior
from kivymd.uix.list import OneLineIconListItem, MDList
from kivy.uix.checkbox import CheckBox
from pathlib import Path
from kivymd.uix.button import  MDFlatButton
from kivymd.uix.dialog import MDDialog
from pathlib import PurePath


from key_device import list_available_key_devices
from wacryptolib.key_storage import FilesystemKeyStorage
from wacryptolib.utilities import load_from_json_file, dump_to_json_file





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
        pass

class MainWindow(Screen):
    def __init__(self, **kwargs):
        self.title = "Witness Angel - WardProject"
        super(MainWindow, self).__init__(**kwargs)


class SecondWindow(Screen):
    pass


class ThirdWindow(Screen):
    pass


class FourthWindow(Screen):
    pass


class WindowManager(ScreenManager):
    pass


class MyMainApp(MDApp):
    def __init__(self, **kwargs):
        self.title = "Witness Angel - WardProject"
        super(MyMainApp, self).__init__(**kwargs)

    def build(self):
        pass
    def log_output(self, msg):
        self._console_output = self.root.get_screen("MainMenu").ids.kivy_console.ids.console_output
        #to simulate log
        for i in range(100):
            self._console_output.add_text(
                msg + ' ' + str(i + 1) + ' ' + msg + msg + ' ' + str(i + 1) + ' ' + msg + msg + ' ' + str(
                    i + 1) + ' ' + msg)

    def draw_menu(self, ecran):
        icons_item = {
            "home": "Main page",
            "key": "Keys management",
            "lock": "Container management",
            "settings-outline": "Settings"

        }
        self.root.get_screen(ecran).ids.content_drawer.ids.md_list.clear_widgets()
        for icon_name in icons_item.keys():
            self.root.get_screen(ecran).ids.content_drawer.ids.md_list.add_widget(
                ItemDrawer(icon=icon_name, text=icons_item[icon_name])
            )

    def on_start(self):
        self.draw_menu("MainMenu")
        self.log_output("Ceci est un message de log ")

    def navigation_draw_menu(self, item_drawer):


        if item_drawer.text == "Main page":
            destination = "MainMenu"

        elif item_drawer.text == "Keys management":
            destination = "Keys_management"
            self.draw_menu("Keys_management")
            self.get_detected_devices()

        elif item_drawer.text == "Container management":
            self.draw_menu("Container_management")
            destination = "Container_management"
            self.get_detected_container()

        elif item_drawer.text == "Settings":
            self.draw_menu("Settings")
            destination = "Settings"

        self.root.current= destination


    def get_list_keys(self, path):
        """
        list keys from key device (USB)
        """
        key_pairs_dir = Path(path).joinpath(".key_storage", "crypto_keys")
        object_FilesystemKeyStorage = FilesystemKeyStorage(key_pairs_dir)
        return object_FilesystemKeyStorage.list_keys()

    def info_keys_stored(self, btn_selected):

        """
        display the information of the keys stored in the selected usb

        """

        # get num of key device and user info
        info_usb_user = btn_selected.text.split('|      UUID device:')[0]
        #search for files that match with the selected device_uuid
        fichiers = [f for f in Path(r".keys_storage_ward").iterdir() if str(PurePath(f).name) ==str(self.btn_lbls[btn_selected])]

        for usb_dir in fichiers:
            object_FilesystemKeyStorage = FilesystemKeyStorage(usb_dir)
            public_key_list=object_FilesystemKeyStorage.list_keys()
            message = ""
            private_key_present = ""
            for index, key in enumerate(public_key_list):
                if key["private_key_present"]:
                    private_key_present="X"
                message += " key  N°:  %s        keychain_uid:  %s      type:    %s    private_key:    %s\n" % (
                str(index + 1), (str(key["keychain_uid"]).split('-'))[0],str(key["key_type"]),private_key_present)
            self.open_dialog_display_keys_in_key_device(message, info_usb_user)

    def open_dialog_display_keys_in_key_device(self, message ,info_usb_user):

        self.dialog = MDDialog(title="%s" %info_usb_user,
                               text=message, size_hint=(0.8, 1),
                               buttons=[MDFlatButton(text='Close', on_release=self.close_dialog)]
                               )
        self.dialog.open()

    def close_dialog(self, obj):
        self.dialog.dismiss()


    def check_box_key_device_checked(self, check_box_checked):
        print(self.chbx_lbls[check_box_checked])

    def radio_box_container_checked(self, radio_box_checked,value):
        print(self.chbx_box_dict[radio_box_checked])
        for chbx in self.chbx_box_dict:
            if chbx.active:
                self.root.get_screen("Container_management").ids.delete.disabled = False
                self.root.get_screen("Container_management").ids.decipher.disabled = False
                break
            else:
                self.root.get_screen("Container_management").ids.delete.disabled = True
                self.root.get_screen("Container_management").ids.decipher.disabled = True



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
                file_metadata=Path(".keys_storage_ward").joinpath(device_dir, ".metadata.json")
                metadata_file_path=Path(key_device["path"]).joinpath(".key_storage", ".metadata.json")
                if not Path(file_metadata.parent).exists():
                    Path(file_metadata.parent).mkdir()
                metadata = load_from_json_file(metadata_file_path)
                dump_to_json_file(file_metadata, metadata)
                dst = Path(".keys_storage_ward").joinpath(device_dir)
                key_pairs_dir = Path(key_device["path"]).joinpath(".key_storage", "crypto_keys")
                #copy contents keys of key_pairs_dir to dst(copy key storage to <KEYS_ROOT>/<device_uid>)
                self.Copy_list_keys(key_pairs_dir, dst)
        # update the display of key_device saved in the local folder .keys_storage_ward
        self.get_detected_devices()


    def Copy_list_keys(self, src, dst):
        """
        copy the keys of a src directory and put it in the a dst directory

        """
        object_Filesystem_destination = FilesystemKeyStorage(dst)
        list_keys_destination = object_Filesystem_destination.list_keys()
        object_Filesystem_source = FilesystemKeyStorage(src)
        list_keys_source=object_Filesystem_source.list_keys()

        for key in list_keys_source:
            if key not in list_keys_destination:
                public_key=object_Filesystem_source.get_public_key(keychain_uid=key['keychain_uid'] , key_type=key['key_type'] )
                if key['private_key_present']:
                    private_key=object_Filesystem_source.get_private_key(keychain_uid=key['keychain_uid'], key_type=key['key_type'])
                object_Filesystem_destination.set_keys(
                    keychain_uid=key['keychain_uid'],
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
        if not Path(r".keys_storage_ward").exists():
            # "no key found"
            self.my_check_box_label = Button(
                text=" no key found ",
                background_color=(1, 0, 0, .01), font_size="28sp", color=[0, 1, 0, 1] )
            self.root.get_screen("Keys_management").ids.table.clear_widgets()
            self.layout = BoxLayout(orientation='horizontal', padding=[140, 0])
            self.layout.add_widget(self.my_check_box_label)
            self.root.get_screen("Keys_management").ids.table.add_widget(self.layout)
        else:
            result=[f for f in Path(r".keys_storage_ward").iterdir() ]
            index=0
            self.root.get_screen("Keys_management").ids.table.clear_widgets()
            self.chbx_lbls = {}
            self.btn_lbls = {}
            for dir_key_sorage in result:
                file_metadata = Path(dir_key_sorage).joinpath(".metadata.json")
                metadata = load_from_json_file(file_metadata)
                b=str(metadata["device_uid"])
                b = b.split('-')
                b = b[0].lstrip()
                UUID1 = b.rstrip()
                self.my_check_box = CheckBox(active=False, size_hint=(0.2, 0.2), on_release=self.check_box_key_device_checked)
                self.my_check_btn = Button(
                    text=" key N°:  %s        User:  %s      |      UUID device:  %s " % (
                    (str(index + 1)), str(metadata["user"]), UUID1), size_hint=(0.8, 0.2),
                    background_color=(1, 1, 1, .01), on_press=self.info_keys_stored)
                self.chbx_lbls[self.my_check_box] = str(metadata["device_uid"])
                self.btn_lbls[self.my_check_btn] = str(metadata["device_uid"])
                self.layout = BoxLayout(orientation='horizontal', pos_hint={"center": 1, "top": 1}, padding=[140, 10], spacing=[0, 10])
                self.layout.add_widget(self.my_check_box)
                self.layout.add_widget(self.my_check_btn)
                self.root.get_screen("Keys_management").ids.table.add_widget(self.layout)
                index+=1




    def get_detected_container(self):
        """

        """
        if not Path(r".keys_storage_ward").exists():
            # "no container found"
            self.my_check_box_label = Button(
                text=" no container found ",
                background_color=(1, 0, 0, .01), font_size="28sp", color=[0, 1, 0, 1] )
            self.root.get_screen("Container_management").ids.table.clear_widgets()
            self.layout = BoxLayout(orientation='horizontal')
            self.layout.add_widget(self.my_check_box_label)
            self.root.get_screen("Container_management").ids.table.add_widget(self.layout)
        else:
            result=[f for f in Path(r".keys_storage_ward").iterdir() ]
            index=0
            self.root.get_screen("Container_management").ids.table.clear_widgets()
            self.chbx_box_dict = {}
            self.chbx_btn_dict = {}
            for dir_key_sorage in result:
                file_metadata = Path(dir_key_sorage).joinpath(".metadata.json")
                metadata = load_from_json_file(file_metadata)
                b=str(metadata["device_uid"])
                b = b.split('-')
                b = b[0].lstrip()
                UUID1 = b.rstrip()
                self.my_check_box = CheckBox(active=False, size_hint=(0.2, 0.2))
                self.my_check_box.bind(active=self.radio_box_container_checked)
                self.my_check_btn = Button(text=" Container N°:  %s        %s      |      ID container :  %s " % ((str(index + 1)), "", UUID1), size_hint=(0.8, 0.2), background_color=(1, 1, 1, .01), on_press=self.info_container_stored)
                self.chbx_box_dict[self.my_check_box] = str(metadata["device_uid"])
                self.chbx_btn_dict[self.my_check_btn] = str(metadata["device_uid"])
                self.layout = BoxLayout(orientation='horizontal', pos_hint={"center": 1, "top": 1},padding=[140, 0])
                self.layout.add_widget(self.my_check_box)
                self.layout.add_widget(self.my_check_btn)
                self.root.get_screen("Container_management").ids.table.add_widget(self.layout)
                index+=1






    def info_container_stored(self, btn_selected):

        """

        """

        info_container_and_user = btn_selected.text.split('|      ID container :')[0]

        fichiers = [f for f in Path(r".keys_storage_ward").iterdir() if PurePath(f).name==self.chbx_btn_dict[btn_selected]]

        for usb_dir in fichiers:
            # get num of key device

            message = r" container composition"
            self.open_dialog_container(message, info_container_and_user)

    def open_dialog_container(self, message, info_container_and_user):
        self.dialog = MDDialog(title=" %s" %info_container_and_user ,
                               text=message, size_hint=(0.8, 1),
                               buttons=[MDFlatButton(text='Close', on_release=self.close_dialog)]
                               )
        self.dialog.open()


    def open_dialog_delete_container(self):
        count_container_checked = 0
        for chbx in self.chbx_box_dict:
            if chbx.active:
                count_container_checked+=1


        if count_container_checked==1:
            messge=" do you want to delete these container?"
        elif count_container_checked > 1:
            messge = " do you want to delete these %d containers" % count_container_checked
        self.dialog = MDDialog(title=" Delete containers confirmation " ,
                               text=messge, size_hint=(0.8, 1),
                               buttons=[MDFlatButton(text='Confirm delete', on_release=self.close_dialog_delete_container),MDFlatButton(text='Cancel', on_release=self.close_dialog)]
                               )
        self.dialog.open()

    def close_dialog_delete_container(self, obj):
        for chbx in self.chbx_box_dict:
            if chbx.active:
                print("delete container | with ID_container %s",self.chbx_box_dict[chbx])
        self.dialog.dismiss()

    def open_dialog_decipher_container(self):
        count_container_checked = 0
        for chbx in self.chbx_box_dict:
            if chbx.active:
                count_container_checked+=1

        if count_container_checked==1:
            messge=" do you want to decipher these container?"
        elif count_container_checked > 1:
            messge = " do you want to decipher these %d containers" % count_container_checked
        self.dialog = MDDialog(title=" Decipher containers confirmation " ,
                               text=messge, size_hint=(0.8, 1),
                               buttons=[MDFlatButton(text='Confirm  decipher', on_release=self.close_dialog_decipher_container),MDFlatButton(text='Cancel', on_release=self.close_dialog)]
                               )
        self.dialog.open()
    def close_dialog_decipher_container(self, obj):
        for chbx in self.chbx_box_dict:
            if chbx.active:
                print("decipher container | with ID_container %s",self.chbx_box_dict[chbx])
        self.dialog.dismiss()

if __name__ == "__main__":
    MyMainApp().run()
