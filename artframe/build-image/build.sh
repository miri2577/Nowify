#!/bin/bash
# Build a ready-to-flash artframe.img from RasPiOS Lite (armhf).
#
# Run in WSL2 Ubuntu. Requires:
#   sudo apt install -y qemu-user-static binfmt-support xz-utils curl \
#                       parted kpartx dosfstools python3 sudo
#
# Produces artframe.img in the working directory. Flash with Raspberry
# Pi Imager ("Use custom") or `dd`.
#
# The resulting SD boots straight into a framebuffer slideshow with
# 100 pre-loaded artworks. No network, no SSH needed to run. SSH is
# still enabled (user: root / password: $ROOT_PW) in case you want in.

set -euo pipefail

# ─── Config (override via env) ──────────────────────────────────────
IMAGE_URL="${IMAGE_URL:-https://downloads.raspberrypi.com/raspios_lite_armhf_latest}"
OUT="${OUT:-$PWD/artframe.img}"
WORK="${WORK:-$PWD/work}"
COUNT="${COUNT:-100}"
ORIENT="${ORIENT:-landscape}"
ROOT_PW="${ROOT_PW:-artframe}"
EXTRA_MB="${EXTRA_MB:-1536}"   # expand root partition for packages + JPGs

HERE="$(cd "$(dirname "$0")" && pwd)"
ARTFRAME_SRC="$(cd "$HERE/.." && pwd)"

# ─── Preflight ──────────────────────────────────────────────────────
need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1"; exit 1; }; }
for t in curl xz sudo sfdisk parted losetup e2fsck resize2fs python3; do need "$t"; done
[ -f /usr/bin/qemu-arm-static ] || {
  echo "ERROR: qemu-arm-static missing. Install with:"
  echo "  sudo apt install -y qemu-user-static binfmt-support"
  exit 1
}

mkdir -p "$WORK"
cd "$WORK"

# ─── 1. Download base image ─────────────────────────────────────────
if [ ! -f base.img.xz ]; then
  echo "==> Downloading RasPiOS Lite (armhf)..."
  curl -fL "$IMAGE_URL" -o base.img.xz
fi

if [ ! -f base.img ]; then
  echo "==> Extracting..."
  xz -dkf base.img.xz
  mv -f -- *-raspios-*-armhf-lite.img base.img 2>/dev/null || \
    mv -f "$(ls -1 *.img | head -1)" base.img
fi

# ─── 2. Fresh copy, expand by EXTRA_MB ─────────────────────────────
cp base.img artframe.img
echo "==> Expanding image by ${EXTRA_MB} MB..."
truncate -s "+${EXTRA_MB}M" artframe.img

# Grow partition 2 (root) to fill the new space
echo ", +" | sudo sfdisk -N 2 artframe.img

# ─── 3. Loop-mount ──────────────────────────────────────────────────
LOOP=$(sudo losetup -fP --show "$WORK/artframe.img")
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

# ─── 4. Fetch artworks on the host ──────────────────────────────────
if [ ! -d "$WORK/art" ] || [ "$(find "$WORK/art" -name '*.jpg' 2>/dev/null | wc -l)" -lt "$COUNT" ]; then
  echo "==> Downloading $COUNT artworks from AIC..."
  mkdir -p "$WORK/art"
  ARTFRAME_DIR="$WORK/art" \
  ARTFRAME_KEEP="$COUNT" \
  ARTFRAME_ORIENT="$ORIENT" \
  python3 "$ARTFRAME_SRC/fetch.py"
fi

# ─── 5. Inject artframe assets ──────────────────────────────────────
echo "==> Injecting artframe files..."
sudo install -d -m 0755 "$WORK/mnt/opt/artframe"
sudo install -d -m 0755 "$WORK/mnt/var/lib/artframe/images"
sudo install -m 0755 "$ARTFRAME_SRC/run-display.sh" "$WORK/mnt/opt/artframe/"
sudo install -m 0644 "$ARTFRAME_SRC/artframe-display.service" \
                     "$WORK/mnt/etc/systemd/system/"
sudo cp "$WORK/art"/*.jpg "$WORK/mnt/var/lib/artframe/images/"

# ─── 6. Chroot: install fbi, set password, enable services ─────────
echo "==> Installing fbi + configuring inside chroot..."
sudo cp /usr/bin/qemu-arm-static "$WORK/mnt/usr/bin/"
sudo cp /etc/resolv.conf "$WORK/mnt/etc/resolv.conf"
sudo mount --bind /dev "$WORK/mnt/dev"
sudo mount --bind /dev/pts "$WORK/mnt/dev/pts"
sudo mount --bind /proc "$WORK/mnt/proc"
sudo mount --bind /sys "$WORK/mnt/sys"

sudo chroot "$WORK/mnt" /usr/bin/qemu-arm-static /bin/bash <<CHROOT
set -e
export DEBIAN_FRONTEND=noninteractive
export LANG=C
apt-get update
apt-get install -y --no-install-recommends fbi coreutils

# Root password
echo "root:${ROOT_PW}" | chpasswd

# Enable SSH + permit root login with password
systemctl enable ssh
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config

# Enable artframe, mask tty1 login
systemctl enable artframe-display.service
systemctl mask getty@tty1.service

# Disable cloud-init firstrun customisation (we're doing it all here)
systemctl disable cloud-init cloud-init-local cloud-config cloud-final 2>/dev/null || true
touch /etc/cloud/cloud-init.disabled 2>/dev/null || true

# Don't resize partition on first boot — we already did
rm -f /etc/init.d/resize2fs_once 2>/dev/null || true
CHROOT

sudo rm -f "$WORK/mnt/usr/bin/qemu-arm-static"
sudo rm -f "$WORK/mnt/etc/resolv.conf"

# ─── 7. Strip cloud-init firstrun junk from cmdline.txt ────────────
echo "==> Simplifying cmdline.txt..."
sudo sed -i -E 's/\bresize\b//g; s/\bds=nocloud;[^ ]*//g; s/\s+/ /g; s/^ +//; s/ +$//' \
  "$WORK/mnt/boot/firmware/cmdline.txt"

# ─── 8. Empty ssh-enable file (belt and braces) ────────────────────
sudo touch "$WORK/mnt/boot/firmware/ssh"

# ─── 9. Unmount, detach, done ──────────────────────────────────────
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

mv "$WORK/artframe.img" "$OUT"
ls -lh "$OUT"
echo
echo "==> Done. Flash with Raspberry Pi Imager ('Use custom') or:"
echo "    sudo dd if=$OUT of=/dev/sdX bs=4M status=progress conv=fsync"
echo
echo "Credentials baked in:"
echo "    user: root   password: $ROOT_PW"
echo "    hostname: artframe (.local via avahi if installed)"
