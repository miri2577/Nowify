#!/bin/sh
LOG=/tmp/kiosk.log
{
  echo "=== $(date) wrapper started ==="
  echo "DISPLAY=$DISPLAY XAUTHORITY=$XAUTHORITY USER=$(whoami)"
  echo "args=$*"
} >> "$LOG" 2>&1

(
  while true; do
    echo "$(date) starting unclutter" >> "$LOG"
    unclutter -idle 1 -root 2>>"$LOG"
    echo "$(date) unclutter exited rc=$?" >> "$LOG"
    sleep 2
  done
) &

echo "$(date) backgrounded watchdog PID=$!" >> "$LOG"

CHROME="$1"
shift
# Flags:
#   --unsafely-treat-insecure-origin-as-secure: Nowify (https) darf das
#       lokale Shutdown-Endpoint (http://127.0.0.1:8787) ansprechen
#   --disable-web-security: WikiArt-API erlaubt kein CORS — der Artframe
#       iframe braucht das, sonst werden alle fetch()-Calls geblockt.
#       Erfordert --user-data-dir damit Chromium das Flag akzeptiert.
exec "$CHROME" \
  --unsafely-treat-insecure-origin-as-secure=http://127.0.0.1:8787 \
  --disable-web-security \
  --user-data-dir=/tmp/chromium-kiosk \
  "$@"
