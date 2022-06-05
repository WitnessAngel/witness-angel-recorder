
if ! compgen -G "/etc/ssh/*_host_*" > /dev/null; then
    # We regenerate hostkeys, probably cleared as part of generic system image building
    /usr/bin/ssh-keygen -A > /tmp/custom_boot_checkups.log 2>&1
    /usr/sbin/service ssh restart >> /tmp/custom_boot_checkups.log 2>&1
fi
