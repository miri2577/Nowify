#!/bin/sh
# Display-loop for artframe. Waits until at least one JPG exists, then
# hands off to fbi on tty1. fbi rescans the argv each cycle, so to pick
# up newly-downloaded images we restart fbi periodically.
set -eu

DIR=/var/lib/artframe/images
INTERVAL=${ARTFRAME_INTERVAL:-60}   # seconds per image
RESTART_AFTER=${ARTFRAME_CYCLE:-1800}  # restart fbi every 30 min

# Wait for first image to appear (fetcher runs in parallel on boot)
i=0
while [ ! -d "$DIR" ] || [ -z "$(ls -1 "$DIR"/*.jpg 2>/dev/null | head -1)" ]; do
  i=$((i + 1))
  [ "$i" -gt 120 ] && exit 1   # give up after ~2 min
  sleep 1
done

while true; do
  # shellcheck disable=SC2086
  set -- $(ls -1 "$DIR"/*.jpg 2>/dev/null | shuf)
  [ "$#" -eq 0 ] && sleep 5 && continue
  timeout "$RESTART_AFTER" \
    fbi -T 1 -a -t "$INTERVAL" -noverbose --readahead --cachemem 32 "$@" \
    || true
done
