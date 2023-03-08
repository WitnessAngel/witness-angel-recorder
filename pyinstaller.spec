# -*- mode: python ; coding: utf-8 -*-

import re, sys, os
from pathlib import Path

from kivymd import hooks_path as kivymd_hooks_path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

import PyInstaller.config
PyInstaller.config.CONF['distpath'] = "bin"  # Make it same as buildozer output path

pyproject_data = Path("pyproject.toml").read_text()
version = re.search(r'''version = ['"](.*)['"]''', pyproject_data).group(1)
assert version, version

root_dir = os.path.abspath(os.getcwd())
assert os.path.isdir(os.path.join(root_dir, "warecorder"))

sys.path.append(root_dir)  # To find WARECORDER package

''' Recent versions of pyinstaller have trouble importing warecorder - to be investigated
print("\n\n>>>>>>>>>>sys.path")
from pprint import pprint
pprint(sys.path)

import warecorder
print("\n\n>>>> warecorder", warecorder)
'''

hiddenimports = collect_submodules("warecorder") + collect_submodules("wacomponents") + collect_submodules("plyer")
#print("\n\n>>>>>>>>>>hiddenimports", hiddenimports)

app_name = "witness_angel_recorder_%s" % version.replace(".","-")

extra_exe_params= []
if sys.platform.startswith("win32"):
    from kivy_deps import sdl2, glew
    extra_exe_params = [Tree(p) for p in (sdl2.dep_bins + glew.dep_bins)]

USE_CONSOLE = True  # Change this if needed, to debug

main_script = os.path.join(root_dir, 'main.py')


a = Analysis([main_script],
             pathex=['.'],
             binaries=[],
             datas=collect_data_files("warecorder") + collect_data_files("wacomponents"),
             hiddenimports=hiddenimports,
             hookspath=[kivymd_hooks_path],
             runtime_hooks=[],
             excludes=['_tkinter', 'Tkinter', "enchant", "twisted", "cv2", "numpy", "pygame"],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=None,
             noarchive=True)

pyz = PYZ(a.pure, a.zipped_data,
             cipher=None)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          *extra_exe_params,
          #exclude_binaries=True,
          name=app_name,
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          runtime_tmpdir=None,
          console=USE_CONSOLE,
          icon='assets/windows_icon_authenticator_64x64.ico')

if sys.platform.startswith("darwin"):
    app = BUNDLE(exe,
             name=app_name+".app",
             icon=None,
             bundle_identifier=None)

''' UNUSED - FOR DIRECTORY BUILD ONLY
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               *extra_exe_params,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='witness_angel_authenticator')
'''
