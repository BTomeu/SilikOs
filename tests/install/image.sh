#!/usr/bin/env bash
# tests/install/image.sh ISO [OUT_DIR]: a disk image of SilikOS already installed, to write straight onto a disk
# (an external one, with balenaEtcher or dd) and start from it: no installer, no USB stick. The owner, 14/11/2026:
# "directly install the system on the disk, without a USB stick for the installation".
#   1. the ISO's own kickstart + the lines of image.ks.in installs the shipped package set, under UEFI, onto a raw
#      disk image on a USB controller. What makes it an image for any computer and for nobody yet:
#        - not encrypted: an image anyone can download cannot keep a passphrase (docs/DISK.md);
#        - the initramfs with every driver (the base's dracut-config-generic): it starts on USB, SATA or NVMe;
#        - no user: the first start asks for the language, the keyboard and the user (gnome-initial-setup, as the
#          base does when a system has no user); root is locked;
#        - no machine id, no ssh host keys, no console on the serial port: each is made at the first start.
#      Nothing of the tests is in it: no check script, no test user.
#   2. the image is not started: two copy-on-write layers over it are, so that what is published has never run.
#        usb    another computer: new firmware variables with Secure Boot on, the disk on a USB controller
#        sata   another one: the disk on SATA
#      Each must reach the first-start setup: the screen is read (a picture, then OCR).
#   3. the image is compressed (xz): SilikOS-VERSION-ARCH-disk.img.xz, with its sha256 and the size a disk needs.
#   OUT_DIR (default build/image): the image, install.log, the screens, report.txt; exit 0 when no check failed.
#   SILIK_CI_IMAGE_GB (default 40): the image's size; the disk it is written to must be at least that large.
# Needs qemu-system-x86_64, qemu-img, xorriso, mtools, python3, xz, OVMF, ImageMagick (convert) and tesseract.
# What it cannot show: a real computer, a real disk, and the setup's screens after the first.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../.." && pwd)
iso=${1:?usage: tests/install/image.sh ISO [OUT_DIR]}
out=${2:-$root/build/image}
mem=${SILIK_CI_MEM:-4096}; cpus=${SILIK_CI_CPUS:-$(nproc)}; gb=${SILIK_CI_IMAGE_GB:-40}
t_install=${SILIK_CI_INSTALL_MIN:-110}; t_boot=${SILIK_CI_BOOT_MIN:-8}
mkdir -p "$out"; out=$(cd "$out" && pwd); iso=$(cd "$(dirname "$iso")" && pwd)/$(basename "$iso")
work=$(mktemp -d /tmp/silik-image.XXXXXX)
qpid=""
cleanup() { [ -z "$qpid" ] || kill "$qpid" 2> /dev/null || true; rm -rf "$work"; }
trap cleanup EXIT

if [ -w /dev/kvm ]; then accel=(-enable-kvm -cpu host)
elif [ "${SILIK_CI_TCG:-0}" = 1 ]; then accel=(-accel tcg,thread=multi -cpu max); echo "no /dev/kvm: emulating (very slow)"
else echo "error: /dev/kvm is not usable (SILIK_CI_TCG=1 to emulate, many hours)" >&2; exit 2; fi
for tool in qemu-system-x86_64 qemu-img xorriso mformat mcopy python3 xz sha256sum convert tesseract; do
  command -v "$tool" > /dev/null || { echo "error: $tool is not installed" >&2; exit 2; }
