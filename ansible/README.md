# How to generate a Raspberry Pi image for Witness Angel Recorder


## Step 1 : Manual configuration of Raspberry Pi OS

Burn an image of Raspberry Pi OS ('bullseye' version) on an SDCARD

Insert the SDCARD in the Raspberry Pi, start it and connect it to the network (wired or wireless)

To get better performances and allow Kivy windowed mode, in raspi-config:

- Extend GPU memory to 256MB
- Enable FULL-KMS OpenGL support
- Enable Glamor

Also enable these Raspberry Pi interfaces:

- SSH
- SPI
- I2C

So that desktop icon works fine, in pcmanfm file explorer, menu "Edit -> Preferences -> General", check the Checkbox: "Don't ask options on launch executable file".

Connect an USB storage named "BigKey", where the exported image will be stored.

Parallel GCC compilation of big python modules might overflow memory, so it's better to increase the SWAP to 1GB and reboot: https://wpitchoune.net/tricks/raspberry_pi3_increase_swap_size.html


## Step 2 : Software provisioning with ansible

On a computer that has SSH access to the Raspberry Pi via ETHERNET, install ansible and sshpass. 

E.g. on Debian/Ubuntu : `sudo apt install ansible sshpass`

You then need to adjust the `hosts` file of this folder with the IP of the Raspberry Pi.

You might have to authorize the SSH hostkey of the Raspberry Pi (by attempting a direct connection via ssh), before ansible can connect to it too. If another hostkey was already known for this host, remove it with "ssh-keygen -R <raspberry-pi-ip>".

Then run `ansible-playbook -i hosts configure-raspberrypi-system.yml`

This will configure everything so that the Raspberry Pi can launch WA-Recorder sotware (both service and GUI processes).

Then REBOOT the raspberry pi, and test the good working of the system, especially regarding datetime handling : "date", "sudo hwclock", "timedatectl status" (set hardware clock to UTC if requested) etc.

All clocks must be well synchronized when Internet is available, and when not, the Raspberry Pi must update its time from hardware clock on boot (but the hardware clock shouldn't auto-update itself when system time is manually changed).

You can also check i2c busses and peripherals with "i2cdetect -l" and "i2cdetect -y 1".

When testing RTSP with VLC, note that it might bug (dropped frames and grey images) on high-resolution streams due to insufficient CPU power, but these streams should still work fine with the Recorder (which doesn't need to decode video). Installing hardware-accelerated VLC might help itsdisplay nonetheless.

Beware system image creation, turn OFF Bluetooth and WIFI, for security.

Then run `ansible-playbook -i hosts export-raspberrypi-system-image.yml`

This will cleanup sensitive information (hostkeys, wifi network...) and dump/shrink a whole system image to the USB storage.

You can then burn the generated image to another SDCARD, and boot on it.



SAY COMPATIBILITY WITH DS1307 and ds3231 too  <<<<<<<<<
