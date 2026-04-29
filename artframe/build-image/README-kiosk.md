# Build a flashable Pi-4 Kiosk image

Produces a single `.img` file that boots into a Chromium-Kiosk pointing
at deine Nowify-Netlify-URL. Nowify zeigt im Idle-Modus (kein Spotify /
KRP) den Artframe (WikiArt-Browser) per iframe. FLIRC-Stick steuert die
Artframe-Navigation als USB-Keyboard.

## One-time WSL2 setup

```powershell
wsl --install -d Ubuntu-22.04
```

In Ubuntu:

```bash
sudo apt update
sudo apt install -y qemu-user-static binfmt-support xz-utils curl \
                    parted dosfstools python3 git openssl
sudo update-binfmts --enable qemu-aarch64
```

## Build

```bash
git clone https://github.com/miri2577/Nowify.git ~/Nowify
cd ~/Nowify/artframe/build-image

NOWIFY_URL="https://deine-netlify-url.netlify.app" \
WIFI_SSID="DeinWLAN" \
WIFI_PSK="DeinPasswort" \
WIFI_COUNTRY="DE" \
ROOT_PW="artframe" \
bash build-kiosk.sh
```

Erster Lauf zieht ~500 MB (RasPiOS Lite arm64) und installiert
Chromium + X im Chroot — dauert ca. **15-25 Minuten**. Output:
`./artframe-kiosk-arm64.img` (~5 GB).

### Knobs

| Var | Default | Meaning |
|---|---|---|
| `NOWIFY_URL` | **required** | Netlify-URL für Nowify |
| `WIFI_SSID` | **required** | WLAN-SSID |
| `WIFI_PSK` | **required** | WLAN-Passwort |
| `WIFI_COUNTRY` | `DE` | 2-Buchstaben-Ländercode |
| `ROOT_PW` | `artframe` | Root-Passwort (SSH) |
| `PI_PW` | `$ROOT_PW` | pi-User-Passwort |
| `ARCH` | `arm64` | `arm64` für Pi 4 (Pi 3 auch), `armhf` für Pi 1/Zero/2 |
| `EXTRA_MB` | `3000` | Root-Partition vergrößern (Chromium braucht Platz) |
| `OUT` | `./artframe-kiosk-arm64.img` | Output-Pfad |

## Flash

```bash
cp artframe-kiosk-arm64.img /mnt/c/Users/<dein-user>/Downloads/
```

Mit Raspberry Pi Imager → *Use custom image* → SD-Karte schreiben.

## Erstboot

1. Pi mit SD-Karte + HDMI + Strom + USB-FLIRC starten
2. Pi verbindet sich mit dem konfigurierten WLAN (~20-30s)
3. Auto-Login als `pi`, X startet, Chromium-Kiosk lädt deine Nowify-URL
4. Wenn keine Musik läuft → nach 60s Idle wechselt Nowify in den
   Artframe-iframe → du siehst den Format-Picker (Quer/Hochformat)
5. FLIRC-Tasten steuern: ↑↓←→ Enter Esc Backspace Space

## FLIRC programmieren

Vor dem ersten Test: am PC mit der **FLIRC-GUI** (Windows/Mac/Linux,
`https://flirc.tv/downloads`) den Stick programmieren. Pro Knopf der
Fernbedienung eine Tastatur-Taste zuweisen:

| FLIRC-Taste | Artframe-Aktion |
|---|---|
| ↑ Up | nach oben in der Liste |
| ↓ Down | nach unten |
| ← Left | links / zurück |
| → Right | rechts / nächstes Bild |
| Enter / OK | auswählen |
| Escape / Back | zurück / Menü |
| Backspace | zurück |
| Space | Pause/Resume in Diashow |
| i | Info-Overlay an/aus |

Die Belegung wird auf dem Stick gespeichert — am Pi keine weitere
Konfiguration nötig.

## SSH-Zugang

```bash
ssh root@artframe.local      # Passwort: $ROOT_PW (default: artframe)
# oder
ssh pi@<pi-ip>               # Passwort: $PI_PW
```

## Was steckt im Image

- RasPiOS Lite **arm64** (Bookworm), cloud-init disabled
- `chromium-browser`, `xserver-xorg`, `xinit`, `openbox`, `unclutter`,
  `python3` installiert
- `/opt/artframe-kiosk/xinitrc` — startet Chromium mit Kiosk-Flags
- `/opt/artframe-kiosk/bash_profile` — pi-User auto-startet X auf tty1
- `/etc/systemd/system/getty@tty1.service.d/autologin.conf` — pi
  loggt sich auto-ein
- `/usr/local/bin/kiosk-control.py` + `kiosk-control.service` —
  HTTP-Endpoint `127.0.0.1:8787/shutdown` für Pi-Auto-Shutdown nach
  60 Min Idle ohne Musik
- `/boot/firmware/wpa_supplicant.conf` — WLAN-Credentials
- SSH aktiviert, root + pi mit Passwort
- tty2 als Notfall-Konsole (Strg+Alt+F2 falls Chromium hängt)

## Updates

Die Webui (Nowify + Artframe) wird über Netlify ausgeliefert. Push auf
den Main-Branch → Netlify rebuildt → Pi Refresh holt die neue Version.
Das Pi-Image musst du nur dann neu bauen, wenn sich:
- WLAN-Credentials,
- Chromium-Kiosk-Flags,
- oder die Pi-System-Konfiguration

ändern.
