#!/bin/bash
# Build a flashable Pi-4 image: Chromium-Kiosk pointing at the deployed
# Nowify URL (which iframes the Artframe at /artframe/).
#
# Run in WSL2 Ubuntu. Prereqs:
#   sudo apt install -y qemu-user-static binfmt-support xz-utils curl \
#                       parted kpartx dosfstools python3 sudo
#
# Required env vars:
#   NOWIFY_URL   — public URL of the Netlify deploy
#                  (e.g. https://nowify-xyz.netlify.app)
#   WIFI_SSID    — your wifi network name
#   WIFI_PSK     — your wifi password
#
# Optional env vars:
#   WIFI_COUNTRY — 2-letter country code (default: DE)
#   ROOT_PW      — root login password (default: artframe)
#   PI_PW        — pi user password (default: same as ROOT_PW)
#   ARCH         — arm64 (default — for Pi 4) or armhf
#   OUT          — output .img path (default: $PWD/artframe-kiosk-arm64.img)
#   EXTRA_MB     — extra MB to add to root partition (default: 3000)
#                  Chromium + Xorg need ~2 GB.

set -euo pipefail

# ─── Config ────────────────────────────────────────────────────────
: "${NOWIFY_URL:?Please set NOWIFY_URL=https://your-netlify.netlify.app}"
: "${WIFI_SSID:?Please set WIFI_SSID=YourWifiName}"
: "${WIFI_PSK:?Please set WIFI_PSK=YourWifiPassword}"

WIFI_COUNTRY="${WIFI_COUNTRY:-DE}"
ROOT_PW="${ROOT_PW:-artframe}"
PI_PW="${PI_PW:-$ROOT_PW}"
ARCH="${ARCH:-arm64}"
EXTRA_MB="${EXTRA_MB:-3000}"

case "$ARCH" in
  armhf)
    DEFAULT_URL="https://downloads.raspberrypi.com/raspios_lite_armhf_latest"
    QEMU_BIN="qemu-arm-static"
    ;;
  arm64)
    DEFAULT_URL="https://downloads.raspberrypi.com/raspios_lite_arm64_latest"
    QEMU_BIN="qemu-aarch64-static"
    ;;
  *)
    echo "ERROR: ARCH must be armhf or arm64 (got: $ARCH)"; exit 1 ;;
esac

IMAGE_URL="${IMAGE_URL:-$DEFAULT_URL}"
OUT="${OUT:-$PWD/artframe-kiosk-$ARCH.img}"
WORK="${WORK:-$PWD/work-kiosk-$ARCH}"

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

# ─── Preflight ─────────────────────────────────────────────────────
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1"; exit 1; }; }
for t in curl xz sudo sfdisk parted losetup e2fsck resize2fs python3; do
    need "$t"
done
[ -f "/usr/bin/$QEMU_BIN" ] || {
    echo "ERROR: $QEMU_BIN missing. Install with:"
    echo "  sudo apt install -y qemu-user-static binfmt-support"
    exit 1
}

mkdir -p "$WORK"
cd "$WORK"

# ─── 1. Download base image ────────────────────────────────────────
if [ ! -f base.img.xz ]; then
    echo "==> Downloading RasPiOS Lite ($ARCH)..."
    curl -fL "$IMAGE_URL" -o base.img.xz
fi
if [ ! -f base.img ]; then
    echo "==> Extracting..."
    xz -dkf base.img.xz
    if [ ! -f base.img ]; then
        src="$(ls -1 *.img 2>/dev/null | grep -v '^base\.img$' | head -1)"
        [ -n "$src" ] && mv -f "$src" base.img
    fi
fi

# ─── 2. Fresh copy + expand ────────────────────────────────────────
cp base.img artframe-kiosk.img
echo "==> Expanding image by ${EXTRA_MB} MB (Chromium needs space)..."
truncate -s "+${EXTRA_MB}M" artframe-kiosk.img
echo ", +" | sudo sfdisk -N 2 artframe-kiosk.img

# ─── 3. Loop-mount ─────────────────────────────────────────────────
LOOP=$(sudo losetup -fP --show "$WORK/artframe-kiosk.img")
trap 'sudo umount -lf "$WORK/mnt/boot/firmware" 2>/dev/null || true; \
      sudo umount -lf "$WORK/mnt/dev/pts" 2>/dev/null || true; \
      sudo umount -lf "$WORK/mnt/dev" 2>/dev/null || true; \
      sudo umount -lf "$WORK/mnt/proc" 2>/dev/null || true; \
      sudo umount -lf "$WORK/mnt/sys" 2>/dev/null || true; \
      sudo umount -lf "$WORK/mnt" 2>/dev/null || true; \
      sudo losetup -d "$LOOP" 2>/dev/null || true' EXIT

sudo partprobe "$LOOP"
sleep 1
sudo e2fsck -fy "${LOOP}p2" || true
sudo resize2fs "${LOOP}p2"

