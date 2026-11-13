#!/usr/bin/env bash
# build_offline_iso.sh [MIRROR_DIR [boot.iso]]: the SilikOS installer that needs no network = the network installer
# (tools/build_iso.sh makes it: the base's boot ISO, the kickstart, product.img, the menus) + a mirror of every
# package the installation takes (`silik mirror create`, docs/OFFLINE.md) as /mirror + a copy of the kickstart whose
# package sources are that folder.
#   MIRROR_DIR           default build/mirror. Made on a machine with the network:
#                          silik mirror create build/mirror --silikos build/repo   (EL 9; 1572 packages, 2.7 GB)
#   SILIK_ARCH=aarch64   as for build_iso.sh; the mirror must be of the same architecture
#   SILIK_OFFLINE_KS=FILE  another kickstart instead of the network installer's (a reduced set, to try the
#                          mechanism): its package sources are rewritten the same way
# What is checked, and when:
#   here, before anything is written: the whole mirror (`mirror.py verify`: every file's sha256 against the manifest,
#     every package of the base against the base's keys, taken from the mirror only with the known fingerprints)
#   at the installation, before a package is installed: the same, by the kickstart's %pre, on the medium itself
#     (the installer, anaconda 34, does not check package signatures: its dnf runs with gpgcheck off; read
#     13/11/2026 in pyanaconda/modules/payloads/payload/dnf/dnf_manager.py). A mirror that fails stops the
#     installation (%pre --erroronfail).
# The kickstart still never selects or erases a disk. No network line: a machine without a network installs.
# Needs what build_iso.sh needs, and python3, rpm (rpmkeys), gpg. The ISO is the mirror's size plus about 1.5 GB.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
arch=${SILIK_ARCH:-x86_64}
mirror=${1:-$root/build/mirror}
plugin=$root/packages/silik-tools/files/plugins/mirror.py
work=$root/build/iso/offline
[ -f "$mirror/silik-mirror.json" ] || { echo "error: $mirror is not a mirror (silik mirror create $mirror --silikos build/repo)" >&2; exit 2; }
mirror=$(cd "$mirror" && pwd)
march=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["arch"])' "$mirror/silik-mirror.json")
[ "$march" = "$arch" ] || { echo "error: the mirror is for $march, the ISO for $arch (SILIK_ARCH)" >&2; exit 2; }
echo "the mirror, before it goes on a medium:"
python3 "$plugin" verify "$mirror" --mirror-keys || { echo "error: the mirror does not verify: no ISO is made of it" >&2; exit 1; }

