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
exec "$CHROME" \
  --unsafely-treat-insecure-origin-as-secure=http://127.0.0.1:8787 \
  "$@"
