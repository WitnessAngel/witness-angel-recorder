#!/bin/bash
#if [[ -f /usr/local/lib/libbcm2835.a ]] ; then
#    echo "libbcm2835 file exists, exiting"
#    exit
#fi
wget http://www.airspayce.com/mikem/bcm2835/bcm2835-1.60.tar.gz
tar zxvf bcm2835-1.60.tar.gz
cd bcm2835-1.60/
sudo ./configure
sudo make
sudo make check
sudo make install
