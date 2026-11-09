Name:           silik-win
Version:        0.1.0
Release:        1%{?dist}
Summary:        Windows programs on SilikOS: Wine, and a Windows virtual machine whose programs open as windows here
License:        LicenseRef-SilikVolt
BuildArch:      noarch
Requires:       silik-tools = %{version}
Recommends:     wine
Recommends:     qemu-kvm
Recommends:     libvirt-daemon-kvm
Recommends:     libvirt-client
Recommends:     virt-install
Recommends:     virt-viewer
Recommends:     virt-manager
Recommends:     edk2-ovmf
Recommends:     swtpm
Recommends:     passt
Recommends:     freerdp

%description
What `silik win` uses: Wine (from EPEL) for the programs it runs, and KVM / libvirt / FreeRDP for the ones it does not
(a Windows virtual machine; `silik win vm app` shows one of its programs as a window of this desktop).
Windows and the programs are the user's own licences.

%files
