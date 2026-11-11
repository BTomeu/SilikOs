# SilikOS — kickstart for the installer (the EL9 base's Anaconda), x86_64.
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
# sshd is in the base and on by default: a personal workstation does not need it (to have it: `sudo systemctl
# enable --now sshd`, then `silik secure apply --keep-ssh`)
services --enabled=NetworkManager,gdm --disabled=sshd
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
%end
