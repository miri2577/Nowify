#!/bin/bash
# Offline-only install — no network, no fetcher. Only the display loop.
# Drop your JPGs into /var/lib/artframe/images before (or after) this.
# Run as root on the Pi: sudo bash install-offline.sh
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"

apt update
apt install -y --no-install-recommends fbi coreutils

install -d -m 0755 /opt/artframe
install -d -m 0755 /var/lib/artframe/images

install -m 0755 "$HERE/run-display.sh"           /opt/artframe/run-display.sh
install -m 0644 "$HERE/artframe-display.service" /etc/systemd/system/

systemctl disable --now getty@tty1.service 2>/dev/null || true

systemctl daemon-reload
systemctl enable artframe-display.service
systemctl start  artframe-display.service

echo
echo "Installed (offline mode). Drop JPGs into:"
echo "  /var/lib/artframe/images/"
echo "They'll be picked up within the next restart cycle (default 30 min),"
echo "or force one: sudo systemctl restart artframe-display.service"
