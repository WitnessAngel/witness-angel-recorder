#!/bin/bash
mkdir -p ~/installers/

curl https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/master/i2smic.py > ~/installers/i2smic_install.py

echo -e "rm /etc/modules-load.d/snd-i2smic-rpi.conf\nrm /etc/modprobe.d/snd-i2smic-rpi.conf\necho 'To enable i2smic manually: sudo modprobe snd-i2smic-rpi rpi_platform_generation=<0 for pizero, 1 for Pi 2/3, or 2 for Pi 4>'" > ~/installers/i2smic_disable_on_boot.sh
