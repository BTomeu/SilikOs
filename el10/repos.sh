#!/usr/bin/env bash
# repos.sh: inside an AlmaLinux 9 or 10 container, set the package sources the SilikOS checks use: BaseOS,
# AppStream, extras, CRB and EPEL of the system's own minor release. With SILIK_EL_BASEURL=1 (box.sh sets it when the
# build machine is behind a proxy: mirrors.almalinux.org and mirrors.fedoraproject.org are not reachable through
# it, repo.almalinux.org and dl.fedoraproject.org are) the sources are the projects' own hosts instead of the mirror
# lists. The packages are still checked against the keys the image ships (EPEL's key is fetched from
# dl.fedoraproject.org, as epel-release would install it).
set -euo pipefail
. /etc/os-release
major=${VERSION_ID%%.*}
if [ "${SILIK_EL_BASEURL:-0}" = 1 ]; then
  sed -i -E 's|^mirrorlist=|# mirrorlist=|; s|^# ?baseurl=|baseurl=|' /etc/yum.repos.d/almalinux*.repo
fi
sed -i -E '/^\[crb\]/,/^\[/{s/^enabled=0/enabled=1/}' /etc/yum.repos.d/almalinux-crb.repo
# EPEL 10 has one tree per minor release of the base (10.0, 10.1, ...); EPEL 9 has one tree
if [ "$major" -ge 10 ]; then epel=$VERSION_ID; else epel=$major; fi
cat > /etc/yum.repos.d/epel.repo <<REPO
[epel]
name=EPEL $epel
baseurl=https://dl.fedoraproject.org/pub/epel/$epel/Everything/\$basearch/
enabled=1
gpgcheck=1
gpgkey=https://dl.fedoraproject.org/pub/epel/RPM-GPG-KEY-EPEL-$major
REPO
