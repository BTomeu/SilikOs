# SilikOS — kickstart for the installer (the EL9 base's Anaconda), x86_64. For aarch64, tools/build_iso.sh puts a
# copy on the ISO with the repositories' architecture changed and without the x86_64 kernel argument (vsyscall).
# What it fixes: the package sources, the package set and the post-install setup. What it leaves to the installer's
# screens, on purpose: language, keyboard, time zone, the disk (never chosen or erased from here: a machine may hold
# another system), the user and the root password.

url --url=https://repo.almalinux.org/almalinux/9/BaseOS/x86_64/os/
repo --name=AppStream --baseurl=https://repo.almalinux.org/almalinux/9/AppStream/x86_64/os/
repo --name=CRB --baseurl=https://repo.almalinux.org/almalinux/9/CRB/x86_64/os/
repo --name=extras --baseurl=https://repo.almalinux.org/almalinux/9/extras/x86_64/os/
repo --name=epel --baseurl=https://dl.fedoraproject.org/pub/epel/9/Everything/x86_64/
# the SilikOS packages, on the installation medium (tools/build_iso.sh puts build/repo there)
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

%packages
@^workstation-product-environment
epel-release
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
# the firewall's default zone is the SilikOS one (package silikos-security): incoming dropped, outgoing free.
# The offline command also leaves a copy of the zone in /etc, which would hide the package's file on updates.
firewall-offline-cmd --set-default-zone=silikos && rm -f /etc/firewalld/zones/silikos.xml || :
# when / is on an LVM thin volume (what the installer's Automatic partitioning makes on SilikOS; any other choice in
# its Installation Destination screen is left as it is): the thin pool grows by itself, from the free space the
# installer leaves in the volume group (profile silikos-thin of silikos-security: at 70 % used, by 20 %). Only the
# profile's name is written to the pool; nothing is created, resized or erased. On a running system:
# `silik snapshot setup`; `silik snapshot status` reads it back
root_lv=$(findmnt -n -o SOURCE /)
pool=$(lvs --noheadings -o vg_name,pool_lv "$root_lv" | awk 'NF == 2 { print $1 "/" $2 }')
if [ -n "$pool" ]; then lvchange --metadataprofile silikos-thin "$pool" || :; fi
%end
