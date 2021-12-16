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
    dt = datetime.datetime.now()

    osc_client = get_osc_client(to_app=False)

    sock = osc_client.sock
    if platform != 'win' and sock.family == getattr(socket, "AF_UNIX", None):

        address = osc_client.address
        result = sock.connect(address)

        if result == 0:
            print(">>>>>>>>> %s - WANVR service already started and listening on its socket, aborting relaunch" % dt)
            sys.exit()

    # INET sockets ALWAYS "connect" when in UDP mode, so we can't know if a server already listens
    # but we don't care since then the service will crash at boot when attempting to reuse port
    print(">>>>>>>>> %s - WANVR service not detectable, relaunching it" % dt)
    os.system("%s %s" % (sys.executable, this_dir / "service.py"))