mkdir -p "$WORK/mnt"
sudo mount "${LOOP}p2" "$WORK/mnt"
sudo mkdir -p "$WORK/mnt/boot/firmware"
sudo mount "${LOOP}p1" "$WORK/mnt/boot/firmware"

# ─── 4. WiFi-Setup (boot/firmware/) ────────────────────────────────
echo "==> Writing WiFi config..."
PSK_HASH=$(printf '%s' "$WIFI_PSK" | iconv -t UTF-8 | \
    openssl dgst -sha1 -mac HMAC -macopt key:"$(printf '%s' "$WIFI_PSK")" 2>/dev/null \
    | sed 's/^.* //' || true)
# Falls openssl-Hash schiefgeht: Klartext in psk= reicht auch (RasPiOS akzeptiert).
sudo tee "$WORK/mnt/boot/firmware/wpa_supplicant.conf" >/dev/null <<EOF
country=$WIFI_COUNTRY
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="$WIFI_SSID"
    psk="$WIFI_PSK"
    key_mgmt=WPA-PSK
}
EOF
sudo chmod 0600 "$WORK/mnt/boot/firmware/wpa_supplicant.conf"

# ─── 5. SSH + pi-User-Pre-config ───────────────────────────────────
sudo touch "$WORK/mnt/boot/firmware/ssh"
# userconf.txt setzt das pi-Passwort beim ersten Boot
PI_HASH=$(openssl passwd -6 "$PI_PW")
echo "pi:$PI_HASH" | sudo tee "$WORK/mnt/boot/firmware/userconf.txt" >/dev/null

# ─── 6. Inject kiosk-Skripte ───────────────────────────────────────
echo "==> Injecting kiosk scripts..."
sudo install -d -m 0755 "$WORK/mnt/opt/artframe-kiosk"

# Kiosk-Autostart (xinitrc)
sudo tee "$WORK/mnt/opt/artframe-kiosk/xinitrc" >/dev/null <<XINITRC
#!/bin/sh
# Bildschirmschoner und Powermanagement aus
xset s off
xset -dpms
xset s noblank

# Cursor verstecken nach 1s Inaktivitaet
unclutter -idle 1 -root &

# Openbox als Fenster-Manager (minimal, ohne Decorations)
openbox-session &

# Chromium im Kiosk-Modus auf die Nowify-URL
exec chromium-browser \\
    --kiosk \\
    --noerrdialogs \\
    --disable-infobars \\
    --disable-translate \\
    --disable-features=TranslateUI \\
    --disable-pinch \\
    --overscroll-history-navigation=0 \\
    --check-for-update-interval=31536000 \\
    --disable-web-security \\
    --user-data-dir=/home/pi/.config/chromium-kiosk \\
    --unsafely-treat-insecure-origin-as-secure=http://127.0.0.1:8787 \\
    --autoplay-policy=no-user-gesture-required \\
    --no-first-run \\
    --enable-features=OverlayScrollbar \\
    --start-fullscreen \\
    "$NOWIFY_URL"
XINITRC
sudo chmod 0755 "$WORK/mnt/opt/artframe-kiosk/xinitrc"

# bash_profile fuer pi: bei Login auf tty1 → startx
sudo tee "$WORK/mnt/opt/artframe-kiosk/bash_profile" >/dev/null <<'PROFILE'
# Auf tty1 automatisch X starten (Kiosk).
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    exec startx /opt/artframe-kiosk/xinitrc -- -nocursor
fi
PROFILE

# kiosk-control daemon (Shutdown-Endpoint) aus pi/ kopieren
sudo install -m 0755 "$REPO_ROOT/pi/kiosk-control.py" \
    "$WORK/mnt/usr/local/bin/kiosk-control.py"
sudo install -m 0644 "$REPO_ROOT/pi/kiosk-control.service" \
    "$WORK/mnt/etc/systemd/system/kiosk-control.service"

# ─── 7. Chroot: Pakete + Auto-Login + Services ─────────────────────
echo "==> Installing packages + configuring inside chroot..."
sudo cp "/usr/bin/$QEMU_BIN" "$WORK/mnt/usr/bin/"
sudo cp /etc/resolv.conf "$WORK/mnt/etc/resolv.conf"
sudo mount --bind /dev "$WORK/mnt/dev"
sudo mount --bind /dev/pts "$WORK/mnt/dev/pts"
sudo mount --bind /proc "$WORK/mnt/proc"
sudo mount --bind /sys "$WORK/mnt/sys"

sudo chroot "$WORK/mnt" "/usr/bin/$QEMU_BIN" /bin/bash <<CHROOT
set -e
export DEBIAN_FRONTEND=noninteractive
export LANG=C
apt-get update
# Kiosk-Stack. chromium-browser wurde in Debian Trixie entfernt,
# das aktuelle Paket heisst nur "chromium". Wir versuchen erst
# chromium, fallen sonst auf chromium-browser zurueck (Bullseye).
apt-get install -y --no-install-recommends \\
    xserver-xorg \\
    xinit \\
    x11-xserver-utils \\
    openbox \\
    unclutter \\
    fonts-dejavu-core \\
    python3 \\
    ca-certificates \\
    wpasupplicant \\
    wireless-tools