done
first_of() { local f; for f in "$@"; do [ -n "$f" ] && [ -f "$f" ] && { echo "$f"; return 0; }; done; return 1; }
code=$(first_of "${SILIK_CI_OVMF_CODE:-}" /usr/share/OVMF/OVMF_CODE_4M.secboot.fd /usr/share/OVMF/OVMF_CODE.secboot.fd /usr/share/edk2/ovmf/OVMF_CODE.secboot.fd) \
  && vars_sb=$(first_of "${SILIK_CI_OVMF_VARS_SB:-}" /usr/share/OVMF/OVMF_VARS_4M.ms.fd /usr/share/OVMF/OVMF_VARS.ms.fd /usr/share/edk2/ovmf/OVMF_VARS.secboot.fd) \
  && vars_plain=$(first_of "${SILIK_CI_OVMF_VARS:-}" /usr/share/OVMF/OVMF_VARS_4M.fd /usr/share/OVMF/OVMF_VARS.fd /usr/share/edk2/ovmf/OVMF_VARS.fd) \
  || { echo "error: no OVMF firmware found (the package ovmf, or edk2-ovmf)" >&2; exit 2; }
machine=(-machine q35,smm=on -global driver=cfi.pflash01,property=secure,value=on -global ICH9-LPC.disable_s3=1)

