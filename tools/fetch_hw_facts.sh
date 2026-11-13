#!/bin/bash
# SilikOS — the facts tools/gen_hwdb.py works from: which devices the base's kernel has a driver for.
#   bash tools/fetch_hw_facts.sh [OUT]            (default build/hwfacts; about 6 MB of text)
# Everything is read from packages, nothing is installed on this machine and no hardware is touched:
#   el9/ARCH/      AlmaLinux 9's kernel-core, kernel-modules-core, kernel-modules, kernel-modules-extra, for x86_64 and
#                  aarch64 (`dnf --forcearch`, no emulation): the modules of each package, `depmod` on the extracted
#                  tree (modules.alias, modules.dep), modules.builtin, the config, the firmware each module names
#   upstream/      the same of Fedora 45's kernel (Linux 7.2.11, x86_64): what a current upstream kernel claims
#   fw/            the files of the base's firmware packages; the kernel package's changelog
#   set/           the kickstart's package set resolved by dnf in an empty root (which packages get installed)
#   ids/           pci.ids and usb.ids (names), src/ the source files whose tables the generator reads
# One package at a time: downloaded, read, deleted (they are 20-100 MB each). Needs docker or podman and the network
# (repo.almalinux.org, dl.fedoraproject.org, raw.githubusercontent.com, gitlab.com).
#   SILIK_CA=FILE  a CA bundle the container must trust (a proxy that re-signs TLS); HTTPS_PROXY is passed through
#   SILIK_ENGINE   docker | podman (default: the one found)
set -euo pipefail
out=$(mkdir -p "${1:-build/hwfacts}" && cd "${1:-build/hwfacts}" && pwd)
engine=${SILIK_ENGINE:-$(command -v docker > /dev/null && echo docker || echo podman)}
fedora=45
fkernel=7.2.11-300.fc45.x86_64
uptag=v7.2
eltag=kernel-5.14.0-687.el9

inside() {   # runs "$1" in an AlmaLinux 9 container with OUT at /out, the repositories asked by their base address
  local ca=()
  [ -n "${SILIK_CA:-}" ] && ca=(-v "$SILIK_CA:/etc/pki/ca-trust/source/anchors/silik-ca.crt:ro")
  "$engine" run --rm --network host -e HTTPS_PROXY="${HTTPS_PROXY:-}" -e https_proxy="${HTTPS_PROXY:-}" \
    "${ca[@]}" -v "$out:/out" almalinux:9 bash -euc '
update-ca-trust
sed -i -e "s|^mirrorlist=|#mirrorlist=|" -e "s|^# *baseurl=|baseurl=|" /etc/yum.repos.d/almalinux*.repo
dnf -q -y install dnf-plugins-core cpio kmod xz zstd > /dev/null
'"$1"
}

for arch in x86_64 aarch64; do
  echo "== the base kernel, $arch"
  inside '
arch='$arch'; o=/out/el9/$arch; rm -rf $o; mkdir -p $o /root/tree /root/rpm
for p in kernel-core kernel-modules-core kernel-modules kernel-modules-extra; do
  cd /root/rpm
  dnf -q --forcearch $arch download --arch $arch $p
  f=$(ls $p-5*.rpm)
  rpm -qp --qf "%{NAME} %{VERSION}-%{RELEASE}.%{ARCH} %{SIZE} built %{BUILDTIME:date}\n" $f >> $o/packages.txt
  rpm -qp --requires $f > $o/requires.$p.txt; rpm -qp --recommends $f > $o/recommends.$p.txt
  mkdir -p /root/x && cd /root/x
  rpm2cpio /root/rpm/$f | cpio -idm --quiet "./lib/modules/*" "./etc/modprobe.d/*" 2> /dev/null || :
  rm -f /root/rpm/$f
  cp -a /root/x/. /root/tree/
  (find . -name "*.ko*" | sed "s|.*/||; s|\.ko.*||" | sort) > $o/modules.$p.txt
  (find ./etc -type f 2> /dev/null | sort | while read e; do echo "== $p $e"; cat "$e"; done) >> $o/modprobe.d.txt
  rm -rf /root/x
done
ver=$(ls /root/tree/lib/modules); echo "$ver" > $o/version.txt
depmod -b /root/tree $ver
m=/root/tree/lib/modules/$ver
cp $m/modules.alias $m/modules.builtin $m/modules.dep $m/config $o/
find $m -name "*.ko*" | sort | while read k; do
  n=$(basename $k | sed "s|\.ko.*||"); modinfo -F firmware $k 2> /dev/null | sed "s|^|$n\t|"
done > $o/modules.firmware.txt
'
done