apt-get install -y --no-install-recommends chromium \\
    || apt-get install -y --no-install-recommends chromium-browser

# Welcher Chromium-Binary-Name? In Trixie /usr/bin/chromium,
# in Bullseye /usr/bin/chromium-browser. Wir setzen einen Symlink
# damit unser xinitrc immer 'chromium-browser' aufrufen kann.
if [ ! -x /usr/bin/chromium-browser ] && [ -x /usr/bin/chromium ]; then
    ln -sf /usr/bin/chromium /usr/bin/chromium-browser
fi

# Root-Passwort
echo "root:${ROOT_PW}" | chpasswd

# SSH einschalten (PermitRootLogin yes — bequem fuer Debug)
systemctl enable ssh
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
rm -f /etc/ssh/ssh_host_*
ssh-keygen -A

# pi-User: shell + .bash_profile (auto-startx auf tty1)
usermod -s /bin/bash pi 2>/dev/null || true
install -m 0644 -o pi -g pi /opt/artframe-kiosk/bash_profile /home/pi/.bash_profile

# Auto-Login fuer pi auf tty1
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin pi --noclear %I \\\$TERM
EOF

# tty2 als Notfall-Konsole offen lassen (Strg+Alt+F2)
systemctl enable getty@tty2.service

# Erstboot-Wizard von RasPiOS unterdruecken
systemctl disable userconfig.service 2>/dev/null || true
systemctl mask    userconfig.service 2>/dev/null || true

# kiosk-control.service aktivieren (Shutdown-Endpoint)
systemctl enable kiosk-control.service

# Cloud-init aus
systemctl disable cloud-init cloud-init-local cloud-config cloud-final 2>/dev/null || true
touch /etc/cloud/cloud-init.disabled 2>/dev/null || true
rm -f /etc/init.d/resize2fs_once 2>/dev/null || true

# Hardware-Watchdog aus (sonst rebootet der Pi bei Chromium-Hangs)
mkdir -p /etc/systemd/system.conf.d
cat > /etc/systemd/system.conf.d/no-watchdog.conf <<EOF
[Manager]
RuntimeWatchdogSec=0
RebootWatchdogSec=0
EOF

# Persistent Journal — Logs ueberleben Reboots
mkdir -p /var/log/journal
systemd-tmpfiles --create --prefix /var/log/journal 2>/dev/null || true

# WiFi-Country fuer regdomain (wichtig fuer 5GHz)
mkdir -p /etc/wpa_supplicant
echo 'country=${WIFI_COUNTRY}' > /etc/wpa_supplicant/wpa_supplicant-country.conf 2>/dev/null || true

# NetworkManager (Bookworm) → wpa_supplicant.conf wird auf erstem Boot
# nach /etc/wpa_supplicant migriert. Reicht so.

# WLAN-rfkill ggf. lift
rfkill unblock wifi 2>/dev/null || true
CHROOT

sudo rm -f "$WORK/mnt/usr/bin/$QEMU_BIN"
sudo rm -f "$WORK/mnt/etc/resolv.conf"

# ─── 8. cmdline.txt aufraeumen ────────────────────────────────────
sudo sed -i -E 's/\bresize\b//g; s/\bds=nocloud;[^ ]*//g; s/\s+/ /g; s/^ +//; s/ +$//' \
    "$WORK/mnt/boot/firmware/cmdline.txt"

# ─── 9. Unmount + done ─────────────────────────────────────────────
echo "==> Unmounting..."
sync
sudo umount "$WORK/mnt/dev/pts"
sudo umount "$WORK/mnt/dev"
sudo umount "$WORK/mnt/proc"
sudo umount "$WORK/mnt/sys"
sudo umount "$WORK/mnt/boot/firmware"
sudo umount "$WORK/mnt"
sudo losetup -d "$LOOP"
trap - EXIT

mv "$WORK/artframe-kiosk.img" "$OUT"
ls -lh "$OUT"

cat <<DONE

==> Done. Image fertig:
    $OUT

Flash mit Raspberry Pi Imager ("Use custom") oder:
    sudo dd if=$OUT of=/dev/sdX bs=4M status=progress conv=fsync

Credentials gebacken:
    user: pi    password: $PI_PW
    user: root  password: $ROOT_PW
    host: artframe (.local via avahi falls installiert)

Das Image bootet → WiFi verbindet sich mit "$WIFI_SSID" → pi loggt sich
auto-ein → X startet → Chromium-Kiosk laedt $NOWIFY_URL.
Nach 60s Idle (keine Musik) wechselt Nowify in den Artframe-iframe.

FLIRC-Stick einstecken (Tasten vorher mit FLIRC-GUI am PC programmieren:
↑↓←→ Enter Esc Backspace Space) — funktioniert direkt als USB-Keyboard.
DONE
