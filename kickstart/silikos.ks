# SilikOS — kickstart for the installer (the EL9 base's Anaconda), x86_64. For aarch64, tools/build_iso.sh puts a
# copy on the ISO with the repositories' architecture changed and without the x86_64 kernel argument (vsyscall).
# What it fixes: the package sources, the package set and the post-install setup. What it leaves to the installer's
# screens, on purpose: language, keyboard, time zone, the disk (never chosen or erased from here: a machine may hold
# another system; the entry for an external disk only hides the computer's own disks: the %pre below), the user and
# the root password.

url --url=https://repo.almalinux.org/almalinux/9/BaseOS/x86_64/os/
repo --name=AppStream --baseurl=https://repo.almalinux.org/almalinux/9/AppStream/x86_64/os/
repo --name=CRB --baseurl=https://repo.almalinux.org/almalinux/9/CRB/x86_64/os/
repo --name=extras --baseurl=https://repo.almalinux.org/almalinux/9/extras/x86_64/os/
repo --name=epel --baseurl=https://dl.fedoraproject.org/pub/epel/9/Everything/x86_64/
# the SilikOS packages, on the installation medium (tools/build_iso.sh puts build/repo there). For the installer
# only (no --install): the installed system does not keep a repository that left with the medium. Its updates come
# from SilikOS's own repository (package silikos-repos, turned on at the end of this file when it can be)
repo --name=silikos --baseurl=file:///run/install/repo/silikos

# a wired connection (cable, or a phone's USB tether) is brought up by itself so that the package sources answer;
# Wi-Fi is joined in the installer's "Network & Host Name" screen, then "Installation Source" is opened once again
network --bootproto=dhcp --device=link --activate --onboot=yes

graphical
xconfig --startxonboot
firstboot --enable
# fstrim.timer: the SSD is told weekly which blocks are free (util-linux's timer, off on EL 9.8 by default).
# silikos-power-auto: performance on mains power, balanced on battery (`silik power`; docs/POWER.md).
# sshd is in the base and on by default: a personal workstation does not need it (to have it: `sudo systemctl
# enable --now sshd`, then `silik secure apply --keep-ssh`)
services --enabled=NetworkManager,gdm,fstrim.timer,silikos-power-auto --disabled=sshd
# Security, stated (docs/SECURITY.md). SELinux stays as the base has it. The firewall is on; the installer opens ssh
# in the default zone unless told not to. Disk encryption is not set here: the disk and "Encrypt my data" are chosen
# in the installer's Installation Destination screen, like everything about the disk.
selinux --enforcing
firewall --enabled --remove-service=ssh
# glibc 2.12 (EL6 userlands of `silik eda`) calls the vsyscall page: keep it callable whatever the kernel's default
bootloader --append="vsyscall=xonly"

# The ISO's menu entry "on an external disk" (tools/build_iso.sh: it gives the installer inst.leavebootorder). With it,
# and only with it, the installer is shown the disks on USB and no others: a disk of the computer itself cannot be
# ticked by mistake, because it is not on the screen. Nothing is chosen and nothing is erased from here: the person
# still ticks the external disk in Installation Destination. With every other entry the file is empty and every
# disk is shown. (An external disk that is not on USB, Thunderbolt or eSATA, is hidden too: the first entry is for it.)
%include /tmp/silik-disks.ks

%pre
: > /tmp/silik-disks.ks
if grep -qw 'inst\.leavebootorder' /proc/cmdline; then
  # this computer's own disks: every disk with a size that is not on USB, by its kernel name (SATA and SCSI, NVMe,
  # eMMC, a virtual machine's disks; never a part of one, such as an eMMC's boot areas, and never zram or a loop).
  # A virtual disk does not say how it is attached (seen in the CI, 14/11/2026): no answer is taken as "not USB"
  own=$(lsblk -d -n -b -P -o NAME,TYPE,TRAN,SIZE \
        | awk -F'"' '$4 == "disk" && $6 != "usb" && $8 > 0 && $2 ~ /^(sd[a-z]+|vd[a-z]+|xvd[a-z]+|hd[a-z]+|nvme[0-9]+n[0-9]+|mmcblk[0-9]+)$/ { print $2 }' | paste -s -d, -)
  [ -z "$own" ] || printf 'ignoredisk --drives=%s\n' "$own" > /tmp/silik-disks.ks
fi
%end

