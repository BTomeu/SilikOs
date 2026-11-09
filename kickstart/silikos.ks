# SilikOS 0.1 — kickstart for the installer (AlmaLinux 9 Anaconda), x86_64.
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
services --enabled=NetworkManager,gdm
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
silik-win
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
%end
