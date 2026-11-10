#!/usr/bin/env bash
# install_on_alma.sh: SilikOS on top of an installed AlmaLinux / Rocky / RHEL 9 (Workstation), without the ISO.
# Builds the packages if build/repo is missing, enables CRB + EPEL, installs the packages with their dependencies.
# The security defaults (firewall zone, sshd off, kernel settings) are not switched on by installing: that is
# `silik secure apply`, which prints what it runs; on a machine reached over ssh, `silik secure apply --keep-ssh`.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
[ -d "$root/build/repo" ] || { sudo dnf -y install rpm-build createrepo_c; bash "$root/tools/build_rpms.sh"; }
sudo dnf -y install epel-release
sudo dnf config-manager --set-enabled crb
sudo dnf -y install "$root"/build/repo/*.rpm
echo "log out and in again (X11 session, SilikOS defaults); Super+Space opens the COMMAND bar; \`silik status\`"
echo "security: \`silik secure status\` reads this system, \`silik secure apply\` sets the SilikOS defaults (docs/SECURITY.md)"
