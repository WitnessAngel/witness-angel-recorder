# Launch this script to workaround the fact that the SSH host key of the dev raspberry pi
# gets reset when it gets exported to image (so ssh w'ont allow connection anymore, for security)

# Remove local fingerprint of raspberry pi host (change IP if needed)
ssh-keygen -R 192.168.1.64

# Reconnect to trigger validation of host fingerprint again
ssh pi@192.168.1.64