# the network installer: everything but the package sources is its work
bash "$root/tools/build_iso.sh" ${2:+"$2"}
net=$(ls -t "$root"/build/SilikOS-*-"$arch"-netinstall.iso | head -1)
out=${net%-netinstall.iso}-offline.iso
label=$(xorriso -indev "$net" -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: *//p')
rm -rf "$work"; mkdir -p "$work"
if [ -n "${SILIK_OFFLINE_KS:-}" ]; then cp "$SILIK_OFFLINE_KS" "$work/net.ks"
else xorriso -indev "$net" -osirrox on -extract /silikos.ks "$work/net.ks" > /dev/null 2>&1; chmod u+w "$work/net.ks"; fi

# the kickstart of the medium: the same, its sources the folders of /mirror
python3 - "$work/net.ks" "$mirror/silik-mirror.json" "$work/silikos.ks" <<'EOF'
import json, re, sys
src, manifest, dst = sys.argv[1:]
m = json.load(open(manifest))
repos = m["repos"]
have = set(e["name"] for e in m["files"].values() if "name" in e)
at = "file:///run/install/repo/mirror/"
out, inside, lacking, dropped = [], False, [], []
for line in open(src).read().split("\n"):
    s = line.strip()
    if s.startswith("url "):
        if "BaseOS" not in repos:
            sys.exit("error: the mirror has no BaseOS")
        line = "url --url=%sBaseOS" % at
    elif s.startswith("repo "):
        name = re.search(r"--name=(\S+)", s).group(1).strip('"')
        if name not in repos:                  # (a source none of the set's packages comes from: not in the mirror)
            dropped.append(name)
            continue
        line = "repo --name=%s --baseurl=%s%s" % (name, at, name)
    elif s.startswith("network "):
        line = "# (no network line: this medium installs without one; the installed system's NetworkManager takes a\n# wired connection by itself, as the base does)"
    elif s.startswith("# the SilikOS packages, on the installation medium"):
        line = "# every package source is a folder of this medium (/mirror: `silik mirror`, docs/OFFLINE.md)"
    elif s.startswith("# a wired connection (cable") or s.startswith("# Wi-Fi is joined in the installer"):
        continue
    elif s.startswith("%packages"):
        inside = True
    elif s.startswith("%end"):
        inside = False
    elif inside and s and not s.startswith(("#", "@", "-")) and s not in have:
        lacking.append(s)
    out.append(line)
if lacking:
    sys.exit("error: the mirror lacks packages the kickstart installs: %s\n  (silik mirror create ... --silikos FOLDER "
             "with them in it, --add NAME for each)" % " ".join(lacking))
text = "\n".join(out).rstrip("\n") + """

# Before anything is installed: every file of the medium's mirror against its manifest (sha256), every package of
# the base against the base's keys (rpmkeys --checksig). The installer does not check signatures by itself. A
# medium that fails stops here; what it said: /tmp/silikos-mirror-verify.log (Ctrl+Alt+F2 during the installation),
# and /root/silikos-mirror-verify.log on the installed system.
%pre --erroronfail --log=/tmp/silikos-mirror-verify.log
python3 /run/install/repo/silik-mirror.py verify /run/install/repo/mirror --mirror-keys
%end

%post --nochroot
cp /tmp/silikos-mirror-verify.log /mnt/sysroot/root/silikos-mirror-verify.log || :
%end
"""
head = ("# SilikOS — kickstart of the OFFLINE medium (tools/build_offline_iso.sh made it from the network installer's):\n"
        "# the same installation, every package from this medium's /mirror, checked before it starts. No network is\n"
        "# needed or brought up. The installed system's dnf still names the Internet's repositories: in a network\n"
        "# without Internet, `silik mirror use http://THE-LAB-MIRROR:8080` (docs/OFFLINE.md).\n")
open(dst, "w").write(head + text)
print("kickstart: sources %s%s" % (" ".join(sorted(repos)), "; not in the mirror, left out: " + " ".join(dropped) if dropped else ""))
EOF
# what the kickstart must still be: no disk chosen, no network source
! grep -Eq '^(clearpart|zerombr|ignoredisk|autopart|part |partition |logvol|volgroup|raid|reqpart)' "$work/silikos.ks" \
  || { echo "error: the offline kickstart touches a disk" >&2; exit 1; }
! grep -v '^#' "$work/silikos.ks" | grep -Eq 'https?://|^network ' \
  || { echo "error: the offline kickstart still names a network source" >&2; exit 1; }

# the mirror as it goes on the medium: without dnf's working folder (hard links: no second copy on this disk)
rm -rf "$work/mirror"
cp -al "$mirror" "$work/mirror" 2> /dev/null || { rm -rf "$work/mirror"; cp -a "$mirror" "$work/mirror"; }
rm -rf "$work/mirror/.root"
rm -f "$out"
xorriso -indev "$net" -outdev "$out" -boot_image any replay -volid "$label" \
  -rm_r /silikos -- -map "$work/silikos.ks" /silikos.ks -map "$plugin" /silik-mirror.py -map "$work/mirror" /mirror
implantisomd5 --force "$out"
rm -rf "$work/mirror"
(cd "$(dirname "$out")" && sha256sum "$(basename "$out")" > "$(basename "$out").sha256")
echo "offline ISO: $out, $(du -h "$out" | cut -f1) ($(stat -c %s "$out") bytes), label $label, sha256 $(cut -d' ' -f1 "$out.sha256")"
echo "  the mirror on it: $(python3 -c 'import json, sys; m = json.load(open(sys.argv[1])); f = m["files"]; print("generation %d, %d packages, %.0f MB" % (m["generation"], sum(1 for r in f if r.endswith(".rpm")), sum(e["size"] for e in f.values()) / 1e6))' "$mirror/silik-mirror.json")"
