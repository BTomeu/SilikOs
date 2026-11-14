#!/usr/bin/env bash
# tests/install/external.sh ISO [OUT_DIR]: SilikOS installed on an external (USB) disk and started from it, as
# docs/DISK.md ("The system on an external disk, started from the computer's boot menu") and docs/PRIMERA-HORA.md
# tell a person to do it. As tests/install/sealed.sh, whose ways it follows (UEFI firmware with its variables in a
# file, the shipped kickstart of the ISO + CI-only lines, the checks said on the serial port as
# SILIKOS-CI|name|verdict|detail, the disk's passphrase typed on the console by sealed-console.py):
#   1. the installation: a machine with two disks, the computer's own (a small disk with a partition table, an EFI
#      system partition and data: it must come out byte for byte as it went in) and one on a USB controller. The
#      installer is started with the options of the ISO's own menu entry "Install SilikOS ... on an external disk"
#      (read from the ISO: inst.leavebootorder). With it the shipped kickstart hides the computer's own disks
#      from the installer; the test's lines (external.ks.in) name no disk: they clear and use, encrypted, every disk
#      the installer is shown. The firmware's boot entries are read before and after: the order must be the same
#      and no entry gone.
#   2. the starts of the installed disk (external-check.sh, one stage each):
#        first   the same computer (the firmware variables as the installer left them), both disks: the firmware
#                finds the external disk and starts it
#        again   the same once more
#        other   another computer: other firmware variables with Secure Boot on, another USB controller, no other
#                disk. Inside, the two commands `silik disk check` gives for a disk that travels are run
#        sata    a third computer where the disk is on SATA: only the initramfs with every driver starts there
#      and the computer's own disk is compared again at the end.
#   OUT_DIR (default build/external-test): external-install.log, external-<stage>.log, report.txt; exit 0 when no
#   check failed.  SILIK_CI_APPEND, SILIK_CI_MEM, SILIK_CI_CPUS, SILIK_CI_TCG: as tests/install/run.sh.
# Needs qemu-system-x86_64, qemu-img, xorriso, mtools, python3 and OVMF (the package ovmf).
# What it cannot show: a real firmware (its boot menu, its own way of ordering entries), a real USB bridge, and the
# installer's screens: a person ticks the external disk there, here the test's kickstart names it.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../.." && pwd)
iso=${1:?usage: tests/install/external.sh ISO [OUT_DIR]}
out=${2:-$root/build/external-test}
mem=${SILIK_CI_MEM:-4096}; cpus=${SILIK_CI_CPUS:-$(nproc)}; disk_gb=${SILIK_CI_EXTERNAL_DISK:-80}
t_install=${SILIK_CI_INSTALL_MIN:-80}; t_boot=${SILIK_CI_BOOT_MIN:-12}
# the test's own: it protects a disk image that is deleted at the end. No letter that is a key of the boot menu
# (c: its command line, e: its editor): in the desktop mode it is typed blind, and a start slower than expected must
# not land it there
PASSPHRASE=silikos-usb-disk-2718
# SILIK_CI_EXTERNAL_MODE=desktop: another test with the same installation steps. The whole desktop (the shipped
# package set and boot loader line) goes onto the USB disk; the installed disk is started once, the graphical
# way: the passphrase is typed on the keyboard at the boot splash, and the stage `desktop` of external-check.sh
# says what came up. (The default, `small`: the base's core and SilikOS's tools, the console on the serial port,
# four starts on three computers.)
# SILIK_CI_EXTERNAL_MODE=splash: the graphical start alone, in minutes: the small set with the boot splash and
# SilikOS's theme, the shipped boot loader line; one start, the passphrase typed at the splash (stage `splash`).
mode=${SILIK_CI_EXTERNAL_MODE:-small}
case $mode in small|desktop|splash) ;; *) echo "error: SILIK_CI_EXTERNAL_MODE is small, desktop or splash" >&2; exit 2 ;; esac
# (the desktop test has its own list of the checks that must be said)
if [ "$mode" != small ] && [ -z "${SILIK_CI_MUST_FILE:-}" ]; then SILIK_CI_MUST_FILE=$here/must-external-$mode.txt; fi
mkdir -p "$out"; out=$(cd "$out" && pwd); iso=$(cd "$(dirname "$iso")" && pwd)/$(basename "$iso")
work=$(mktemp -d /tmp/silik-external.XXXXXX)
qpid=""
cleanup() { [ -z "$qpid" ] || kill "$qpid" 2> /dev/null || true; rm -rf "$work"; }
trap cleanup EXIT

if [ -w /dev/kvm ]; then accel=(-enable-kvm -cpu host)
elif [ "${SILIK_CI_TCG:-0}" = 1 ]; then accel=(-accel tcg,thread=multi -cpu max); echo "no /dev/kvm: emulating (very slow)"
else echo "error: /dev/kvm is not usable (SILIK_CI_TCG=1 to emulate, many hours)" >&2; exit 2; fi
for tool in qemu-system-x86_64 qemu-img xorriso mformat mcopy python3 sha256sum; do
  command -v "$tool" > /dev/null || { echo "error: $tool is not installed" >&2; exit 2; }
