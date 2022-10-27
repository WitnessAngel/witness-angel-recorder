#!/bin/bash
# Download and link to python3 this DFRobot driver, which is not pip-installable...

mkdir -p ~/installers/
cd ~/installers/
git clone https://github.com/DFRobot/DFRobot_RPi_Display_V2 dfrobot_rpi_display_v2_driver
absdir=`readlink -f ~/installers/dfrobot_rpi_display_v2_driver/`
echo "$absdir" > ~/.venv/lib/python3.9/site-packages/dfrobot_rpi_display_v2_driver.pth