label=$(xorriso -indev "$iso" -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: *//p')
[ -n "$label" ] || { echo "error: cannot read the label of $iso" >&2; exit 2; }
xorriso -indev "$iso" -osirrox on -extract /silikos.ks "$work/shipped.ks" -extract /images/pxeboot/vmlinuz "$work/vmlinuz" \
  -extract /images/pxeboot/initrd.img "$work/initrd.img" > /dev/null 2>&1
chmod u+w "$work"/*
clean() { tr -d '\r' < "$1" | sed 's/\x1b\[[0-9;?]*[A-Za-z]//g; s/\x1b[()][A-Z0-9]//g' | grep -a -v '^[[:space:]]*$'; }
: > "$out/report.txt"
row() { printf '%-5s %-40s %s\n' "$1" "$2" "$(echo "$3" | tr '\n' ' ' | cut -c1-500)" >> "$out/report.txt"; }

# the name: SilikOS-9.8-x86_64-netinstall.iso -> SilikOS-9.8-x86_64-disk.img
name=$(basename "$iso" | sed -E 's/-(netinstall|offline|lab-[a-z0-9]*-netinstall)\.iso$//')-disk.img
img="$out/$name"

# the kickstart: the ISO's own (its screen-mode line taken out; its package set, its services and its boot loader
# line stay) + the image's lines, and the base's package that makes the initramfs with every driver
python3 - "$work/shipped.ks" "$here/image.ks.in" > "$work/image.ks" <<'EOF'
import re, sys
shipped, extra = sys.argv[1:3]
ks = "\n".join(l for l in open(shipped).read().splitlines() if l != "graphical") + "\n"
ks = re.sub(r"(?m)^%packages\n", "%packages\ndracut-config-generic\n", ks, count=1)
print(ks + open(extra).read())
EOF
cp "$work/image.ks" "$out/image.ks"
dd if=/dev/zero of="$work/ks.img" bs=1M count=8 status=none
mformat -i "$work/ks.img" -v SILIKCI ::
mcopy -i "$work/ks.img" "$work/image.ks" ::/ci.ks

# ---------------------------------------------------------------------------------------------- 1. the installation
rm -f "$img"; qemu-img create -q -f raw "$img" "${gb}G"
cp "$vars_plain" "$work/vars-install.fd"
echo "[image] installing from $(basename "$iso") under UEFI onto a ${gb} GB raw image on a USB controller, $cpus CPUs, $mem MB; the installer's console: $out/install.log"
: > "$out/install.log"
rc=0
timeout "${t_install}m" qemu-system-x86_64 "${accel[@]}" "${machine[@]}" -m "$mem" -smp "$cpus" -display none -no-reboot \
  -drive "if=pflash,format=raw,unit=0,readonly=on,file=$code" -drive "if=pflash,format=raw,unit=1,file=$work/vars-install.fd" \
  -kernel "$work/vmlinuz" -initrd "$work/initrd.img" \
  -append "inst.stage2=hd:LABEL=$label inst.ks=hd:LABEL=SILIKCI:/ci.ks inst.text console=ttyS0,115200 ${SILIK_CI_APPEND:-}" \
  -drive "file=$work/ks.img,if=virtio,format=raw,readonly=on" \
  -device qemu-xhci,id=xhci -drive "if=none,id=ext,file=$img,format=raw,discard=unmap,detect-zeroes=unmap" \
  -device usb-storage,bus=xhci.0,drive=ext,serial=SILIKIMG \
  -cdrom "$iso" -nic user,model=virtio-net-pci -serial "file:$out/install.log" -monitor none &
qpid=$!
( n=0
  while kill -0 $qpid 2> /dev/null; do
    sleep 20; n=$((n + 1))
    if grep -q "Please make a selection from the above" "$out/install.log"; then    # it asks: it will never go on
      echo "error: [image] the installer stopped at its summary and waits for an answer:" >&2
      clean "$out/install.log" | grep -B14 "Please make a selection" | tail -16 >&2
      pkill -P $qpid qemu-system-x86 2> /dev/null; kill $qpid 2> /dev/null
      break
    fi
    [ $((n % 6)) = 0 ] && echo "  ... $(clean "$out/install.log" | tail -1 | cut -c1-150)"
  done ) &
watch=$!
disown $watch
wait $qpid || rc=$?
qpid=""
pkill -P $watch 2> /dev/null || true; kill $watch 2> /dev/null || true
echo "::group::[image] what the installation said of the image (its last step)"
clean "$out/install.log" | grep -a '^SILIKOS-IMG' | cut -c1-400 || true
echo "::endgroup::"
if [ $rc -ne 0 ]; then
  echo "error: [image] the installation did not finish (exit $rc; 124 = time limit of $t_install min). Last lines of its console:" >&2
  clean "$out/install.log" | tail -40 >&2
  row FAIL image.installed "did not finish: $(clean "$out/install.log" | grep -i "error\|\[!\]" | tail -2 | tr '\n' ' ' | cut -c1-200)"
  cat "$out/report.txt"; rm -f "$img"; exit 1
fi
row ok image.installed "the shipped package set installed onto the image: $(du -h "$img" | cut -f1) of ${gb} GB used"
# what the image must and must not carry, as its own last step said it
said() { clean "$out/install.log" | sed -n "s/^SILIKOS-IMG|$1|//p" | tail -1; }
[ "$(said users)" = none ] && row ok image.no-user "no user in the image: the first start asks for one" || row FAIL image.no-user "users in the image: $(said users)"
case "$(said root)" in L*) row ok image.root-locked "root is locked ($(said root))" ;; *) row FAIL image.root-locked "root's password state: '$(said root)'" ;; esac
[ "$(said machine-id)" = empty ] && row ok image.no-machine-id "no machine id: each system makes its own at its first start" || row FAIL image.no-machine-id "machine id: $(said machine-id)"
case " $(said args) " in *console=ttyS0*) row FAIL image.no-serial-console "the kernel's command line has a serial console: $(said args)" ;; *" rhgb "*) row ok image.no-serial-console "the kernel's command line: $(said args)" ;; *) row FAIL image.no-serial-console "no rhgb on the kernel's command line: '$(said args)'" ;; esac
case "$(said initramfs)" in *"ahci 1"*"nvme 1"*"usb-storage 1"*) row ok image.initramfs-generic "the initramfs has every driver: $(said initramfs)" ;; *) row FAIL image.initramfs-generic "the initramfs: '$(said initramfs)'" ;; esac
case "$(said encrypted)" in no) row ok image.not-encrypted "not encrypted (an image anyone can download cannot keep a passphrase)" ;; *) row FAIL image.not-encrypted "LUKS in the image: $(said encrypted)" ;; esac
[ "$(said ci)" = none ] && row ok image.nothing-of-the-tests "no check script, service or test user of the tests in the image" || row FAIL image.nothing-of-the-tests "found: $(said ci)"
row info image.layout "$(said layout)"

# ---------------------------------------------------------------------------------------------- 2. it starts
picture() {   # picture FILE.ppm: the screen in letters; its last line says how much of it is not background
  python3 - "$1" <<'EOF' || true
import sys
try:
    data = open(sys.argv[1], "rb").read()
    tok, pos = [], 0
    while len(tok) < 4:                               # P6, width, height, maxval
        while data[pos:pos + 1].isspace(): pos += 1
        if data[pos:pos + 1] == b"#":
            pos = data.index(b"\n", pos) + 1; continue
        end = pos
        while not data[end:end + 1].isspace(): end += 1
        tok.append(data[pos:end]); pos = end
    w, h = int(tok[1]), int(tok[2]); pix = data[pos + 1:]
except (OSError, ValueError, IndexError):
    print("no picture of the screen"); print("lit 0"); sys.exit(0)
cols, rows, ramp = 100, 34, " .:-=+*#%@"
bg = pix[0] + pix[1] + pix[2]
lit, out = 0, []
for r in range(rows):
    line = ""
    for c in range(cols):
        x0, x1, y0, y1 = c * w // cols, (c + 1) * w // cols, r * h // rows, (r + 1) * h // rows
        m = 0
        for y in range(y0, y1, 2):
            base = (y * w + x0) * 3
            row = pix[base:base + (x1 - x0) * 3]
            for i in range(0, len(row) - 2, 6):
                d = abs(row[i] + row[i + 1] + row[i + 2] - bg)
                if d > m: m = d
        line += ramp[min(9, m * 10 // 766)]
        lit += m > 60
    out.append(line.rstrip())
while out and not out[-1]: out.pop()
while out and not out[0]: out.pop(0)
print("\n".join(out))
print("%d x %d; background %s" % (w, h, pix[:3].hex()))
print("lit %d" % lit)
EOF
}
# start NAME VARS DISK_ARGS...: a layer over the image starts in a machine with these firmware variables and this
# disk; the screen is read every 15 s until the first-start setup is on it (its language question, or its welcome)
start() {
  local name=$1 vars=$2 i seen=0 text fw; shift 2
  rm -f "$work/$name.qcow2" "$work/mon.sock"
  qemu-img create -q -f qcow2 -b "$img" -F raw "$work/$name.qcow2"
  : > "$out/start-$name.log"
  echo "[image] start '$name' (a layer over the image: the image itself is not written); the firmware's lines: $out/start-$name.log"
  qemu-system-x86_64 "${accel[@]}" "${machine[@]}" -m "$mem" -smp "$cpus" -display none -vga std \
    -drive "if=pflash,format=raw,unit=0,readonly=on,file=$code" -drive "if=pflash,format=raw,unit=1,file=$vars" \
    -drive "if=none,id=ext,file=$work/$name.qcow2,format=qcow2" "$@" \
    -nic user,model=virtio-net-pci -monitor "unix:$work/mon.sock,server,nowait" -serial "file:$out/start-$name.log" &
  qpid=$!
  for i in $(seq 1 50); do [ -S "$work/mon.sock" ] && break; sleep 0.2; done
  for i in $(seq 1 $((t_boot * 4))); do
    sleep 15
    kill -0 $qpid 2> /dev/null || break
    rm -f "$work/screen.ppm"
    python3 - "$work/mon.sock" "$work/screen.ppm" 2> /dev/null <<'EOF' || true
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); time.sleep(0.3); s.recv(65536)
s.send(("screendump %s\n" % sys.argv[2]).encode()); time.sleep(2.5)
EOF
    [ -s "$work/screen.ppm" ] || continue
    convert "$work/screen.ppm" "$out/screen-$name.png" 2> /dev/null || true
    convert "$work/screen.ppm" -colorspace Gray -resize 200% "$work/ocr.png" 2> /dev/null || continue
    tesseract "$work/ocr.png" "$work/ocr" --psm 6 > /dev/null 2>&1 || continue
    cp "$work/ocr.txt" "$out/screen-$name.txt"
    text=$(tr 'A-Z' 'a-z' < "$work/ocr.txt" | tr -cd 'a-z0-9')
    case "$text" in *welcome*|*english*deutsch*|*deutsch*english*|*unitedstates*|*espanol*|*francais*) seen=1; break ;; esac
  done
  echo "::group::[image] the screen of '$name' ($((i * 15)) s after the start)"
  picture "$work/screen.ppm" | grep -v '^lit ' || true
  echo "--- read from it:"
  grep -v '^[[:space:]]*$' "$out/screen-$name.txt" 2> /dev/null | head -30 | cut -c1-160 || true
  echo "::endgroup::"
  kill $qpid 2> /dev/null || true; wait $qpid 2> /dev/null || true; qpid=""
  fw=$(clean "$out/start-$name.log" | grep -a 'BdsDxe: starting' | sed 's/.*BdsDxe: starting //' | cut -c1-110 | tr '\n' ';' | cut -c1-300) || fw=""
  row info "image.$name.firmware" "${fw:-the firmware said nothing of what it started}"
  if [ $seen = 1 ]; then row ok "image.$name.first-start" "the image started there and reached its first-start setup in $((i * 15)) s: $(tr -s ' \n' ' ' < "$out/screen-$name.txt" | cut -c1-140)"
  else row FAIL "image.$name.first-start" "the first-start setup was not read on the screen in $((t_boot)) min (screen-$name.png, screen-$name.txt)"; fi
  rm -f "$work/$name.qcow2"
}
cp "$vars_sb" "$work/vars-usb.fd"; cp "$vars_plain" "$work/vars-sata.fd"
start usb "$work/vars-usb.fd" -device nec-usb-xhci,id=xhci -device usb-storage,bus=xhci.0,drive=ext,serial=SILIKIMG
start sata "$work/vars-sata.fd" -device ide-hd,drive=ext,bus=ide.0

# ---------------------------------------------------------------------------------------------- 3. the file
status=0
for must in image.installed image.no-user image.root-locked image.no-machine-id image.no-serial-console image.initramfs-generic \
            image.not-encrypted image.nothing-of-the-tests image.usb.first-start image.sata.first-start; do
  awk -v m="$must" '($1 == "ok" || $1 == "FAIL") && $2 == m { f = 1 } END { exit !f }' "$out/report.txt" \
    || printf '%-5s %-40s %s\n' FAIL "$must" "was not said" >> "$out/report.txt"
done
grep -q '^FAIL' "$out/report.txt" && status=1
if [ $status = 0 ]; then
  echo "[image] compressing (xz)..."
  xz -T0 -1 -f -k "$img"
  ( cd "$out" && sha256sum "$name.xz" > "$name.xz.sha256" )
  row ok image.file "$name.xz: $(du -h "$img.xz" | cut -f1) to download; a disk of at least ${gb} GB; sha256 $(cut -c1-64 "$img.xz.sha256")"
else
  row FAIL image.file "not made: a check failed, and an image that did not pass is not handed out"
fi
rm -f "$img"
echo "SilikOS disk image: $(basename "$iso"), $(date -u +%Y-%m-%dT%H:%MZ)"
cat "$out/report.txt"
ok=$(grep -c '^ok' "$out/report.txt" || true); fail=$(grep -c '^FAIL' "$out/report.txt" || true)
echo "$ok ok, $fail failed"
if [ "$fail" -gt 0 ]; then echo "::error title=SilikOS disk image::$fail of $((ok + fail)) checks failed; the first: $(grep '^FAIL' "$out/report.txt" | head -1 | cut -c7- | tr -s ' ' | cut -c1-240)"
else echo "::notice title=SilikOS disk image::$ok checks ok: installed, nothing of the tests in it, starts on USB with Secure Boot on and on SATA up to its first-start setup"; fi
exit $status
