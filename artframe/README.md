# Artframe — a minimal digital picture frame

Pi-Zero-sized Chromium-free picture frame. Pulls artworks from the Art
Institute of Chicago public API and cycles them fullscreen on the
Linux framebuffer via `fbi`. No X, no browser.

**RAM footprint**: ~30 MB at rest (fbi + python + kernel buffers),
fits comfortably on a 512 MB Pi Zero 1 or Zero 2 W.

## What you get

- Fullscreen slideshow on `tty1`, 60 s per image (configurable).
- Rotating local cache of up to 40 JPGs in `/var/lib/artframe/images/`.
- Hourly refill from the AIC API (random page, orientation-filtered).
- Automatic restart of fbi every 30 min so newly-downloaded images
  get picked up without a reboot.

## Requirements

- Raspberry Pi OS Lite / DietPi / any Debian-family, no X needed.
- HDMI display that accepts your configured resolution (set in
  `/boot/config.txt`, e.g. `hdmi_group=1`, `hdmi_mode=16` for 1080p).
- Network (any, wifi or ethernet).

## Install

Clone or wget the `artframe/` folder onto the Pi, then:

```bash
sudo bash install.sh
```

That installs `fbi`, drops the scripts into `/opt/artframe/`, the
systemd units into `/etc/systemd/system/`, stops the login prompt on
tty1, primes the image cache, and starts the slideshow.

## Quick-and-dirty one-shot install from GitHub

```bash
mkdir -p /tmp/artframe && cd /tmp/artframe
BASE=https://raw.githubusercontent.com/miri2577/Nowify/main/artframe
for f in fetch.py run-display.sh install.sh \
         artframe-fetch.service artframe-fetch.timer \
         artframe-display.service; do
  wget -q "$BASE/$f"
done
sudo bash install.sh
```

## Configure

All knobs are environment variables on the respective systemd unit.
Edit the unit file and add lines under `[Service]`:

| Variable | Default | Where | What |
|---|---|---|---|
| `ARTFRAME_ORIENT` | `landscape` | fetch.service | `landscape`, `portrait`, or `any` |
| `ARTFRAME_INTERVAL` | `60` | display.service | seconds per image |
| `ARTFRAME_CYCLE` | `1800` | display.service | seconds before fbi is restarted |

After editing: `sudo systemctl daemon-reload && sudo systemctl restart <unit>`.

## Display rotation (portrait installation)

For a vertical display, add to `/boot/config.txt`:

```
display_rotate=1   # 1=90°, 2=180°, 3=270°
```

…and set `ARTFRAME_ORIENT=portrait` on the fetch service so you get
tall artworks.

## Troubleshooting

- **Black screen**: `systemctl status artframe-display.service`. If it
  says "no images yet", check `ls /var/lib/artframe/images/` and
  `journalctl -u artframe-fetch.service` for network errors.
- **Login prompt on tty1**: `sudo systemctl disable --now getty@tty1`.
  DietPi's autologin may also need disabling via `dietpi-autostart`.
- **Slow to flip**: Pi Zero 1 is CPU-bound when decoding 1920 px
  JPGs. Lower `WIDTH` in `fetch.py` to `1280` and redownload.

## Uninstall

```bash
sudo systemctl disable --now artframe-display.service
sudo systemctl disable --now artframe-fetch.timer
sudo rm /etc/systemd/system/artframe-{fetch,display}.service
sudo rm /etc/systemd/system/artframe-fetch.timer
sudo rm -rf /opt/artframe /var/lib/artframe
sudo systemctl daemon-reload
sudo systemctl enable --now getty@tty1.service   # restore login prompt
```