%packages
@^workstation-product-environment
epel-release
# the base's own package, which its Workstation set leaves out: the kernel's vcan (the virtual CAN bus), slcan
# (serial-line CAN adapters) and ems_usb are in it. An update of the kernel brings its kernel-modules-extra too
kernel-modules-extra
silikos-branding
silikos-desktop
silik-tools
silik-command
silik-eda-compat
silik-eda-open
silik-dev
silik-win
silikos-security
silikos-power
# the way back from an update (docs/ROLLBACK.md): the base's snapshot manager and its boot entries (AppStream). With
# / on an LVM thin volume (the installer's Automatic partitioning on SilikOS) a snapshot is made before each update
snapm
boom-boot
silikos-repos
# USB devices plugged in while the screen is locked are refused (docs/USB.md): the base's USBGuard, its D-Bus service
# (what GNOME's USB protection talks to) and its SELinux policy (AppStream); silikos-security carries the configuration
usbguard
usbguard-dbus
usbguard-selinux
# the TPM's tools: what the start-up needs to open an encrypted disk with the TPM and a PIN (`silik disk tpm enroll`,
# docs/DISK.md), so that enrolling does not need the network
tpm2-tools
%end

%post --log=/root/silikos-post.log
# CRB is needed by EPEL packages (Wine among them)
dnf config-manager --set-enabled crb || :
# the boot menu says SilikOS; /etc/os-release stays the base system's (vendor installers read it)
if grep -q '^GRUB_DISTRIBUTOR=' /etc/default/grub; then
  sed -i 's/^GRUB_DISTRIBUTOR=.*/GRUB_DISTRIBUTOR="SilikOS"/' /etc/default/grub
else
  echo 'GRUB_DISTRIBUTOR="SilikOS"' >> /etc/default/grub
fi
dconf update || :
# an account with no password does not log in (the audit of 13/11/2026: the base's login files accept one, their
# `nullok`). The base's own tool and its own switch: where a profile is selected the switch is added to it; a new
# installation has none selected (seen in the installation test: "No existing configuration detected"), so the
# base's default profile is selected with the switch
if authselect current | grep -q 'Profile ID'; then authselect enable-feature without-nullok || :
else authselect select sssd without-nullok --force || :; fi
# the firewall's default zone is the SilikOS one (package silikos-security): incoming dropped, outgoing free.
# The offline command also leaves a copy of the zone in /etc, which would hide the package's file on updates.
firewall-offline-cmd --set-default-zone=silikos && rm -f /etc/firewalld/zones/silikos.xml || :
# nothing listens beyond this machine (docs/SECURITY.md): the base's port mapper of NFS v3 (port 111; an NFS v3 mount
# starts it by itself), mDNS (UDP 5353, which also announces the machine's name) and the discovery of network
# printers are off. One at a time: a unit the set does not bring is not an error. On the installed system
# `silik listen` shows them and `silik listen on NAME` is the way back
for u in rpcbind.socket rpcbind.service avahi-daemon.socket avahi-daemon.service cups-browsed.service; do
  systemctl disable "$u" || :
done
# USBGuard, with the configuration of silikos-security (what is plugged in at the start, at the login screen or
# while the screen is unlocked is accepted; GNOME's USB protection refuses new devices while it is locked). Never with
# the base's own configuration, which refuses every device no rule names, a keyboard included
if [ -f /etc/usbguard/silikos-daemon.conf ] && [ -f /usr/lib/systemd/system/usbguard.service.d/10-silikos.conf ]; then
  systemctl enable usbguard.service usbguard-dbus.service || :
fi
# the speed profile (docs/SPEED.md): what the base starts and an engineer's workstation does not need is off from the
# first start (kdump's arming, ModemManager, the storage-array daemon, multipathd and the wait for udev it brings,
# rpcbind until asked, the hourly metadata download, the daily updatedb, the file indexer, GNOME Software in the
# background). Nothing of docs/SECURITY.md is in it; the kernel's parameters are not touched. It writes down what it
# changed: `silik speed undo` on the installed system puts it back, `silik speed` shows each item.
# (SYSTEMD_OFFLINE: nothing runs here to be stopped; the units are off from the first start)
SYSTEMD_OFFLINE=1 silik -q speed apply || :
# when / is on an LVM thin volume (what the installer's Automatic partitioning makes on SilikOS; any other choice in
# its Installation Destination screen is left as it is): the thin pool grows by itself, from the free space the
# installer leaves in the volume group (profile silikos-thin of silikos-security: at 70 % used, by 20 %). Only the
# profile's name is written to the pool; nothing is created, resized or erased. On a running system:
# `silik snapshot setup`; `silik snapshot status` reads it back
root_lv=$(findmnt -n -o SOURCE /)
pool=$(lvs --noheadings -o vg_name,pool_lv "$root_lv" | awk 'NF == 2 { print $1 "/" $2 }')
if [ -n "$pool" ]; then lvchange --metadataprofile silikos-thin "$pool" || :; fi
# SilikOS's own packages are updated from the stable channel of their repository, when this system has the key they
# are signed with (the package silikos-repos carries it once the owner has made it: docs/REPO.md). Without the key
# both channels stay off: nothing unsigned is trusted. On a running system: silik update channel stable | next | off
if grep -qs '^-----BEGIN PGP PUBLIC KEY BLOCK-----' /etc/pki/rpm-gpg/RPM-GPG-KEY-SilikOS; then
  rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-SilikOS || :
  dnf config-manager --save --setopt=silikos.enabled=1 || :
fi
%end