done
first_of() { local f; for f in "$@"; do [ -n "$f" ] && [ -f "$f" ] && { echo "$f"; return 0; }; done; return 1; }
code=$(first_of "${SILIK_CI_OVMF_CODE:-}" /usr/share/OVMF/OVMF_CODE_4M.secboot.fd /usr/share/OVMF/OVMF_CODE.secboot.fd /usr/share/edk2/ovmf/OVMF_CODE.secboot.fd) \
  && vars_sb=$(first_of "${SILIK_CI_OVMF_VARS_SB:-}" /usr/share/OVMF/OVMF_VARS_4M.ms.fd /usr/share/OVMF/OVMF_VARS.ms.fd /usr/share/edk2/ovmf/OVMF_VARS.secboot.fd) \
  && vars_plain=$(first_of "${SILIK_CI_OVMF_VARS:-}" /usr/share/OVMF/OVMF_VARS_4M.fd /usr/share/OVMF/OVMF_VARS.fd /usr/share/edk2/ovmf/OVMF_VARS.fd) \
  || { echo "error: no OVMF firmware found (the package ovmf, or edk2-ovmf); here: $(ls /usr/share/OVMF /usr/share/edk2/ovmf 2> /dev/null | tr '\n' ' ')" >&2; exit 2; }
echo "firmware: $code; Secure Boot on: $vars_sb; off: $vars_plain"
machine=(-machine q35,smm=on -global driver=cfi.pflash01,property=secure,value=on -global ICH9-LPC.disable_s3=1)

