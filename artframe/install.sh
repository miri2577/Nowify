#!/bin/bash
# Install the artframe picture-frame stack.
# Run as root on the Pi: sudo bash install.sh
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"

apt update
apt install -y --no-install-recommends fbi coreutils python3

install -d -m 0755 /opt/artframe
install -d -m 0755 /var/lib/artframe/images

install -m 0755 "$HERE/fetch.py"         /opt/artframe/fetch.py
install -m 0755 "$HERE/run-display.sh"   /opt/artframe/run-display.sh

install -m 0644 "$HERE/artframe-fetch.service"   /etc/systemd/system/
install -m 0644 "$HERE/artframe-fetch.timer"     /etc/systemd/system/
install -m 0644 "$HERE/artframe-display.service" /etc/systemd/system/

# Free tty1 from login prompt so fbi can own it
systemctl disable --now getty@tty1.service 2>/dev/null || true

systemctl daemon-reload
systemctl enable  artframe-fetch.timer
systemctl enable  artframe-display.service
systemctl start   artframe-fetch.service     # prime the image dir now
systemctl start   artframe-fetch.timer
systemctl start   artframe-display.service

echo
echo "Installed. The first batch of images is being downloaded now."
echo "Check:"
echo "  ls /var/lib/artframe/images/"
echo "  systemctl status artframe-fetch.service"
echo "  systemctl status artframe-display.service"
echo
echo "Orientation is landscape by default. To switch to portrait, edit"
echo "/etc/systemd/system/artframe-fetch.service and add under [Service]:"
echo "  Environment=ARTFRAME_ORIENT=portrait"
echo "then: systemctl daemon-reload && systemctl start artframe-fetch.service"
