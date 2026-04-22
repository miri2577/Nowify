# Build a ready-to-flash artframe image

Produces a single `.img` file that boots straight into the framebuffer
slideshow with 100 pre-loaded artworks. No network needed to run.

## One-time WSL2 setup (on your Windows machine)

If you don't have WSL2 Ubuntu yet:

```powershell
wsl --install -d Ubuntu-22.04
```

Reboot, finish the Ubuntu username/password dialog, then open Ubuntu
and install the build tools:

```bash
sudo apt update
sudo apt install -y qemu-user-static binfmt-support xz-utils curl \
                    parted dosfstools python3 git
sudo update-binfmts --enable qemu-arm
```

## Build

Inside WSL2 Ubuntu:

```bash
git clone https://github.com/miri2577/Nowify.git ~/Nowify
cd ~/Nowify/artframe/build-image
bash build.sh
```

First run downloads ~500 MB (RasPiOS Lite + 100 JPGs), takes about
10–15 minutes on a decent connection. Subsequent runs reuse the cache
in `./work/` — delete that directory for a fully fresh build.

Output: `./artframe.img` (~3 GB).

### Knobs

Override via environment:

| Var | Default | Meaning |
|---|---|---|
| `COUNT` | `100` | number of artworks to bake in |
| `ORIENT` | `landscape` | `landscape`, `portrait`, or `any` |
| `ROOT_PW` | `artframe` | root password (SSH) |
| `EXTRA_MB` | `1536` | MB to grow the root partition by |
| `OUT` | `./artframe.img` | output file |

Example:

```bash
COUNT=200 ORIENT=portrait ROOT_PW=geheim bash build.sh
```

## Flash

Copy the image to Windows and flash with Raspberry Pi Imager:

```bash
cp artframe.img /mnt/c/Users/<you>/Downloads/
```

In Pi Imager → *Use custom image* → pick `artframe.img` → write.

Or `dd` directly to an SD card from WSL2 (needs `usbipd-win` to attach
the USB reader — overkill, use Imager).

## What's on the image

- RasPiOS Lite armhf (Bookworm), cloud-init disabled
- `fbi` installed
- `/opt/artframe/run-display.sh` — the slideshow loop
- `/etc/systemd/system/artframe-display.service` — enabled, owns tty1
- `/var/lib/artframe/images/*.jpg` — your 100 artworks
- `getty@tty1` masked (so fbi owns the console)
- SSH enabled, root login with password permitted
- Hostname: `artframe`

## First boot

- Green ACT LED blinks as the rootfs replays its journal (first-boot
  check + any pending resize; ~30 s extra the first time).
- HDMI comes up to a black screen for ~20 s while fbi initialises.
- Slideshow starts. 60 s per image, random order, loops the 100
  stored JPGs forever.

## Refilling / replacing images

Since there's no network, you either:

- **Re-build the image** with `bash build.sh` (fresh artworks each run).
- **Or** mount the SD on a PC and drop new JPGs into the ext4 root
  partition under `/var/lib/artframe/images/`.
- **Or** boot once with an ethernet-USB dongle or enable WiFi via
  `wpa_supplicant.conf`, SSH in (`root` / `$ROOT_PW`), and `scp` files
  to `/var/lib/artframe/images/`.
