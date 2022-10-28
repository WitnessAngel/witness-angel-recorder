
# Disable firewall first
ufw --force disable

# Remove all existing rules
ufw --force reset

# Allow SSH
ufw allow 22

# Allow NTP
ufw allow 123

# Allow VNC
ufw allow 5900

# Activate firewall
ufw --force enable
