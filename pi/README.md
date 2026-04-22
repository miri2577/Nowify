# Pi-side kiosk helper

A tiny loopback HTTP daemon so the Nowify browser frontend can trigger a
shutdown on the Raspberry Pi it runs on.

## What it does

- `POST http://127.0.0.1:8787/shutdown` → runs `shutdown -h now`.
- Bound to `127.0.0.1` — not reachable from the network, no auth needed.

Nowify calls this endpoint after 60 min in art mode with no music.

## Install

Copy this folder to the Pi and run:

```bash
sudo bash install.sh
```

This places the script at `/usr/local/bin/kiosk-control.py` and enables
the `kiosk-control.service` systemd unit.

## Chromium flag (required)

Nowify is served over `https://` from Netlify. Browsers block mixed
content (https → http), including to localhost. Add this flag to the
Chromium kiosk launch:

```
--unsafely-treat-insecure-origin-as-secure=http://127.0.0.1:8787
--user-data-dir=/root/.config/chromium
```

(`--user-data-dir` is required alongside the insecure-origin flag for
it to take effect.)

In DietPi the Chromium kiosk is started by
`/var/lib/dietpi/dietpi-software/installed/chromium-autostart.sh`
(wrapped via `/usr/local/bin/kiosk-wrapper.sh` in this setup). Append
the flag to the `chromium-browser` command line there.

## Uninstall

```bash
sudo systemctl disable --now kiosk-control.service
sudo rm /etc/systemd/system/kiosk-control.service
sudo rm /usr/local/bin/kiosk-control.py
sudo systemctl daemon-reload
```

## Smoke-test (without actually shutting down)

Stop the service and run the daemon by hand, then curl a wrong path:

```bash
sudo systemctl stop kiosk-control.service
/usr/local/bin/kiosk-control.py &
curl -i -X POST http://127.0.0.1:8787/nope   # → 404, OK
kill %1
sudo systemctl start kiosk-control.service
```
