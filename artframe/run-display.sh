#!/bin/sh
# mpv-based slideshow direct to DRM/KMS framebuffer.
set -eu

DIR=/var/lib/artframe/images
INTERVAL=${ARTFRAME_INTERVAL:-60}

i=0
while [ ! -d "$DIR" ] || [ -z "$(ls -1 "$DIR"/*.jpg 2>/dev/null | head -1)" ]; do
  i=$((i + 1))
  [ "$i" -gt 120 ] && exit 1
  sleep 1
done

# OSD positioning: bottom-centre, 60 px margin from edge.
# Explicit --script= guarantees the label loads regardless of mpv's
# packaging quirks around /etc/mpv/scripts/ auto-load.
exec mpv \
  --vo=drm \
  --image-display-duration="$INTERVAL" \
  --loop-playlist=inf \
  --shuffle \
  --no-input-default-bindings \
  --no-input-cursor \
  --quiet \
  --script=/etc/mpv/scripts/artframe-info.lua \
  "$DIR"/*.jpg
