"""
Quick and dirty singleton service launcher, to be replaced by a more solid solution like systemD.
"""

import socket
from pathlib import Path

import os
import sys
import datetime

from waguilib.service_control.osc_transport import get_osc_client
from kivy.utils import platform

this_dir = Path(__file__).resolve().parent

if __name__ == "__main__":
    osc_client = get_osc_client(to_app=False)

    sock = osc_client.sock
    if platform != 'win32' and sock.family == socket.AF_UNIX:
        address = osc_client.address
    else:
        address = (osc_client.address, osc_client.port)
    result = sock.connect_ex(address)

    dt = datetime.datetime.now()

    if result == 0:
        print(">>>>>>>>> %s - WANVR service already started and listening on its socket, aborting relaunch" % dt)
    else:
        print(">>>>>>>>> %s - WANVR service not found, relaunching it" % dt)
        os.system("%s %s" % (sys.executable, this_dir / "service.py"))
