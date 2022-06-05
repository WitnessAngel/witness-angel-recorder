
# Allow SSH
ufw allow 22

# Allow NTP
ufw allow 123

# Activate firewall
ufw --force enable
