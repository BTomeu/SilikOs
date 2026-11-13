#!/usr/bin/env bash
# tests/install/offline.sh ISO [OUT_DIR]: tests/install/run.sh (the unattended installation, the first boot, the
# checks and the pictures) of the OFFLINE ISO (tools/build_offline_iso.sh), in a virtual machine that has no network
# device at all: every `-nic ...` run.sh gives QEMU becomes `-nic none`, in the installation and in the first boot.
# run.sh is used as it is; QEMU is started through a wrapper put first in PATH.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
iso=${1:?usage: tests/install/offline.sh ISO [OUT_DIR]}
real=$(command -v qemu-system-x86_64) || { echo "error: qemu-system-x86_64 is not installed" >&2; exit 2; }
# (the ISO must be the offline one: its kickstart names no network source)
ks=$(mktemp); trap 'rm -rf "$ks" "${shim:-}"' EXIT
xorriso -indev "$iso" -osirrox on -extract /silikos.ks "$ks" > /dev/null 2>&1 || { echo "error: no /silikos.ks in $iso" >&2; exit 2; }
if grep -v '^#' "$ks" | grep -Eq 'https?://'; then echo "error: $iso installs from the network: not the offline ISO" >&2; exit 2; fi
grep -q 'silik-mirror.py verify /run/install/repo/mirror' "$ks" || { echo "error: the kickstart of $iso does not verify its mirror" >&2; exit 2; }
shim=$(mktemp -d)
cat > "$shim/qemu-system-x86_64" <<SHIM
#!/usr/bin/env bash
# no network device: the argument after -nic is replaced by "none"
args=(); nic=0
for a in "\$@"; do
  if [ \$nic = 1 ]; then args+=(none); nic=0; continue; fi
  [ "\$a" = -nic ] && nic=1
  args+=("\$a")
done
echo "qemu: \$(printf '%s ' "\${args[@]}" | grep -o -- '-nic [^ ]*' | tr '\n' ' ')" >&2
exec "$real" "\${args[@]}"
SHIM
chmod +x "$shim/qemu-system-x86_64"
PATH="$shim:$PATH" bash "$here/run.sh" "$@"
