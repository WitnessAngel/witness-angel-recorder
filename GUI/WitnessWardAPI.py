from kivy.uix.screenmanager import ScreenManager
from kivy.factory import Factory
from kivy.uix.image import Image
from kivymd.uix.list import IRightBodyTouch, ILeftBody
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.screen import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, ListProperty
from kivymd.uix.label import Label
from kivy.uix.button import Button
from kivymd.app import MDApp
from kivymd.theming import ThemableBehavior
from kivymd.uix.list import OneLineIconListItem, MDList
from kivy.uix.checkbox import CheckBox
from pathlib import Path

from key_device import (
    list_available_key_devices,
    initialize_key_device,
    _get_metadata_file_path,
)

from wacryptolib.utilities import load_from_json_file, dump_to_json_file


from kivymd.uix.datatables import MDDataTable
from kivy.metrics import dp


class ContentNavigationDrawer(BoxLayout):
    pass


class ItemDrawer(OneLineIconListItem):
    icon = StringProperty()
    text_color = ListProperty((0, 0, 0, 1))


class DrawerList(ThemableBehavior, MDList):
    def set_color_item(self, instance_item):
        """Called when tap on a menu item."""

        # Set the color of the icon and text for the menu item.
        for item in self.children:
            if item.text_color == self.theme_cls.primary_color:
                item.text_color = self.theme_cls.text_color
                break
        instance_item.text_color = self.theme_cls.primary_color


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
            # item_drawer.color à rechercher
        elif item_drawer.text == "Keys management":
            destination = "Keys_management"
            self.draw_menu("Keys_management")
            self.get_detected_devices()
        elif item_drawer.text == "Container management":
            self.draw_menu("Container_management")
            destination = "Container_management"
        elif item_drawer.text == "Settings":
            self.draw_menu("Settings")
            destination = "Settings"

        return destination

    def fct1(self, event):
        print("ok 1")
    def fct2(self, event):
        print("ok 2")
    def import_keys(self):
        """

       quand on clique sur “import keys”, ça doit boucler sur les “key_devices” présents,
        et pour ceux qui sont initialiser, copier (avec différents KeyStorage pour chaque dossier)
        leur contenu dans un dossier <KEYS_ROOT>/<device_uid>/  (en reprenant le device_uid du metadata.json),
        en copiant y compris ledit fichier metadata.json
        (pour l’instant mettons KEYS_ROOT en dur à “~/.keys_storage_ward/”
        en crééant ce dossier s’il n’existe pas, tout cela sera normalisé avec common_config.py du witness-angel-client)
        le GUI doit rafraîchir automatiquement à chaque retour sur ce Screen : il boucle alors sur les dossiers de KEYS_ROOT/,
        et lit leur metadata.json, pour afficher dans l’interface leur USER et le début de leur UUID
        Quand on clique sur une clef, le popup charge la liste des clefs en utilisant le list_keys() d’un “key storage”
        initialisé sur ce dossier, et affiche le début de leur uid, leur type (rsa_oaep…),
        et une croix suivant que la clef privée correspondante existe aussi

        """
        from wacryptolib.key_storage import FilesystemKeyStorage
        list_devices = list_available_key_devices()
        for index, key_device in enumerate(list_devices):
            if str(key_device["is_initialized"]) == "True":


                if not Path(".keys_storage_ward").exists():
                    Path(".keys_storage_ward").mkdir()
                device_dir = str(key_device["device_uid"])
                #KEYS_ROOT = Path(".keys_storage_ward").joinpath(device_dir)
                file_metadata=Path(".keys_storage_ward").joinpath(device_dir, ".metadata.json")
                metadata_file_path=Path(key_device["path"]).joinpath(".key_storage", ".metadata.json")
                if not Path(file_metadata.parent).exists():
                    Path(file_metadata.parent).mkdir()
                metadata = load_from_json_file(metadata_file_path)
                print(metadata)
                dump_to_json_file(file_metadata, metadata)

                #list public keys in device
                # key_pairs_dir=Path(key_device["path"]).joinpath("private_key")
                metadata_file = _get_metadata_file_path(key_device)
                metadata_folder = metadata_file.parent
                key_pairs_dir = metadata_folder.joinpath("private_key")
                object_FilesystemKeyStorage = FilesystemKeyStorage(key_pairs_dir)
                public_key_list = object_FilesystemKeyStorage.list_keys()
                print(public_key_list)

                #copy key storage to <KEYS_ROOT>/<device_uid>
                dst = Path(".keys_storage_ward").joinpath(device_dir)
                #copy contents of key_pairs_dir to dst
                self.copytree(key_pairs_dir, dst)

    def copytree( self,src, dst, symlinks=False, ignore=None):

        """
        This is an improved version of shutil.copytree which allows writing to
        existing folders and does not overwrite existing files .
        """
        import shutil
        import os

        names = os.listdir(src)
        if ignore is not None:
            ignored_names = ignore(src, names)
        else:
            ignored_names = set()

        if not os.path.exists(dst):
            os.makedirs(dst)
            shutil.copystat(src, dst)
        errors = []
        for name in names:
            if name in ignored_names:
                continue
            srcname = os.path.join(src, name)
            dstname = os.path.join(dst, name)

            try:
                if symlinks and os.path.islink(srcname):
                    linkto = os.readlink(srcname)
                    os.symlink(linkto, dstname)
                elif os.path.isdir(srcname):
                    self.copytree(srcname, dstname, symlinks, ignore)
                else:
                    shutil.copy2(srcname, dstname)

            except (IOError, os.error) as why:
                errors.append((srcname, dstname, str(why)))

            # catch the Error from the recursive copytree so that we can
            # continue with other files
            except BaseException as err:
                errors.extend(err.args[0])
        try:
            shutil.copystat(src, dst)
        except WindowsError:
            # can't copy file access times on Windows
            pass
        except OSError as why:
            errors.extend((src, dst, str(why)))
        if errors:
            raise BaseException(errors)


    def get_detected_devices(self):
        list_devices = list_available_key_devices()
        for index, usb in enumerate(list_devices):
            self.my_check_box = CheckBox(active=False, size_hint= (0.2, 0.2), on_release=self.fct1)
            self.my_check_box_label = Button(
                text=" key N°:  %s        Path:  %s       |      Label:  %s "  %((str(index+1)) , (str(usb["path"])), (str(usb["label"]))), size_hint= (0.8, 0.2), background_color= (1, 1, 1, .01), on_press=self.fct2)
                #text=" [color=#FFFFFF][b]Path:[/b] %s[/color]" % (str(usb["path"])))
            self.root.get_screen("Keys_management").ids.table.clear_widgets()
            self.layout = BoxLayout(orientation='horizontal', pos_hint={"center": 1, "top": 1},padding=[140,0])
            self.layout.add_widget(self.my_check_box)
            self.layout.add_widget(self.my_check_box_label)
            self.root.get_screen("Keys_management").ids.table.add_widget(self.layout)


    def get_info_key_selected(self, linelist):
        list_devices = list_available_key_devices()
        for i in self.list.ids.scroll.children:
            i.bg_color = [0.1372, 0.2862, 0.5294, 1]
        linelist.bg_color = [0.6, 0.6, 0.6, 1]

        self.l = Label(text="")
        self.alertMessage = Label(text="")
        self.list.ids.labelInfoUsb1.clear_widgets()
        self.list.ids.label_alert.clear_widgets()
        self.list.ids.labelInfoUsb1.add_widget(self.l)
        self.list.ids.label_alert.add_widget(self.alertMessage)
        for index, key_device in enumerate(list_devices):
            if linelist.text == "[color=#FFFFFF][b]Path:[/b] " + str(key_device["path"]) + "[/color]":
                self.key_device_selected = key_device
                if str(key_device["is_initialized"]) == "True":

                    self.l = Label(
                        text="USB information : Size %s   |   Fst :%s | and it is initialized"
                             % (str(key_device["size"]), str(key_device["format"]))
                    )
                    self.alertMessage = Label(
                        text="You have to format the key or manually delete the private folder"
                    )
                    meta = load_from_json_file(
                        key_device["path"] + "\.key_storage\.metadata.json"
                    )

                else:
                    self.l = Label(
                        text="USB information : Size %s   |   Fst :%s | and it is not initialized"
                             % (str(key_device["size"]), str(key_device["format"]))
                    )
                    self.alertMessage = Label(
                        text="Please fill in the username and passphrase to initialize the usb key"
                    )

                self.list.ids.labelInfoUsb1.add_widget(self.l)
                self.list.ids.label_alert.add_widget(self.alertMessage)


if __name__ == "__main__":
    MyMainApp().run()