echo "== the upstream kernel: Fedora $fedora, $fkernel"
inside '
o=/out/upstream; rm -rf $o; mkdir -p $o /root/tree /root/rpm
base=https://dl.fedoraproject.org/pub/fedora/linux/releases/'$fedora'/Everything/x86_64/os/Packages/k
for p in kernel-core kernel-modules-core kernel-modules kernel-modules-extra; do
  cd /root/rpm; f=$p-'$fkernel'.rpm
  curl -sS -f -O $base/$f
  echo "$f $(stat -c %s $f) sha256 $(sha256sum $f | cut -d" " -f1)" >> $o/packages.txt
  mkdir -p /root/x && cd /root/x
  rpm2cpio /root/rpm/$f | cpio -idm --quiet "./lib/modules/*" 2> /dev/null || :
  rm -f /root/rpm/$f
  cp -a /root/x/. /root/tree/
  (find . -name "*.ko*" | sed "s|.*/||; s|\.ko.*||" | sort) > $o/modules.$p.txt
  rm -rf /root/x
done
ver=$(ls /root/tree/lib/modules); echo "$ver" > $o/version.txt
depmod -b /root/tree $ver
m=/root/tree/lib/modules/$ver
cp $m/modules.alias $m/modules.builtin $m/modules.dep $m/config $o/
find $m -name "*.ko*" | sort | while read k; do
  n=$(basename $k | sed "s|\.ko.*||"); modinfo -F firmware $k 2> /dev/null | sed "s|^|$n\t|"
done > $o/modules.firmware.txt
'

echo "== firmware packages, the kernel changelog, the kickstart's set"
inside '
mkdir -p /out/fw /out/set /out/libfprint /root/r && cd /root/r
dnf -q download kernel-core && rpm -qp --changelog kernel-core-*.rpm > /out/fw/kernel.changelog.txt; rm -f kernel-core*.rpm
for p in linux-firmware alsa-sof-firmware iwl7260-firmware iwl3160-firmware libertas-sd8787-firmware netronome-firmware \
         alsa-firmware microcode_ctl; do
  dnf -q repoquery --latest-limit 1 -l $p.x86_64 $p.noarch > /out/fw/files.$p.txt 2> /dev/null || :
done
dnf -q repoquery --latest-limit 1 --qf "%{name} %{version}-%{release} %{reponame}" linux-firmware alsa-sof-firmware \
  microcode_ctl hwdata libfprint fprintd mesa-dri-drivers almalinux-release-nvidia-driver elrepo-release > /out/fw/versions.txt
dnf -q download systemd-udev && rpm2cpio systemd-udev-*.rpm | cpio -idm --quiet "*60-autosuspend-fingerprint-reader.hwdb"
cp usr/lib/udev/hwdb.d/60-autosuspend-fingerprint-reader.hwdb /out/libfprint/
rpm -qp --qf "%{NAME} %{VERSION}-%{RELEASE}\n" systemd-udev-*.rpm > /out/libfprint/packages.txt; rm -f *.rpm
dnf config-manager --set-enabled crb > /dev/null
printf "[epel]\nname=epel\nbaseurl=https://dl.fedoraproject.org/pub/epel/9/Everything/\$basearch/\ngpgcheck=0\nenabled=1\n" > /etc/yum.repos.d/epel.repo
# (the kickstart: @^workstation-product-environment and epel-release; the SilikOS packages are not in a public repository)
dnf -y --installroot=/root/ir --releasever=9 install --assumeno "@workstation-product-environment" epel-release kernel \
  grub2-efi-x64 shim-x64 > /out/set/resolve.x86_64.txt 2>&1 || :
'

echo "== names and source tables"
mkdir -p "$out/ids" "$out/src/up" "$out/src/el"
get() { curl -sS -f -L --retry 2 -o "$2" "$1"; }
get https://raw.githubusercontent.com/pciutils/pciids/master/pci.ids "$out/ids/pci.ids"
get https://raw.githubusercontent.com/usbids/usbids/master/usb.ids "$out/ids/usb.ids"
for f in include/drm/intel/pciids.h drivers/gpu/drm/amd/amdgpu/amdgpu_discovery.c drivers/gpu/drm/i915/i915_pci.c \
         drivers/gpu/drm/i915/display/intel_display_device.c drivers/gpu/drm/xe/xe_pci.c \
         drivers/gpu/drm/nouveau/nvkm/engine/device/base.c Makefile; do
  d=$(echo "$f" | tr / _)
  get "https://raw.githubusercontent.com/torvalds/linux/$uptag/$f" "$out/src/up/$d"
  get "https://gitlab.com/redhat/centos-stream/src/kernel/centos-stream-9/-/raw/$eltag/$f" "$out/src/el/$d"
done
get "https://gitlab.com/redhat/centos-stream/src/kernel/centos-stream-9/-/raw/$eltag/Makefile.rhelver" "$out/src/el/Makefile.rhelver"
date -u +%Y-%m-%d > "$out/date.txt"
du -sh "$out"
