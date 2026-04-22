#!/bin/bash
# Install the Nowify kiosk helper on the Pi.
# Run as root: sudo bash install.sh
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"

install -m 0755 "$HERE/kiosk-control.py" /usr/local/bin/kiosk-control.py
install -m 0644 "$HERE/kiosk-control.service" /etc/systemd/system/kiosk-control.service

systemctl daemon-reload
systemctl enable --now kiosk-control.service

echo
echo "Installed. Status:"
systemctl --no-pager status kiosk-control.service | head -n 10
echo
echo "Test: curl -X POST http://127.0.0.1:8787/shutdown  (will power down!)"
echo
echo "IMPORTANT: The Chromium kiosk must be started with the flag"
echo "  --unsafely-treat-insecure-origin-as-secure=http://127.0.0.1:8787"
echo "so the Netlify-served (https) page is allowed to POST to the http loopback."
echo "See pi/README.md for details."
