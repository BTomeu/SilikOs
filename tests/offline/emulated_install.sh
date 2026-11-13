#!/usr/bin/env bash
# tests/offline/emulated_install.sh: the offline ISO's mechanism in a machine WITHOUT KVM and WITHOUT a network
# device, with a reduced set so that an emulated installation ends in an hour: the base's group `core` plus what
# the installer adds (400 packages, 1.1 GB). The whole set in a real virtual machine is .github/workflows/offline.yml.
#   1  a mirror of the reduced set (`silik mirror create --ks`, in an almalinux:9 container with the network)
#   2  tools/build_offline_iso.sh with that mirror and kickstart (SILIK_OFFLINE_KS)
#   3  QEMU (`-nic none`; TCG when there is no /dev/kvm) installs from it onto an empty virtual disk: the ISO's own
#      kickstart plus the lines below, which choose and erase THAT disk (a test's lines, as tests/install/ci.ks.in:
#      never part of an ISO), given to the installer from a second disk image
#   4  the installed disk boots (emulated_boot.py logs in on the serial console and asks a few things)
# What it left on 13/11/2026 (QEMU 8.2.2, TCG, 4 cores): docs/OFFLINE.md. THIS FILE AS A WHOLE HAS NOT BEEN RUN: it
# is the commands of that day, which were typed one by one, put in order.
# Needs docker, xorriso, mtools, qemu-system-x86_64, qemu-img, and what tools/build_offline_iso.sh needs.
#   SILIK_OFFLINE_TOOLS_IMAGE, SILIK_OFFLINE_NET_ARGS: as for container_run.sh
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../.." && pwd)
w=$root/build/offline-emu; rm -rf "$w"; mkdir -p "$w"
tools=${SILIK_OFFLINE_TOOLS_IMAGE:-silik-offline-tools}
read -r -a netargs <<< "${SILIK_OFFLINE_NET_ARGS:-}"
cat > "$w/reduced.ks" <<'KS'
# a reduced set, to try the offline ISO's mechanism in an emulated machine: the base's core group only
url --url=https://repo.almalinux.org/almalinux/9/BaseOS/x86_64/os/
repo --name=AppStream --baseurl=https://repo.almalinux.org/almalinux/9/AppStream/x86_64/os/
selinux --enforcing
firewall --enabled --remove-service=ssh
%packages
@core
%end
KS
docker run --rm "${netargs[@]}" -v "$root:/src:ro" -v "$w:/w" "$tools" \
  python3 /src/packages/silik-tools/files/silik -q mirror create /w/mirror --ks /w/reduced.ks --yes | grep -E '^generation|^silik'
SILIK_OFFLINE_KS=$w/reduced.ks bash "$root/tools/build_offline_iso.sh" "$w/mirror" | tail -2
mv "$root"/build/SilikOS-*-x86_64-offline.iso "$w/reduced-offline.iso"; rm -f "$root"/build/SilikOS-*-x86_64-offline.iso.sha256
cd "$w"
label=$(xorriso -indev reduced-offline.iso -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: *//p')
xorriso -indev reduced-offline.iso -osirrox on -extract /silikos.ks shipped.ks -extract /images/pxeboot/vmlinuz vmlinuz \
  -extract /images/pxeboot/initrd.img initrd.img > /dev/null 2>&1
chmod u+w shipped.ks vmlinuz initrd.img
{ cat shipped.ks; cat <<'KS'

# ---- lines of this emulated test only (a throw-away virtual disk) ----
text
ignoredisk --only-use=vda
zerombr
clearpart --all --initlabel --drives=vda
autopart --type=plain --nohome
lang en_US.UTF-8
keyboard us
timezone UTC --utc
rootpw --plaintext silikos-ci
firstboot --disable
poweroff
%post --nochroot
{ echo; echo "OFFLINE-TEST|net-devices|$(ls /sys/class/net | tr '\n' ' ')"
  echo "OFFLINE-TEST|verify-tail|$(tail -1 /tmp/silikos-mirror-verify.log)"
  grep '^[●▼?·]' /tmp/silikos-mirror-verify.log | sed 's/^/OFFLINE-TEST|verify-row|/'
  echo "OFFLINE-TEST|installed-packages|$(rpm --root /mnt/sysroot -qa | wc -l)"
  echo "OFFLINE-TEST|kernel|$(rpm --root /mnt/sysroot -q kernel)"
  echo "OFFLINE-TEST|repo-mount|$(findmnt -n -o SOURCE,FSTYPE /run/install/repo)"
  echo "OFFLINE-TEST|DONE"; } > /dev/ttyS0
%end
KS
} > ci.ks
dd if=/dev/zero of=ks.img bs=1M count=8 status=none
mformat -i ks.img -v SILIKCI ::
mcopy -i ks.img ci.ks ::/ci.ks
qemu-img create -q -f qcow2 disk.qcow2 16G
if [ -w /dev/kvm ]; then accel=(-enable-kvm -cpu host); else accel=(-accel tcg,thread=multi -cpu max); fi
: > install.log
timeout 170m qemu-system-x86_64 "${accel[@]}" -machine q35 -m 4096 -smp "$(nproc)" -display none -no-reboot \
  -kernel vmlinuz -initrd initrd.img \
  -append "inst.stage2=hd:LABEL=$label inst.ks=hd:LABEL=SILIKCI:/ci.ks inst.text console=ttyS0,115200" \
  -drive file=disk.qcow2,if=virtio,format=qcow2 -drive file=ks.img,if=virtio,format=raw,readonly=on \
  -cdrom reduced-offline.iso -nic none -serial file:install.log -monitor none
tr -d '\r' < install.log | grep -a 'OFFLINE-TEST' || { echo "error: the installation did not report (install.log)" >&2; exit 1; }
python3 "$here/emulated_boot.py" disk.qcow2 boot.log
tr -d '\r' < boot.log | sed 's/\x1b\[[0-9;?]*[A-Za-z]//g' | sed -n '/login: root/,$p' | grep -v '^\s*$'
grep -aq 'BOOT-TEST-DONE' boot.log