label=$(xorriso -indev "$iso" -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: *//p')
[ -n "$label" ] || { echo "error: cannot read the label of $iso" >&2; exit 2; }
xorriso -indev "$iso" -osirrox on -extract /silikos.ks "$work/shipped.ks" -extract /images/pxeboot/vmlinuz "$work/vmlinuz" \
  -extract /images/pxeboot/initrd.img "$work/initrd.img" -extract /EFI/BOOT/grub.cfg "$work/grub.cfg" > /dev/null 2>&1 || true
[ -s "$work/vmlinuz" ] && [ -s "$work/shipped.ks" ] || { echo "error: the ISO has no kernel or no kickstart" >&2; exit 2; }
chmod u+w "$work"/*
clean() { tr -d '\r' < "$1" | sed 's/\x1b\[[0-9;?]*[A-Za-z]//g; s/\x1b[()][A-Z0-9]//g' | grep -a -v '^[[:space:]]*$'; }

: > "$out/report.txt"
row() { printf '%-5s %-44s %s\n' "$1" "$2" "$3" >> "$out/report.txt"; }

# the options of the ISO's own entry for an external disk (its kernel line), without the ones the test replaces:
# where the kickstart is, the screen mode, quiet
entry=$(python3 - "$work/grub.cfg" <<'EOF'
import re, sys
try:
    s = open(sys.argv[1]).read()
except OSError:
    sys.exit(0)
m = re.search(r"^menuentry '[^'\n]*external disk[^'\n]*'[^\n]*\{\n((?:[^\n]*\n)*?)\}", s, re.M)
if m:
    k = re.search(r"^\s*linux(?:efi)?\s+\S+\s+(.*)$", m.group(1), re.M)
    if k:
        print(" ".join(a for a in k.group(1).split() if not a.startswith(("inst.ks=", "inst.stage2=")) and a not in ("quiet", "rhgb")))
EOF
)
case " $entry " in
  *" inst.leavebootorder "*) row ok external.install.entry "the ISO's entry for an external disk gives the installer: $entry" ;;
  *) row FAIL external.install.entry "the ISO's UEFI menu has no entry for an external disk with inst.leavebootorder (found: '${entry:-nothing}'); the test goes on with the option given by hand"
     entry="inst.leavebootorder" ;;
esac

# the kickstart of the test: the ISO's own (its screen-mode lines, its boot loader line and its desktop taken out:
# the base's core and the SilikOS packages this test is about) + the CI-only lines of external.ks.in
python3 - "$work/shipped.ks" "$here/external.ks.in" "$here/external-check.sh" "$PASSPHRASE" "$mode" "${SILIK_CI_EXTERNAL_DEBUG:-}" > "$work/external.ks" <<'EOF'
import re, sys
shipped, extra, check, passphrase, mode, debug = sys.argv[1:7]
# SILIK_CI_EXTERNAL_DEBUG=1 (the graphical modes): the start is the graphical one still (the splash on the screen, the
# passphrase asked there), and what the splash program and systemd say goes to the serial port, for a start that
# does not arrive
DEBUG = ('bootloader --append="vsyscall=xonly console=tty0 console=ttyS0,115200 plymouth.ignore-serial-consoles '
         'plymouth.debug=stream:/dev/ttyS0 systemd.show_status=1 rd.systemd.show_status=1"')
def graphical(extra):
    lines = [l for l in extra.splitlines() if not l.startswith("bootloader ")]
    if debug:
        lines.insert(lines.index("zerombr"), DEBUG)
    return "\n".join(lines) + "\n"
ks = "\n".join(l for l in open(shipped).read().splitlines() if l not in ("graphical", "firstboot --enable")) + "\n"
extra = open(extra).read()
if mode == "desktop":
    # the shipped package set, services and boot loader line stay; the test's own boot loader line (the console on
    # the serial port, no splash) is left out: this installation starts as a person's does
    extra = graphical(extra)
elif mode == "splash":
    # the small set with the boot splash and SilikOS's theme; the shipped boot loader line stays, the test's goes
    extra = graphical(extra)
    small = ["@core", "silik-tools", "silikos-security", "silikos-branding", "plymouth", "plymouth-scripts", "plymouth-theme-spinner",
             "cryptsetup", "mokutil", "efibootmgr"]
    ks = re.sub(r"(?ms)^%packages.*?^%end\n", "%packages\n" + "\n".join(small) + "\n%end\n", ks, count=1)
    ks = "\n".join(l for l in ks.splitlines() if not l.startswith(("services ", "xconfig "))) + "\n"
else:
    shipped_set = re.search(r"(?ms)^%packages.*?^%end\n", ks).group(0).split()
    small = ["@core", "silik-tools", "silikos-security", "cryptsetup", "mokutil", "efibootmgr"] + [p for p in ("silikos-power", "usbguard") if p in shipped_set]
    ks = re.sub(r"(?ms)^%packages.*?^%end\n", "%packages\n" + "\n".join(small) + "\n%end\n", ks, count=1)
    ks = "\n".join(l for l in ks.splitlines() if not l.startswith(("services ", "xconfig ", "bootloader "))) + "\n"
print(ks + extra.replace("@PASSPHRASE@", passphrase).replace("@CHECK@", open(check).read().rstrip("\n")))
EOF
cp "$work/external.ks" "$out/external.ks"
dd if=/dev/zero of="$work/ks.img" bs=1M count=8 status=none
mformat -i "$work/ks.img" -v SILIKCI ::
mcopy -i "$work/ks.img" "$work/external.ks" ::/ci.ks

# the computer's own disk: a partition table, an EFI system partition with another system's loader in it (a file
# of that name: the firmware cannot start it, which is all the test needs), and data
internal="$work/internal.img"
truncate -s 512M "$internal"
python3 - "$internal" <<'EOF'
# a GUID partition table written here (no partitioning tool is needed on the host): an EFI system partition of
# 128 MiB at 1 MiB, then a partition for the system up to the end
import binascii, struct, sys, uuid
path, sec = sys.argv[1], 512
with open(path, "r+b") as f:
    f.seek(0, 2); total = f.tell() // sec; last = total - 1
    parts = (("c12a7328-f81f-11d2-ba4b-00a0c93ec93b", "5111c0de-0000-4000-8000-00000000e5b0", 2048, 2048 + 262144 - 1, "ESP"),
             ("0fc63daf-8483-4772-8e79-3d69d8477de4", "5111c0de-0000-4000-8000-0000000051f5", 264192, last - 34, "system"))
    ent = b"".join(uuid.UUID(t).bytes_le + uuid.UUID(u).bytes_le + struct.pack("<QQQ", a, b, 0) + n.encode("utf-16-le").ljust(72, b"\0")
                   for t, u, a, b, n in parts).ljust(128 * 128, b"\0")
    def header(me, other, table):
        h = struct.pack("<8sIIIIQQQQ16sQIII", b"EFI PART", 0x10000, 92, 0, 0, me, other, 34, last - 33,
                        uuid.UUID("5111c0de-0000-4000-8000-00000000d15c").bytes_le, table, 128, 128, binascii.crc32(ent) & 0xffffffff)
        return h[:16] + struct.pack("<I", binascii.crc32(h) & 0xffffffff) + h[20:]
    mbr = bytearray(sec)
    mbr[446:462] = struct.pack("<B3sB3sII", 0, b"\x00\x02\x00", 0xEE, b"\xff\xff\xff", 1, min(last, 0xffffffff))
    mbr[510:512] = b"\x55\xaa"
    f.seek(0); f.write(bytes(mbr)); f.write(header(1, last, 2).ljust(sec, b"\0")); f.write(ent)
    f.seek((last - 32) * sec); f.write(ent); f.write(header(last, 1, last - 32).ljust(sec, b"\0"))
EOF
mformat -i "$internal@@1M" -T 262144 -v OTHERESP ::
mmd -i "$internal@@1M" ::/EFI ::/EFI/Other
head -c 300000 /dev/urandom > "$work/loader"; mcopy -i "$internal@@1M" "$work/loader" ::/EFI/Other/loader.efi
dd if=/dev/urandom of="$internal" bs=1M seek=129 count=64 conv=notrunc status=none
sum0=$(sha256sum "$internal" | cut -d' ' -f1)
echo "the computer's own disk: 512 MB, sha256 $sum0"
same_internal() {   # same_internal NAME WHEN
  local s; s=$(sha256sum "$internal" | cut -d' ' -f1)
  if [ "$s" = "$sum0" ]; then row ok "$1" "the computer's own disk is byte for byte what it was, $2 (sha256 ${s:0:16}...)"
  else row FAIL "$1" "the computer's own disk CHANGED $2: sha256 was $sum0, is $s"; fi
}

# ---------------------------------------------------------------------------------------------- 1. the installation
install() {
  local rc=0 n=0
  qemu-img create -q -f qcow2 "$out/external.qcow2" "${disk_gb}G"
  cp "$vars_plain" "$work/vars-a.fd"
  echo "[external] installing from $(basename "$iso") under UEFI onto a USB disk (${disk_gb} GB), $cpus CPUs, $mem MB; the installer's console: $out/external-install.log"
  : > "$out/external-install.log"
  timeout "${t_install}m" qemu-system-x86_64 "${accel[@]}" "${machine[@]}" -m "$mem" -smp "$cpus" -display none -no-reboot \
    -drive "if=pflash,format=raw,unit=0,readonly=on,file=$code" -drive "if=pflash,format=raw,unit=1,file=$work/vars-a.fd" \
    -kernel "$work/vmlinuz" -initrd "$work/initrd.img" \
    -append "inst.stage2=hd:LABEL=$label inst.ks=hd:LABEL=SILIKCI:/ci.ks $entry inst.text console=ttyS0,115200 ${SILIK_CI_APPEND:-}" \
    -drive "file=$internal,if=virtio,format=raw" -drive "file=$work/ks.img,if=virtio,format=raw,readonly=on" \
    -device qemu-xhci,id=xhci -drive "if=none,id=ext,file=$out/external.qcow2,format=qcow2,discard=unmap" \
    -device usb-storage,bus=xhci.0,drive=ext,serial=SILIKEXT \
    -cdrom "$iso" -nic user,model=virtio-net-pci -serial "file:$out/external-install.log" -monitor none &
  qpid=$!
  ( while kill -0 $qpid 2> /dev/null; do
      sleep 20; n=$((n + 1))
      if grep -q "Please make a selection from the above" "$out/external-install.log"; then    # it asks: it will never go on
        echo "error: [external] the installer stopped at its summary and waits for an answer:" >&2
        clean "$out/external-install.log" | grep -B14 "Please make a selection" | tail -16 >&2
        pkill -P $qpid qemu-system-x86 2> /dev/null; kill $qpid 2> /dev/null
        break
      fi
      [ $((n % 6)) = 0 ] && echo "  ... $(clean "$out/external-install.log" | tail -1 | cut -c1-150)"
    done ) &
  local watch=$!
  disown $watch
  wait $qpid || rc=$?
  qpid=""
  pkill -P $watch 2> /dev/null || true; kill $watch 2> /dev/null || true
  echo "::group::[external] what the installer saw: the disks, the firmware's entries before and after"
  clean "$out/external-install.log" | grep -a '^SILIKOS-E' | cut -c1-300 || true
  echo "::endgroup::"
  if [ $rc -ne 0 ]; then
    echo "error: [external] the installation did not finish (exit $rc; 124 = time limit of $t_install min). Last lines of its console:" >&2
    clean "$out/external-install.log" | tail -40 >&2
    return 1
  fi
  echo "[external] installed: the disk image holds $(du -h "$out/external.qcow2" | cut -f1)"
}

# what the installer said of the disks and of the firmware's entries, as rows
judge_install() {
  python3 - "$out/external-install.log" >> "$out/report.txt" <<'EOF'
import re, sys
log = open(sys.argv[1], "rb").read().replace(b"\r", b"").decode("utf-8", "replace")
def row(verdict, name, detail):
    print("%-5s %-44s %s" % (verdict, "external.install." + name, detail.replace("\n", " ")[:400]))
m = re.search(r"^SILIKOS-EXT\|usb-disks\|(\d+)\|(.*)$", log, re.M)
d = re.search(r"^SILIKOS-EXT\|disks\|(.*)$", log, re.M)
if m:
    row("ok" if m.group(1) == "1" else "FAIL", "one-usb-disk", "the installer saw %s disk(s) on USB (%s) among: %s" % (m.group(1), m.group(2).strip() or "none",
        "; ".join("%s %s %s %s" % (n, t, tr or "(no transport said)", sz) for n, t, tr, sz in re.findall(r'NAME="([^"]*)" TYPE="([^"]*)" TRAN="([^"]*)" SIZE="([^"]*)"', d.group(1) if d else "")) or "?"))
else:
    row("FAIL", "one-usb-disk", "the installer did not say which disks it saw")
h = re.search(r"^SILIKOS-EXT\|hidden\|(.*)$", log, re.M)
hidden = h.group(1).strip() if h else ""
seen = re.findall(r'NAME="([^"]*)" TYPE="([^"]*)" TRAN="([^"]*)" SIZE="([^"]*)"', d.group(1) if d else "")
own = sorted(n for n, typ, tran, size in seen if typ == "disk" and tran != "usb" and not n.startswith("zram"))
want = "ignoredisk --drives=" + ",".join(own)
row("ok" if own and sorted(hidden.replace("ignoredisk --drives=", "").split(",")) == own and hidden.startswith("ignoredisk --drives=") else "FAIL", "own-disks-hidden",
    "the shipped kickstart told the installer: '%s' (the disks that are not on USB: %s)" % (hidden or "nothing", ", ".join(own) or "none seen"))
lay = re.search(r"^SILIKOS-EXT\|layout\|(.*)$", log, re.M)
row("info", "layout", lay.group(1) if lay else "not said")
def entries(when):
    lines = re.findall(r"^SILIKOS-EFI\|%s\|(.*)$" % when, log, re.M)
    if "end" not in lines:
        return None, None
    order = next((l[len("BootOrder: "):] for l in lines if l.startswith("BootOrder: ")), None)
    return order, {l[:8]: l[9:].strip() for l in lines if re.match(r"Boot[0-9A-F]{4} ", l)}
o0, e0 = entries("pre")
o1, e1 = entries("post")
if e0 is None or e1 is None:
    row("FAIL", "boot-order-kept", "the firmware's entries were not read %s the installation" % ("before" if e0 is None else "after"))
    row("FAIL", "no-entry-removed", "the firmware's entries were not read")
else:
    row("ok" if o0 == o1 else "FAIL", "boot-order-kept", "the firmware's boot order before the installation: %s; after: %s" % (o0, o1))
    gone = ["%s %s" % (k, v) for k, v in sorted(e0.items()) if e1.get(k) != v]
    row("ok" if not gone else "FAIL", "no-entry-removed", "the %d entries there were before are there after" % len(e0) if not gone else "gone or changed: " + "; ".join(gone))
    new = ["%s %s%s" % (k, v, "" if k[4:] in (o1 or "").split(",") else " (not in the order)") for k, v in sorted(e1.items()) if k not in e0]
    row("info", "entry-added", "; ".join(new) if new else "the installer added no entry")
EOF
}

# rows_of NAME: the checks the system said on the console of the start NAME, as rows of the report
# (rows.py: every check whole and counted; a line the serial port lost is a FAIL here, not a silence)
rows_of() {
  python3 "$here/rows.py" --name "external.$1.rows" "$out/external-$1.log" | while IFS='|' read -r _ check verdict detail; do
    row "$verdict" "$check" "$detail"
  done || row FAIL "external.$1.reader" "rows.py did not get to the end of the log: rows are missing"
}

# ---------------------------------------------------------------------------------------------- 2. the starts
# start NAME VARS_FILE MINUTES DISK_ARGS...: the installed disk starts once in a machine with these firmware
# variables and these disks; external-check.sh runs its stage NAME there and powers off. The passphrase is typed
# on the console whenever the start asks for it.
start() {
  local name=$1 vars=$2 limit=$3 i fw; shift 3
  dd if=/dev/zero of="$work/stage.img" bs=1M count=4 status=none
  mformat -i "$work/stage.img" -v SILIKCI ::
  echo "$name" > "$work/stage"; mcopy -i "$work/stage.img" "$work/stage" ::/stage
  rm -f "$work/ser.sock"
  : > "$out/external-$name.log"
  echo "[external] start '$name': $(basename "$vars"); the console: $out/external-$name.log"
  qemu-system-x86_64 "${accel[@]}" "${machine[@]}" -m "$mem" -smp "$cpus" -display none \
    -drive "if=pflash,format=raw,unit=0,readonly=on,file=$code" -drive "if=pflash,format=raw,unit=1,file=$vars" \
    "$@" -drive "file=$work/stage.img,if=virtio,format=raw,readonly=on" \
    -nic user,model=virtio-net-pci -monitor none \
    -chardev "socket,id=ser,path=$work/ser.sock,server=on,wait=off,logfile=$out/external-$name.log" -serial chardev:ser &
  qpid=$!
  python3 "$here/sealed-console.py" "$work/ser.sock" --passphrase "$PASSPHRASE" --limit $((limit * 60)) > "$work/$name.json" || true
  for i in $(seq 1 30); do kill -0 $qpid 2> /dev/null || break; sleep 2; done      # (it powers itself off after its stage)
  kill $qpid 2> /dev/null || true; wait $qpid 2> /dev/null || true; qpid=""
  echo "::group::[external] the console of '$name': what the firmware started, what the start asked"
  clean "$out/external-$name.log" | grep -a -i 'BdsDxe\|enter .* for disk\|falling back\|Cryptography Setup\|SILIKOS-CI|END\|emergency\|Reset System\|dracut-initqueue.*timeout' | cut -c1-220 | tail -40 || true
  if ! tr -d '\r' < "$out/external-$name.log" | grep -a -q "^SILIKOS-CI|END|$name"; then
    echo "--- the stage did not get to its end; the last lines of the console:"
    clean "$out/external-$name.log" | tail -30 | cut -c1-220 || true
  fi
  echo "::endgroup::"
  # what the firmware started (its own lines on the console), for the report
  fw=$(clean "$out/external-$name.log" | grep -a 'BdsDxe: starting' | sed 's/BdsDxe: starting //' | cut -c1-110 | tr '\n' ';' | cut -c1-330) || fw="the firmware said nothing of what it started"
  row info "external.$name.firmware" "$fw"
  rows_of "$name"
  python3 - "$work/$name.json" "$name" >> "$out/report.txt" <<'EOF'
import json, sys
path, name = sys.argv[1:3]
try:
    r = json.load(open(path))
except (OSError, ValueError):
    r = {"asked": [], "end": "no result", "why": "sealed-console.py gave nothing", "marks": []}
done = r["end"] == "closed" and name in r["marks"]
def row(verdict, check, detail):
    print("%-5s %-44s %s" % (verdict, "external.%s.%s" % (name, check), detail))
if done:
    ok = "passphrase" in r["asked"]
    row("ok" if ok else "FAIL", "passphrase-asked", "the start asked: %s" % (", ".join(r["asked"]) or "nothing; the disk opened WITHOUT its passphrase"))
row("ok" if done else "FAIL", "finished", "the disk started there, the stage ran and the machine powered off" if done else
    "the start did not get to the stage's end: the console ended with '%s'%s" % (r["end"], " (%s)" % r["why"] if r.get("why") else ""))
EOF
  grep -q "^ok    external\.$name\.finished " "$out/report.txt"
}

# start_graphical STAGE MINUTES DISK_ARGS...: the installed system starts the graphical way (the modes desktop and
# splash). Nothing of that start is on the serial port (the shipped boot loader line): the screen is looked at every
# ten seconds, and the passphrase is typed on the keyboard when something is on it (the boot splash and its
# question), or 90 s after the firmware started the disk whatever it shows; again every 40 s while the stage has not
# ended, six times at most (a passphrase typed at the login screen later does nothing). The screen before each
# typing, five minutes in and at the end is kept (screen-*.png), read (OCR, when tesseract is here) and printed as
# a coarse picture in letters: a start that does not arrive must be seen, not guessed.
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
start_graphical() {
  local stage=$1 limit=$2 i typed=0 t0 now last=-100 lit shots=0 five=0; shift 2
  dd if=/dev/zero of="$work/stage.img" bs=1M count=4 status=none
  mformat -i "$work/stage.img" -v SILIKCI ::
  echo "$stage" > "$work/stage"; mcopy -i "$work/stage.img" "$work/stage" ::/stage
  rm -f "$work/mon.sock"
  : > "$out/external-$stage.log"
  echo "[external] start '$stage': the graphical way; the firmware's lines and the checks: $out/external-$stage.log"
  qemu-system-x86_64 "${accel[@]}" "${machine[@]}" -m "$mem" -smp "$cpus" -display none -vga std \
    -drive "if=pflash,format=raw,unit=0,readonly=on,file=$code" -drive "if=pflash,format=raw,unit=1,file=$work/vars-a.fd" \
    "$@" -drive "file=$work/stage.img,if=virtio,format=raw,readonly=on" \
    -nic user,model=virtio-net-pci -monitor "unix:$work/mon.sock,server,nowait" -serial "file:$out/external-$stage.log" &
  qpid=$!
  for i in $(seq 1 50); do [ -S "$work/mon.sock" ] && break; sleep 0.2; done
  monitor() { python3 - "$work/mon.sock" "$@" 2> /dev/null <<'EOF' || true
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); time.sleep(0.3); s.recv(65536)
names = {"-": "minus", " ": "spc", ".": "dot", "/": "slash"}
if sys.argv[2] == "type":
    for c in sys.argv[3]:
        k = names.get(c, c.lower()); s.send(("sendkey %s\n" % ("shift-" + k if c.isupper() else k)).encode()); time.sleep(0.15)
    s.send(b"sendkey ret\n"); time.sleep(0.5)
else:
    s.send((sys.argv[2] + "\n").encode()); time.sleep(float(sys.argv[3]) if len(sys.argv) > 3 else 0.5)
EOF
  }
  # look NAME WHY: the screen now, kept as screen-NAME.png, read and printed
  look() {
    rm -f "$work/screen.ppm"
    monitor "screendump $work/screen.ppm" 2.5
    echo "::group::[external] the screen, $2"
    picture "$work/screen.ppm" | grep -v '^lit ' || true
    if command -v convert > /dev/null && [ -s "$work/screen.ppm" ]; then
      convert "$work/screen.ppm" "$out/screen-$1.png" 2> /dev/null || true
      if command -v tesseract > /dev/null; then
        convert "$work/screen.ppm" -colorspace Gray -resize 200% "$work/ocr.png" 2> /dev/null && tesseract "$work/ocr.png" "$work/ocr" --psm 6 > /dev/null 2>&1 \
          && { echo "--- read from it:"; grep -v '^[[:space:]]*$' "$work/ocr.txt" | head -30 | cut -c1-160; cp "$work/ocr.txt" "$out/screen-$1.txt"; } || true
      fi
    fi
    echo "::endgroup::"
  }
  t0=$(date +%s)
  for i in $(seq 1 $((limit * 6))); do
    sleep 10
    kill -0 $qpid 2> /dev/null || break
    tr -d '\r' < "$out/external-$stage.log" | grep -a -q "^SILIKOS-CI|END|$stage" && break
    now=$(( $(date +%s) - t0 ))
    if [ $five = 0 ] && [ $now -ge 300 ]; then five=1; look five "five minutes after the start"; fi
    [ $typed -lt 6 ] && [ $((now - last)) -ge 40 ] && grep -a -q 'BdsDxe: starting' "$out/external-$stage.log" || continue
    rm -f "$work/peek.ppm"; monitor "screendump $work/peek.ppm" 2
    lit=$(picture "$work/peek.ppm" | sed -n 's/^lit //p' | tail -1)
    if [ "${lit:-0}" -gt 0 ] && [ $now -ge 25 ] || [ $now -ge 90 ]; then
      typed=$((typed + 1)); last=$now
      look "typing-$typed" "$now s after the start, before the passphrase is typed ($typed)"
      monitor type "$PASSPHRASE"
      echo "  ... the passphrase typed on the keyboard ($typed), $now s after the start"
    fi
  done
  if kill -0 $qpid 2> /dev/null; then look last "at the end ($(( $(date +%s) - t0 )) s after the start)"; fi
  for i in $(seq 1 30); do kill -0 $qpid 2> /dev/null || break; sleep 2; done
  kill $qpid 2> /dev/null || true; wait $qpid 2> /dev/null || true; qpid=""
  echo "::group::[external] the console of '$stage': what the firmware started"
  clean "$out/external-$stage.log" | grep -a -i 'BdsDxe\|SILIKOS-CI|END' | cut -c1-220 | tail -12 || true
  echo "::endgroup::"
  if [ -n "${SILIK_CI_EXTERNAL_DEBUG:-}" ]; then
    echo "::group::[external] the serial port of '$stage' (debug): the splash program and systemd, the lines that matter and the last ones"
    clean "$out/external-$stage.log" | grep -a -i 'error\|fail\|could not\|cannot\|crash\|segfault\|password\|passphrase\|renderer\|theme\|two-step\|cryptsetup\|Reached target\|Started\|emergency\|timed out' | cut -c1-200 | head -150 || true
    echo "--- the last lines:"
    clean "$out/external-$stage.log" | tail -60 | cut -c1-200 || true
    echo "::endgroup::"
  fi
  rows_of "$stage"
  if tr -d '\r' < "$out/external-$stage.log" | grep -a -q "^SILIKOS-CI|END|$stage"; then
    row ok "external.$stage.passphrase-at-the-splash" "the passphrase typed on the keyboard at the graphical start opened the disk (typed $typed time(s); screen-typing-N.png are the screens before each)"
    row ok "external.$stage.finished" "the system started from the USB disk the graphical way, the stage ran and the machine powered off"
  else
    row FAIL "external.$stage.finished" "the graphical start did not get to the stage's end in $limit min (the passphrase was typed $typed time(s); the screens are in the log)"
    return 1
  fi
}

status=0
usb_a=(-device qemu-xhci,id=xhci -drive "if=none,id=ext,file=$out/external.qcow2,format=qcow2,discard=unmap" -device usb-storage,bus=xhci.0,drive=ext,serial=SILIKEXT)
usb_b=(-device nec-usb-xhci,id=xhci -drive "if=none,id=ext,file=$out/external.qcow2,format=qcow2,discard=unmap" -device usb-storage,bus=xhci.0,drive=ext,serial=SILIKEXT)
sata=(-drive "if=none,id=ext,file=$out/external.qcow2,format=qcow2,discard=unmap" -device ide-hd,drive=ext,bus=ide.0)
own=(-drive "file=$internal,if=virtio,format=raw")
if [ "$mode" != small ]; then
  if install; then
    row ok external.install.finished "an encrypted installation ($mode) onto the USB disk finished under UEFI"
    judge_install
    same_internal external.install.own-disk-untouched "after the installation"
    start_graphical "$mode" $((t_boot * 2)) "${own[@]}" "${usb_a[@]}" || status=1
    same_internal "external.$mode.own-disk-untouched" "after the graphical start from the external disk"
  else
    row FAIL external.install.finished "did not finish: $(clean "$out/external-install.log" | grep -i "error\|\[!\]" | tail -2 | tr '\n' ' ' | cut -c1-200)"
    status=1
  fi
elif install; then
  row ok external.install.finished "an encrypted installation onto the USB disk finished under UEFI"
  judge_install
  same_internal external.install.own-disk-untouched "after the installation"
  # the same computer: the firmware variables as the installer left them, its own disk beside the external one
  if start first "$work/vars-a.fd" $((t_boot * 2)) "${own[@]}" "${usb_a[@]}"; then
    start again "$work/vars-a.fd" "$t_boot" "${own[@]}" "${usb_a[@]}" || status=1
    same_internal external.again.own-disk-untouched "after two starts from the external disk"
    # another computer: Secure Boot on, another USB controller, nothing else
    cp "$vars_sb" "$work/vars-b.fd"
    if start other "$work/vars-b.fd" $((t_boot * 2)) "${usb_b[@]}" && grep -q "^ok    external\.other\.initramfs-generic " "$out/report.txt"; then
      cp "$vars_plain" "$work/vars-c.fd"
      start sata "$work/vars-c.fd" "$t_boot" "${sata[@]}" || status=1
    else
      status=1; row FAIL external.sata.finished "not started: the initramfs with every driver was not made in the start before"
    fi
  else
    status=1
    echo "error: [external] the first start from the external disk did not finish. Last lines of its console:" >&2
    clean "$out/external-first.log" | tail -40 >&2
  fi
else
  row FAIL external.install.finished "did not finish: $(clean "$out/external-install.log" | grep -i "error\|\[!\]" | tail -2 | tr '\n' ' ' | cut -c1-200)"
  status=1
fi
rm -f "$out/external.qcow2"

# every check of the list must be there with a verdict (tests/install/must-external.txt): one that was skipped,
# swallowed by the shell or lost on the way is a FAIL of the report, not a row that is simply not there
# (SILIK_CI_MUST_FILE: another list, for the unit tests' stand-in machines)
mustf=${SILIK_CI_MUST_FILE:-$here/must-external.txt}
if [ -f "$mustf" ]; then
  while read -r must; do
    case $must in ''|'#'*) continue ;; esac
    awk -v m="$must" '($1 == "ok" || $1 == "FAIL") && $2 == m { f = 1 } END { exit !f }' "$out/report.txt" \
      || printf '%-5s %-44s %s\n' FAIL "$must" "was not said (it is in $(basename "$mustf"))" >> "$out/report.txt"
  done < "$mustf"
fi
echo "SilikOS external disk test: $(basename "$iso"), $(date -u +%Y-%m-%dT%H:%MZ)"
cat "$out/report.txt"
grep -q '^FAIL' "$out/report.txt" && status=1
echo "$(grep -c '^ok' "$out/report.txt" || true) ok, $(grep -c '^FAIL' "$out/report.txt" || true) failed"

# one line for each part: what its checks said (an annotation of the run in GitHub Actions)
step() {   # step NAME TITLE
  local rx ok fail first
  rx="^(ok|FAIL|info) +external\.$1(\.| )"
  ok=$(grep -E "$rx" "$out/report.txt" | grep -c '^ok' || true)
  fail=$(grep -E "$rx" "$out/report.txt" | grep -c '^FAIL' || true)
  first=$(grep -E "$rx" "$out/report.txt" | grep '^FAIL' | head -1 | cut -c7- | tr -s ' ' | cut -c1-240 || true)
  if [ "$fail" -gt 0 ]; then echo "::error title=external $1: $2::$fail of $((ok + fail)) checks failed; the first: $first"
  elif [ "$ok" -gt 0 ]; then echo "::notice title=external $1: $2::$ok checks ok"
  else echo "::error title=external $1: $2::it did not run (see report.txt and the consoles in the artifact external-test)"; status=1; fi
}
step install "installed onto the USB disk; the boot order and the computer's own disk kept"
if [ "$mode" = desktop ]; then
  step desktop "the whole desktop on the USB disk: the passphrase at the boot splash, the login screen"
elif [ "$mode" = splash ]; then
  step splash "the graphical start alone: the passphrase at the boot splash"
else
  step first "the same computer starts the external disk"
  step again "the same computer again: nothing changes again"
  step other "another computer, Secure Boot on; the initramfs with every driver"
  step sata "a third computer, the disk on SATA"
fi
# for the documents: the informative rows (what the firmware started, its entries after each start)
echo "::group::[external] the informative rows"
grep '^info' "$out/report.txt" | cut -c1-420 || true
echo "::endgroup::"
exit $status
