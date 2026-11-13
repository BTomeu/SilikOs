#!/usr/bin/env bash
# shell_image.sh: make the local container image "silikos-el10-shell" (AlmaLinux 10 with GNOME Shell, gjs, mutter's
# development kit, a session bus, software rendering and the tools the shell checks use), once; the shell checks
# (el10/shell_check.sh, el10/shell_run.sh) run in it. Nothing of SilikOS is in the image: the repository is mounted
# when a check runs. It is a build-machine image, never published.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
name=silikos-el10-shell
docker rm -f "$name-build" >/dev/null 2>&1 || true
# box.sh runs with --rm: run it without, by hand, to be able to commit
opts=(--name "$name-build" --network host -v "$here/..:/src" -w /src)
ca=${SILIK_CA:-${SSL_CERT_FILE:-}}; proxy=${HTTPS_PROXY:-${https_proxy:-}}; pre=:
if [ -n "$proxy" ]; then
  opts+=(-e SILIK_EL_BASEURL=1 -e "HTTPS_PROXY=$proxy" -e "https_proxy=$proxy")
  if [ -n "$ca" ] && [ -f "$ca" ]; then opts+=(-v "$ca:/etc/pki/ca-trust/source/anchors/build-proxy.crt:ro"); pre=update-ca-trust; fi
fi
docker run "${opts[@]}" almalinux:10 bash -c "$pre"' && bash /src/el10/repos.sh &&
  dnf -y install gnome-shell gjs mutter gnome-session dbus-daemon mesa-dri-drivers xorg-x11-server-Xwayland \
      glib2-devel gsettings-desktop-schemas gnome-shell-extension-user-theme gnome-extensions-app \
      dejavu-sans-fonts procps-ng findutils diffutils unzip which python3-gobject gtk3 gtk4 xprop xdpyinfo xhost xterm &&
  (dnf -y install mutter-devkit || echo "note: no mutter-devkit package") && dnf clean all'
docker commit "$name-build" "$name" >/dev/null
docker rm "$name-build" >/dev/null
docker run --rm "$name" bash -c 'rpm -q gnome-shell mutter gjs xorg-x11-server-Xwayland'
