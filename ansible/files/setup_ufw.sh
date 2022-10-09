
# Allow SSH
ufw allow 22

# Allow NTP
ufw allow 123

# Allow VNC
ufw allow 5900599

# Activate firewall
ufw --force enable
