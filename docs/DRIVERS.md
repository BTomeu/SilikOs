# Drivers: what the base's kernel drives, read from its own packages (13/11/2026)

## Resum (català)

- **Què porta instal·lat.** SilikOS no afegeix cap driver: porta els del kernel d'AlmaLinux 9.8 (5.14.0-687.66.2, amb la
  part gràfica d'un Linux 6.18) i el seu firmware (`linux-firmware`, `alsa-sof-firmware`, `iwl*`, microcodi). Hem llegit
  les taules d'IDs dels paquets del kernel (x86_64 i aarch64) i les hem comparat amb un kernel actual (Linux 7.2).
- **El resultat és millor del que s'esperava.** Wi-Fi 7 d'Intel, MediaTek MT7925 i Qualcomm WCN7850, gràfics Intel
  fins a Panther Lake (i915 i xe), AMD fins a Radeon RX 9000, Thunderbolt/USB4, àudio SOF fins a Panther Lake: el
  kernel de la base té un driver que reclama aquests IDs.
- **El que li falta a un portàtil de 2025** (llista de sota): la càmera MIPI dels Intel (IPU6/IPU7), tres Wi-Fi de
  Realtek (RTL8922AE, RTL8851BE, RTL8852BE-VT), dos de MediaTek (MT7927, MT7902), la Realtek de 10G (RTL8127), la NPU
  d'AMD, l'EC dels Framework, les Broadcom BCM43xx antigues, els adaptadors Wi-Fi USB de Realtek/MediaTek nous.
- **Un error trobat i arreglat:** `vcan`, `slcan` i `ems_usb` són a `kernel-modules-extra`, que el conjunt Workstation no
  instal·la. Ara el kickstart el demana, i `silik doctor hardware` ho diu si falta.
- **Ordres noves:** `silik hw check` (cada dispositiu d'aquesta màquina i el seu driver) i
  `silik hw check --from llista.txt` (una llista `lspci -nn` / `lsusb` / IDs de Windows d'una altra màquina: "funcionarà
  el meu portàtil?" abans d'instal·lar); `silik hw driver add NOM` (un kmod d'ELRepo, tercer, per als forats que en
  tenen); `silik hw nvidia install --source almalinux` (els mòduls oberts precompilats i signats d'AlmaLinux).
- **El límit, dit clar:** que un driver reclami un ID no vol dir que el dispositiu funcioni bé. **Res d'això s'ha
  executat en maquinari real**; totes les files porten `verified=no`.
- **Decisions teves:** NVIDIA per defecte (AlmaLinux natiu o el DKMS d'NVIDIA, secció 5) i si acceptes ELRepo com a
  font opcional (secció 6).

## The short answer

**What a 2025 laptop or workstation most likely lacks on EL 9.8's kernel** (each line is a row of the tables below):

| # | Part | What the kernel packages say | What a person can do |
|---|---|---|---|
| 1 | Intel MIPI webcam (IPU6: Tiger / Alder / Raptor / Meteor Lake; IPU7: Lunar / Panther Lake) | no `intel_ipu6` / `intel_ipu7` module, `CONFIG_VIDEO_INTEL_IPU6` not set, none of the sensor drivers | a USB webcam (`uvcvideo` is there) |
| 2 | Realtek Wi-Fi RTL8922AE (Wi-Fi 7), RTL8851BE, RTL8852BE-VT | no `rtw89_8922ae`, `rtw89_8851be`, `rtw89_8852bte` | `silik hw driver add rtw89_usb` (ELRepo builds exactly these three and the USB ones), or a USB adapter the base drives |
| 3 | MediaTek MT7927 (Wi-Fi 7, 320 MHz), MT7902 | `mt7925e` / `mt7921e` are there but do not claim these two IDs | a cable or a USB adapter |
| 4 | Realtek RTL8127 10G Ethernet | `r8169` claims RTL8125 and RTL8126, not `10ec:8127` | `silik hw driver add r8127` |
| 5 | AMD NPU (Ryzen AI: `1022:1502`, `1022:17f0`) | no `amdxdna` (Intel's NPU has `intel_vpu`) | nothing: no driver on this base |
| 6 | Framework laptops: the embedded controller | `CONFIG_CROS_EC` not set: no `cros_ec_lpcs`, `cros_charge_control`, `cros_kbd_led_backlight` | the laptop's other parts are ordinary Intel / AMD parts (see the tables); charge limit and EC sensors: nothing |
| 7 | Broadcom BCM4360 / BCM4352 / BCM4331 / BCM43142 Wi-Fi | `bcma` takes the card's bus; there is no `b43` for the radio on it | `silik hw driver add wl` |
| 8 | USB Wi-Fi adapters with Realtek 802.11ac / Wi-Fi 6 chips, MediaTek MT7921U | no `rtw88_*u`, `rtw89_*u`, `mt7921u` | `silik hw driver add rtw88_usb` / `rtw89_usb` |
| 9 | NVIDIA cards | `nouveau` claims every one (its chip list is the upstream kernel's, RTX 50 included); CUDA and full speed need NVIDIA's driver | `silik hw nvidia install` (section 5) |
| 10 | Newest AMD graphics (2026 parts) | `amdgpu` binds any AMD display device, but handles graphics-core versions up to 12.0.1; the upstream kernel adds 11.5.4, 11.5.6, 11.7.x, 12.1.0 | wait for the base, or nothing |
| 11 | CAN: esd CAN-USB/2, /3, /Micro; Microchip CAN BUS Analyzer; Fintek F81604; three newer Kvaser USB IDs | no `esd_usb`, `mcba_usb`, `f81604` (and, as in Fedora's build of the upstream kernel, no `kvaser_pciefd`, `etas_es58x`, `ucan`) | a gs_usb / candleLight, PEAK or Kvaser adapter; or Windows in the VM |
| 12 | Fingerprint readers newer than libfprint 1.94.6 | the base's `libfprint` is 1.94.6; its list is in `kernel-aliases.tsv` | `silik hw check` names the reader and its libfprint driver, or says it is not listed |
| 13 | ARM laptops (Snapdragon X), Raspberry Pi, Apple silicon on bare metal | the aarch64 kernel has no device tree, clock, pin, PHY or display driver for them (section "ARM") | a virtual machine; for the Pi, AlmaLinux's own Pi image |

Not gaps, against expectation: Intel Wi-Fi 7 BE200 / BE201, MediaTek MT7925, Qualcomm WCN7850 (`ath12k`), Intel I226,
Realtek RTL8126, Intel graphics through Panther Lake, AMD graphics through Radeon RX 9000 and Ryzen AI 300, SOF audio
through Panther Lake, Thunderbolt 4 / USB4 through Panther Lake, the touchpad's I2C controllers through Panther Lake,
AMD P-State (active mode by default) and Intel Thread Director.

**A bug found here and fixed:** the kernel's `vcan` (the virtual CAN bus), `slcan` (serial-line CAN adapters) and
`ems_usb` are in `kernel-modules-extra`, which the base's Workstation set does not install. The kickstart now asks for
it, `tools/install_on_alma.sh` installs it, and `silik doctor hardware` says when it is missing for the running kernel.

## Method, and its limits

- **What was read.** The packages `kernel-core`, `kernel-modules-core`, `kernel-modules` and `kernel-modules-extra`
  5.14.0-687.66.2.el9_8 of AlmaLinux 9.8, for x86_64 and aarch64
  (<https://repo.almalinux.org/almalinux/9/BaseOS/x86_64/os/Packages/>, `.../aarch64/os/Packages/`), downloaded one at a
  time in an `almalinux:9` container (`dnf --forcearch aarch64 download` for ARM: no emulation), their modules
  extracted, `depmod` run on the tree to get `modules.alias`, the packages deleted. `tools/fetch_hw_facts.sh` is that,
  as one script.
- **The reference.** The same of Fedora 45's kernel 7.2.11
  (<https://dl.fedoraproject.org/pub/fedora/linux/releases/45/Everything/x86_64/os/Packages/k/>): the ID tables of the
  upstream kernel's drivers, compiled. The upstream source is
  <https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git> (tag `v7.2`); the files quoted here were read at
  that tag through its mirror <https://github.com/torvalds/linux> (git.kernel.org was not reachable from the build
  machine). EL's source files were read from CentOS Stream 9's kernel,
  <https://gitlab.com/redhat/centos-stream/src/kernel/centos-stream-9>, tag `kernel-5.14.0-687.el9`, the build EL 9.8's
  kernel series starts from [A: AlmaLinux's own source package is on vault.almalinux.org, not reachable from here; the
  later 687.x builds are fixes].
- **Names** are those of pci.ids (<https://pci-ids.ucw.cz/>, read from <https://github.com/pciutils/pciids>) and
  usb.ids (<https://github.com/usbids/usbids>). A device with no name there is shown without one, not named from memory.
- **The match.** For each device ID, the modules whose alias pattern it satisfies. `tools/gen_hwdb.py` writes
  `packages/silik-tools/files/kernel-aliases.tsv` (every PCI and USB alias of EL 9.8's kernel for both architectures,
  and the upstream module for the IDs EL does not claim), `pci.tsv` (the named devices and every gap of the families)
  and the tables of this page (between the `gen:` marks: do not edit them by hand).
- **A driver built into the kernel has no alias** (`xhci_pci`, `thunderbolt`, `vmd`, `virtio_pci`, the PCIe port driver).
  Their tables were read from the source: `tools/hwdb/builtin.tsv`.

**Limits. An alias match says a driver in EL 9.8's kernel claims the ID, not that the device works.**
- The driver may bind and still lack the code for that chip revision, the firmware file, or the ACPI glue of that
  laptop. `amdgpu`, `nouveau`, `btusb`, `uvcvideo`, `nvme`, `ahci` bind by class: for them the table says nothing about
  the model (the AMD and NVIDIA sections read the drivers' own chip lists instead).
- A driver can refuse a device it claims (`xe` asks for `force_probe` on the platforms `i915` owns: read from the source,
  table below).
- Suspend, power use, audio routing, external displays, fan control: not visible in any table.
- Parts that are not PCI or USB (the touchpad on I2C, the keyboard, ACPI platform devices) are covered only by the
  "modules present" table.
- **Nothing was run on hardware.** Every row of `pci.tsv` and `hardware.tsv` has `verified=no`. A row becomes `yes`
  when the device was used on SilikOS (`docs/STATUS.md`).

## 1. What is preinstalled

SilikOS adds no driver and changes none: the drivers are the base's kernel and its firmware packages.

<!-- gen:kernel -->
| Kernel | Version | kernel-modules-core | kernel-modules | kernel-modules-extra | built in | PCI aliases | USB aliases |
|---|---|---|---|---|---|---|---|
| EL 9.8 x86_64 | `5.14.0-687.66.2.el9_8.x86_64` | 1403 | 971 | 26 | 293 | 6399 | 6971 |
| EL 9.8 aarch64 | `5.14.0-687.66.2.el9_8.aarch64` | 1289 | 591 | 26 | 380 | 4543 | 6445 |
| Linux 7.2.11 (Fedora 45) x86_64 | `7.2.11-300.fc45.x86_64` | 2260 | 2492 | 98 | 358 | 8071 | 8621 |
<!-- /gen -->

- The graphics stack of this kernel is the upstream kernel's 6.18: `RHEL_DRM_VERSION = 6`, `RHEL_DRM_PATCHLEVEL = 18`
  in `Makefile.rhelver` of the tag above.
- AlmaLinux's kernel differs from RHEL's in what its changelog says (`rpm -q --changelog kernel-core`, 5.14.0-687.66.1):
  "Use AlmaLinux OS secure boot cert", "Debrand for AlmaLinux OS", and device IDs Red Hat removed, brought back: `hpsa`,
  `mptsas`, `megaraid_sas`, `qla2xxx`, `qla4xxx`, `lpfc`, `be2iscsi` ("bring back deprecated PCI ids").
- `kernel-modules-extra` also puts `sctp`, `l2tp_*` and `atm` on the modprobe blacklist (its `/etc/modprobe.d/*-blacklist.conf`,
  citing <https://access.redhat.com/articles/3760101>); the CAN modules in it are not blacklisted.

**Packages of the kickstart's set** (`@^workstation-product-environment` and `epel-release`, resolved by `dnf` in an
empty root with the repositories of 13/11/2026: 1230 packages; the installer was not run for this):

<!-- gen:set -->
| Package | In the kickstart's set | Version (repository) |
|---|---|---|
| kernel | **installed** | 5.14.0-687.66.2.el9_8 (baseos) |
| kernel-core | **installed** | 5.14.0-687.66.2.el9_8 (baseos) |
| kernel-modules-core | **installed** | 5.14.0-687.66.2.el9_8 (baseos) |
| kernel-modules | **installed** | 5.14.0-687.66.2.el9_8 (baseos) |
| kernel-modules-extra | not installed |  |
| linux-firmware | **installed** | 20261026-161.5.el9_8 (baseos) |
| microcode_ctl | **installed** | 20260210-1.20260812.1.el9_8 (baseos) |
| alsa-sof-firmware | **installed** | 2025.12.2-1.el9 (appstream) |
| alsa-firmware | not installed |  |
| iwl7260-firmware | **installed** | 25.30.13.0-161.5.el9_8 (baseos) |
| iwl3160-firmware | **installed** | 25.30.13.0-161.5.el9_8 (baseos) |
| iwl100-firmware | **installed** | 39.31.5.1-161.5.el9_8 (baseos) |
| libertas-sd8787-firmware | **installed** | 20261026-161.5.el9_8 (baseos) |
| netronome-firmware | **installed** | 20261026-161.5.el9_8 (baseos) |
| mesa-dri-drivers | **installed** | 25.2.7-5.el9_8.alma.1 (appstream) |
| mesa-vulkan-drivers | **installed** | 25.2.7-5.el9_8.alma.1 (appstream) |
| fprintd | **installed** | 1.94.0-3.el9 (appstream) |
| fprintd-pam | **installed** | 1.94.0-3.el9 (appstream) |
| libfprint | **installed** | 1.94.6-1.el9 (appstream) |
| bolt | **installed** | 0.9.10-1.el9 (baseos) |
| thermald | **installed** | 2.5.9-1.el9 (appstream) |
| tuned | **installed** | 2.27.0-2.el9_8 (baseos) |
| tuned-ppd | **installed** | 2.27.0-2.el9_8 (appstream) |
| fwupd | **installed** | 2.0.19-2.el9_8.alma.1 (baseos) |
| bluez | **installed** | 5.87+1.git30db66dc971b-1.el9_8 (baseos) |
| ModemManager | **installed** | 1.20.2-1.el9 (baseos) |
| usb_modeswitch | **installed** | 2.6.1-4.el9 (baseos) |
| iio-sensor-proxy | **installed** | 3.3-1.el9 (appstream) |
| switcheroo-control | **installed** | 2.4-4.el9 (appstream) |
| pipewire | **installed** | 1.4.11-1.el9_8.2 (appstream) |
| wpa_supplicant | **installed** | 2.11-2.el9 (baseos) |
| wireless-regdb | **installed** | 2025.10.07-1.el9 (baseos) |
| xorg-x11-drv-libinput | **installed** | 1.0.1-4.el9_6 (appstream) |
| xorg-x11-drv-wacom | **installed** | 1.0.0-5.el9_8 (appstream) |
| libcamera | not installed |  |
| v4l-utils | not installed |  |
| pcsc-lite | not installed |  |
| pcsc-lite-ccid | not installed |  |
| opensc | not installed |  |
| hplip | not installed |  |
| akmods | not installed |  |
| dkms | not installed |  |
| elrepo-release | not installed |  |
| almalinux-release-nvidia-driver | not installed |  |
<!-- /gen -->

`kernel-core` recommends `linux-firmware`, which is why it is there. Intel's Wi-Fi firmware is not in it: on EL 9.8
all of it, the AX and BE cards' included, is in the package named `iwl7260-firmware` (374 `iwlwifi-*` files); the other
`iwl*-firmware` packages are older cards'.

**Firmware the drivers name, against the files of those packages** (`modinfo -F firmware` of each module; a file name
missing here is not always a fault: several are alternatives, older boards, or SDIO variants):

<!-- gen:firmware -->
| Module | Firmware files it names | in the base's firmware packages | there under a lower API number | Package | Named, not in the packages |
|---|---|---|---|---|---|
| iwlwifi | 62 | 19 | 9 | iwl3160-firmware, iwl7260-firmware | `iwlwifi-100-5.ucode`, `iwlwifi-1000-5.ucode`, `iwlwifi-135-6.ucode` and 31 more |
| rtw89_8852a | 1 | 1 | 0 | linux-firmware | none |
| rtw89_8852b | 1 | 1 | 0 | linux-firmware | none |
| rtw89_8852c | 1 | 1 | 0 | linux-firmware | none |
| rtw88_8822c | 2 | 2 | 0 | linux-firmware | none |
| rtw88_8821c | 1 | 1 | 0 | linux-firmware | none |
| mt7921e | 6 | 6 | 0 | linux-firmware | none |
| mt7925e | 2 | 2 | 0 | linux-firmware | none |
| ath10k_pci | 21 | 15 | 0 | linux-firmware | `ath10k/QCA6174/hw3.0/firmware-5.bin`, `ath10k/QCA6174/hw2.1/firmware-4.bin`, `ath10k/QCA9887/hw1.0/board-2.bin` and 3 more |
| ath11k_pci | 4 | 4 | 0 | linux-firmware | none |
| brcmfmac | 78 | 45 | 0 | linux-firmware | `brcm/brcmfmac*-sdio.*.bin`, `brcm/brcmfmac43752-sdio.clm_blob`, `brcm/brcmfmac43752-sdio.bin` and 30 more |
| btintel | 4 | 4 | 0 | linux-firmware | none |
| btrtl | 48 | 40 | 0 | linux-firmware | `rtl_bt/rtl8852bs_config.bin`, `rtl_bt/rtl8852bs_fw.bin`, `rtl_bt/rtl8723ds_config.bin` and 5 more |
| btmtk | 6 | 6 | 0 | linux-firmware | none |
| i915 | 58 | 58 | 0 | linux-firmware | none |
| xe | 39 | 39 | 0 | linux-firmware | none |
| amdgpu | 583 | 575 | 0 | linux-firmware | `amdgpu/cyan_skillfish_gpu_info.bin`, `amdgpu/ip_discovery.bin`, `amdgpu/vega10_cap.bin` and 5 more |
| nouveau | 519 | 416 | 0 | linux-firmware | `nvidia/tu106/gsp/gsp-570.144.bin`, `nvidia/tu106/gsp/bootloader-570.144.bin`, `nvidia/tu106/gsp/booter_unload-570.144.bin` and 100 more |
| r8169 | 27 | 27 | 0 | linux-firmware | none |
| intel_vpu | 3 | 3 | 0 | linux-firmware | none |
| snd_soc_avs | 11 | 0 | 0 | linux-firmware | `intel/fcl/dsp_basefw.bin`, `intel/adl_n/dsp_basefw.bin`, `intel/adl/dsp_basefw.bin` and 8 more |
| ice | 1 | 1 | 0 | linux-firmware | none |
| qed | 1 | 1 | 0 | linux-firmware | none |
<!-- /gen -->

## 2. Coverage by family

Two kinds of table. "Named devices": the parts asked about, by ID, with the name pci.ids gives. "By driver": every ID the
family's drivers claim in the upstream kernel, counted in EL 9.8's, with the ones it lacks.

### Wi-Fi and Bluetooth

<!-- gen:wifi -->
| Device | IDs | Name (pci.ids) | EL 9.8 x86_64 | EL 9.8 aarch64 | Linux 7.2.11 (Fedora 45) | Note |
|---|---|---|---|---|---|---|
| Intel Wi-Fi 6 AX200 | `8086:2723` | Wi-Fi 6 AX200 | iwlwifi | iwlwifi | iwlwifi |  |
| Intel Wi-Fi 6 AX201 (CNVi) | `8086:a0f0` `8086:02f0` `8086:06f0` `8086:34f0` `8086:43f0` `8086:4df0` | Wi-Fi 6 AX201; 400 Series Chipset Family On-Package CNVi WiFi; 400 Series Chipset Family CNVi Wi-Fi and 3 more | iwlwifi | iwlwifi | iwlwifi |  |
| Intel Wi-Fi 6E AX210 | `8086:2725` | Wi-Fi 6E(802.11ax) AX210/AX1675* 2x2 [Typhoon Peak] | iwlwifi | iwlwifi | iwlwifi |  |
| Intel Wi-Fi 6E AX211 (CNVi of Alder / Raptor / Meteor Lake) | `8086:51f0` `8086:51f1` `8086:54f0` `8086:7a70` `8086:7af0` `8086:7e40` `8086:7f70` | Alder Lake-P PCH CNVi WiFi; Raptor Lake PCH CNVi WiFi; Alder Lake-N PCH CNVi WiFi and 4 more | iwlwifi | iwlwifi | iwlwifi |  |
| Intel Wi-Fi 7 BE200 / BE202 | `8086:272b` | Wi-Fi 7(802.11be) AX1775*/AX1790*/BE20*/BE401/BE1750* 2x2 | iwlwifi | iwlwifi | iwlwifi |  |
| Intel Wi-Fi 7 BE201 (CNVi of Arrow / Lunar / Panther Lake) | `8086:7740` `8086:a840` `8086:e340` `8086:e440` `8086:d340` | Arrow Lake CNVi WiFi; BE200 Series Wi-Fi 7; Core Ultra Processors (Series 3) CNVi Wi-Fi and 1 more | iwlwifi | iwlwifi | iwlwifi |  |
| Realtek RTL8852AE | `10ec:8852` `10ec:a85a` | RTL8852AE 802.11ax PCIe Wireless Network Adapter; RTL8852AE WiFi 6 802.11ax PCIe Adapter | rtw89_8852ae | rtw89_8852ae | rtw89_8852ae |  |
| Realtek RTL8852BE | `10ec:b852` `10ec:b85b` | RTL8852BE PCIe 802.11ax Wireless Network Controller; RTL8852BE PCIe 802.11ax Wireless Network Controller [1T1R] | rtw89_8852be | rtw89_8852be | rtw89_8852be |  |
| Realtek RTL8852BE-VT | `10ec:b520` | RTL8852BE-VT PCIe 802.11ax Wireless Network Controller | **no driver** | no driver | rtw89_8852bte | silik hw driver add rtw89_usb |
| Realtek RTL8852CE | `10ec:c852` | RTL8852CE PCIe 802.11ax Wireless Network Controller | rtw89_8852ce | rtw89_8852ce | rtw89_8852ce |  |
| Realtek RTL8851BE | `10ec:b851` | RTL8851BE PCIe 802.11ax Wireless Network Controller | **no driver** | no driver | rtw89_8851be | silik hw driver add rtw89_usb |
| Realtek RTL8922AE (Wi-Fi 7) | `10ec:8922` | RTL8922AE 802.11be PCIe Wireless Network Adapter | **no driver** | no driver | rtw89_8922ae | silik hw driver add rtw89_usb |
| Realtek RTL8821CE | `10ec:c821` `10ec:b821` | RTL8821CE 802.11ac PCIe Wireless Network Adapter; RTL8821CE PCIe 802.11ac Wireless Network Controller | rtw88_8821ce | rtw88_8821ce | rtw88_8821ce |  |
| Realtek RTL8822CE | `10ec:c822` `10ec:c82f` | RTL8822CE 802.11ac PCIe Wireless Network Adapter | rtw88_8822ce | rtw88_8822ce | rtw88_8822ce |  |
| Realtek RTL8822BE / RTL8723DE | `10ec:b822` | RTL8822BE 802.11a/b/g/n/ac WiFi adapter | rtw88_8822be | rtw88_8822be | rtw88_8822be |  |
| Realtek RTL8822BE / RTL8723DE | `10ec:d723` | RTL8723DE 802.11b/g/n PCIe Adapter | rtw88_8723de | rtw88_8723de | rtw88_8723de |  |
| MediaTek MT7921 | `14c3:7961` `14c3:0608` | MT7921 802.11ax PCIe Wireless Network Adapter [Filogic 330]; MT7921K (RZ608) Wi-Fi 6E 80MHz | mt7921e | mt7921e | mt7921e |  |
| MediaTek MT7922 | `14c3:7922` `14c3:0616` | MT7922 802.11ax PCI Express Wireless Network Adapter | mt7921e | mt7921e | mt7921e |  |
| MediaTek MT7925 (Wi-Fi 7) | `14c3:7925` `14c3:0717` | MT7925 802.11be 160MHz 2x2 PCIe Wireless Network Adapter [Filogic 360]; MT7925 (RZ717) Wi-Fi 7 160MHz | mt7925e | mt7925e | mt7925e |  |
| MediaTek MT7927 / MT7902 | `14c3:7927` | MT7927 802.11be 320MHz 2x2 PCIe Wireless Network Adapter [Filogic 380] | **no driver** | no driver | mt7925e | no driver in EL 9's kernel: a cable, or a USB Wi-Fi adapter it drives |
| MediaTek MT7927 / MT7902 | `14c3:7902` | MT7902 802.11ax PCIe Wireless Network Adapter [Filogic 310] | **no driver** | no driver | mt7921e | no driver in EL 9's kernel: a cable, or a USB Wi-Fi adapter it drives |
| Qualcomm QCA6390 | `17cb:1101` | QCA6390 Wireless Network Adapter | ath11k_pci | ath11k_pci | ath11k_pci |  |
| Qualcomm WCN6855 (QCNFA765) | `17cb:1103` | QCNFA765 Wireless Network Adapter | ath11k_pci | ath11k_pci | ath11k_pci |  |
| Qualcomm WCN7850 (Wi-Fi 7) | `17cb:1107` | NCM8x5/WCN785x Wi-Fi 7(802.11be) 320MHz 2x2 [FastConnect 7800] | ath12k | ath12k | ath12k_wifi7 |  |
| Qualcomm QCA6174 / QCA9377 | `168c:003e` `168c:0042` | QCA6174 802.11ac Wireless Network Adapter; QCA9377 802.11ac Wireless Network Adapter | ath10k_pci | ath10k_pci | ath10k_pci |  |
| Broadcom BCM4360 / BCM4352 / BCM4331 / BCM43142 (bcma bus) | `14e4:43a0` `14e4:43b1` `14e4:4331` | BCM4360 802.11ac Dual Band Wireless Network Adapter; BCM4352 802.11ac Dual Band Wireless Network Adapter; BCM4331 802.11a/b/g/n | bcma (the bus only) | bcma | bcma | silik hw driver add wl; bcma is the bus; EL 9.8 has no b43 for the radio on it |
| Broadcom BCM4360 / BCM4352 / BCM4331 / BCM43142 (bcma bus) | `14e4:4365` | BCM43142 802.11b/g/n | bcma, brcmfmac | bcma, brcmfmac | bcma, brcmfmac | silik hw driver add wl; bcma is the bus; EL 9.8 has no b43 for the radio on it |
| Broadcom BCM4350 / BCM4356 / BCM43602 (FullMAC) | `14e4:43a3` `14e4:43ec` `14e4:43ba` | BCM4350 802.11ac Wireless Network Adapter; BCM4356 802.11ac Wireless Network Adapter; BCM43602 802.11ac Wireless LAN SoC | brcmfmac | brcmfmac | brcmfmac |  |
| Broadcom BCM4364 / BCM4377 / BCM4378 / BCM4387 (Apple machines) | `14e4:4464` `14e4:4488` `14e4:4425` `14e4:4433` | BCM4364 802.11ac Wireless Network Adapter; BCM4377b Wireless Network Adapter; BCM4378 802.11ax Dual Band Wireless Network Adapter and 1 more | brcmfmac | brcmfmac | brcmfmac |  |
<!-- /gen -->

<!-- gen:wifi-cov -->
| Family | Bus | Modules in EL 9.8 x86_64 (package) | IDs upstream claims | of them in EL 9.8 x86_64 | in EL 9.8 aarch64 | Upstream IDs EL 9.8 does not claim |
|---|---|---|---|---|---|---|
| Intel Wi-Fi (iwlwifi) | pci | iwlwifi | 89 | 85 | 85 | `8086:4222` PRO/Wireless 3945ABG [Golan] Network Connection, `8086:4227` PRO/Wireless 3945ABG [Golan] Network Connection, `8086:4229` PRO/Wireless 4965 AG or AGN [Kedron] Network Connection, `8086:4230` PRO/Wireless 4965 AG or AGN [Kedron] Network Connection; modules not in EL: iwl3945, iwl4965 |
| Realtek 802.11ac (rtw88) | pci | rtw88_8723de, rtw88_8821ce, rtw88_8822be, rtw88_8822ce | 7 | 6 | 6 | `10ec:8813` RTL8813AE 802.11ac PCIe Wireless Network Adapter; modules not in EL: rtw88_8814ae |
| Realtek Wi-Fi 6 / 7 (rtw89) | pci | rtw89_8852ae, rtw89_8852be, rtw89_8852ce | 9 | 5 | 5 | `10ec:8922` RTL8922AE 802.11be PCIe Wireless Network Adapter, `10ec:892b`, `10ec:b520` RTL8852BE-VT PCIe 802.11ax Wireless Network Controller, `10ec:b851` RTL8851BE PCIe 802.11ax Wireless Network Controller; modules not in EL: rtw89_8851be, rtw89_8852bte, rtw89_8922ae |
| Realtek 802.11n / older ac (rtlwifi) | pci | rtl8188ee, rtl8192ce, rtl8192de, rtl8192ee, rtl8192se, rtl8723ae, rtl8723be, rtl8821ae | 27 | 17 | 17 | `10ec:8180` RTL8180L 802.11b MAC, `10ec:8185` RTL-8185 IEEE 802.11a/b/g Wireless LAN Controller, `10ec:8199` RTL8187SE Wireless LAN Controller, `1186:3300` DWL-510 / DWL-610 802.11b [Realtek RTL8180L], `1186:3301`, `1432:7106` and 4 more; modules not in EL: rtl818x_pci |
| MediaTek (mt76) | pci | mt76x0e, mt76x2e, mt7921e, mt7925e | 32 | 14 | 14 | `14c3:0738`, `14c3:6639`, `14c3:7603` MT7603E 802.11bgn PCI Express Wireless Network Adapter, `14c3:7611`, `14c3:7615` MT7615E 802.11ac PCI Express Wireless Network Adapter, `14c3:7663` MT7663 802.11ac PCI Express Wireless Network Adapter and 12 more; modules not in EL: mt7603e, mt7615e, mt7915e, mt7996e |
| Qualcomm Atheros (ath) | pci | ath10k_pci, ath11k_pci, ath12k, ath9k | 54 | 29 | 29 | `10b7:0013` AR5212 802.11abg NIC (3CRDAG675), `168c:0007` AR5210 Wireless Network Adapter [AR5000 802.11a], `168c:0011` AR5211 Wireless Network Adapter [AR5001A 802.11a], `168c:0012` AR5211 Wireless Network Adapter [AR5001X 802.11ab], `168c:0013` AR5212/5213/2414 Wireless Network Adapter, `168c:0014` and 19 more; modules not in EL: ath12k_wifi7, ath5k, wil6210 |
| Broadcom | pci | bcma, brcmfmac, brcmsmac | 66 | 45 | 45 | `14a4:4318` Broadcom BCM4318 [AirForce One 54g] 802.11g WLAN Controller, `14e4:4301` BCM4301 802.11b Wireless LAN Controller, `14e4:4306` BCM4306 802.11bg Wireless LAN controller, `14e4:4307` BCM4306 802.11bg Wireless LAN Controller, `14e4:4311` BCM4311 802.11b/g WLAN, `14e4:4312` BCM4311 802.11a/b/g and 15 more; modules not in EL: b43, b43legacy, ssb |
| USB Wi-Fi adapters | usb | ath9k_htc, brcmfmac, mt7601u, mt76x0u, mt76x2u, rt2800usb, rtl8192cu, rtl8xxxu, rtw88_8822bu | 1039 | 566 | 566 | `0053:5301` GW-US54ZGL 802.11bg, `0105:145f` NW-3100 802.11b/g 54Mbps Wireless Network Adapter [zd1211], `03f0:ca02`, `0409:0248` Aterm PA-WL54GU, `0409:0249` Aterm WL300NU-G, `0409:02b4` Aterm WL300NU-AG and 467 more; modules not in EL: ar5523, ath10k_usb, carl9170, mt7663u, mt7921u, mt7925u, rt2500usb, rt73usb, rtl8187, rtl8192du, rtw88_8723du, rtw88_8812au, rtw88_8814au, rtw88_8821au, rtw88_8821cu, rtw88_8822cu, rtw89_8851bu, rtw89_8852au, rtw89_8852bu, rtw89_8852cu, rtw89_8922au, zd1211rw |
| Bluetooth (btusb: by class, and these IDs by name) | usb | ath3k, bfusb, bpa10x, btusb | 96 | 95 | 95 | `0471:0215` |
<!-- /gen -->

- Intel's CNVi cards have the platform's ID, not the radio's: AX201, AX211 and BE201 are the radios behind those rows.
- Bluetooth is USB: `btusb` takes any Bluetooth-class device and names some by ID; which chips it can start is inside
  `btintel`, `btrtl`, `btmtk`, `btbcm` (all four are in EL 9.8) and their firmware (table above): not visible here.
- Broadcom: `brcmfmac` (FullMAC chips) is there; `bcma` is only the bus of the BCM43xx SoftMAC cards, and `brcmsmac`
  drives few of them. EL 9.8 has no `b43`. ELRepo's `kmod-wl` is Broadcom's own driver; its README lists 0x4311-0x4365,
  0x4331, 0x43a0 among others (<https://github.com/elrepo/packages>, `wl-kmod/el9/README.txt`).

### Ethernet

<!-- gen:net -->
| Device | IDs | Name (pci.ids) | EL 9.8 x86_64 | EL 9.8 aarch64 | Linux 7.2.11 (Fedora 45) | Note |
|---|---|---|---|---|---|---|
| Intel I219 (the PCH's Ethernet, Tiger Lake and newer) | `8086:15fb` `8086:15fc` `8086:1a1c` `8086:1a1d` `8086:1a1e` `8086:1a1f` `8086:0dc5` `8086:0dc6` `8086:550a` `8086:550e` `8086:5510` `8086:57a0` `8086:57b3` | Ethernet Connection (13) I219-LM; Ethernet Connection (13) I219-V; Ethernet Connection (17) I219-LM and 10 more | e1000e | e1000e | e1000e |  |
| Intel I219 (the PCH's Ethernet, Tiger Lake and newer) | `8086:57b5` | Ethernet Connection (26) I219-LM | e1000e | e1000e | no driver |  |
| Intel I219 (the PCH's Ethernet, Tiger Lake and newer) | `8086:57b7` `8086:57b9` | Ethernet Connection (27) I219-LM; Ethernet Connection (29) I219-LM | e1000e | e1000e | e1000e |  |
| Intel I225 | `8086:15f2` `8086:15f3` `8086:0d9f` | Ethernet Controller I225-LM; Ethernet Controller I225-V; Ethernet Controller I225-IT | igc | igc | igc |  |
| Intel I226 | `8086:125b` `8086:125c` `8086:125d` `8086:3102` | Ethernet Controller I226-LM; Ethernet Controller I226-V; Ethernet Controller I226-IT and 1 more | igc | igc | igc |  |
| Intel I210 / I211 | `8086:1533` `8086:1539` | I210 Gigabit Network Connection; I211 Gigabit Network Connection | igb | igb | igb |  |
| Realtek RTL8111 / RTL8168 | `10ec:8168` `10ec:8161` | RTL8111/8168/8211/8411 PCI Express Gigabit Ethernet Controller; RTL8111/8168/8411 PCI Express Gigabit Ethernet Controller | r8169 | r8169 | r8169 |  |
| Realtek RTL8125 (2.5G) | `10ec:8125` | RTL8125 2.5GbE Controller | r8169 | r8169 | r8169 |  |
| Realtek RTL8126 (5G) | `10ec:8126` | RTL8126 5GbE Controller | r8169 | r8169 | r8169 |  |
| Realtek RTL8127 (10G) | `10ec:8127` | RTL8127 10GbE Controller | **no driver** | no driver | r8169 | silik hw driver add r8127 |
| Marvell (Aquantia) AQC107 | `1d6a:07b1` `1d6a:d107` `1d6a:0001` | AQtion AQC107 NBase-T/IEEE 802.3an Ethernet Controller [Atlantic 10G]; AQC107 NBase-T/IEEE 802.3bz Ethernet Controller [AQtion] | atlantic | no driver | atlantic |  |
| Marvell (Aquantia) AQC113 | `1d6a:04c0` `1d6a:14c0` `1d6a:94c0` | AQtion AQC113 NBase-T/IEEE 802.3an Ethernet Controller [Antigua 10G]; AQC113C NBase-T/IEEE 802.3an Ethernet Controller [Marvell Scalable mGig]; AQtion AQC113CS NBase-T/IEEE 802.3an Ethernet Controller [Antigua 10G] | atlantic | no driver | atlantic |  |
| Intel X550 / X540 (10G) | `8086:1563` `8086:15d1` `8086:1528` | Ethernet Controller X550; Ethernet Controller 10G X550T; Ethernet Controller 10-Gigabit X540-AT2 | ixgbe | ixgbe | ixgbe |  |
| Intel X710 / XXV710 (10 / 25G) | `8086:1572` `8086:15ff` `8086:158b` | Ethernet Controller X710 for 10GbE SFP+; Ethernet Controller X710 for 10GBASE-T; Ethernet Controller XXV710 for 25GbE SFP28 | i40e | i40e | i40e |  |
| Intel E810 (25 / 100G) | `8086:1593` `8086:159b` `8086:1592` | Ethernet Controller E810-C for SFP; Ethernet Controller E810-XXV for SFP; Ethernet Controller E810-C for QSFP | ice | ice | ice |  |
| NVIDIA (Mellanox) ConnectX-4 Lx / 5 / 6 Dx / 7 | `15b3:1015` `15b3:1017` `15b3:101d` `15b3:1021` | MT27710 Family [ConnectX-4 Lx]; MT27800 Family [ConnectX-5]; MT2892 Family [ConnectX-6 Dx] and 1 more | mlx5_core | mlx5_core | mlx5_core |  |
| Broadcom NetXtreme-E BCM57414 / BCM57416 / BCM57508 | `14e4:16d7` `14e4:16d8` `14e4:1750` | BCM57414 NetXtreme-E 10Gb/25Gb RDMA Ethernet Controller; BCM57416 NetXtreme-E Dual-Media 10G RDMA Ethernet Controller; BCM57508 NetXtreme-E 10Gb/25Gb/40Gb/50Gb/100Gb/200Gb Ethernet | bnxt_en | bnxt_en | bnxt_en |  |
| Broadcom NetXtreme BCM5720 (1G) | `14e4:165f` | NetXtreme BCM5720 Gigabit Ethernet PCIe | tg3 | tg3 | tg3 |  |
<!-- /gen -->

<!-- gen:net-cov -->
| Family | Bus | Modules in EL 9.8 x86_64 (package) | IDs upstream claims | of them in EL 9.8 x86_64 | in EL 9.8 aarch64 | Upstream IDs EL 9.8 does not claim |
|---|---|---|---|---|---|---|
| Intel 1G / 2.5G | pci | e1000 (core), e1000e (core), igb (core), igc (core) | 201 | 201 | 201 | none |
| Intel 10 / 25 / 40 / 100G | pci | fm10k (core), i40e (core), iavf (core), ice (core), idpf (core), igbvf (core), ixgbe (core), ixgbevf (core) | 150 | 150 | 150 | none |
| Realtek | pci | 8139cp (core), 8139too (core), r8169 (core) | 46 | 44 | 44 | `10ec:0e10`, `10ec:8127` RTL8127 10GbE Controller |
| Marvell Aquantia (atlantic) | pci | atlantic | 25 | 25 | 0 | none |
| Broadcom | pci | bnx2, bnx2x, bnxt_en, tg3 | 201 | 198 | 198 | `14e4:170c` BCM4401-B0 100Base-TX, `14e4:4401` BCM4401 100Base-T, `14e4:4402` BCM4402 Integrated 10/100BaseT; modules not in EL: b44 |
| NVIDIA Mellanox | pci | mlx4_core (core), mlx5_core (core), mlxsw_pci (core) | 52 | 49 | 49 | `15b3:1025` CX9 Family [ConnectX-9], `15b3:1027` CX10 Family [ConnectX-10], `15b3:2101` CX10 Family [ConnectX-10 NVLink-C2C] |
| Other server cards (Chelsio, Marvell / QLogic, Solarflare, Pensando, Netronome, Emulex, Cisco, Huawei, Amazon, Microsoft, Google) | pci | alx, atl1c, atl1e, be2net, cxgb4, cxgb4vf, ena (core), enic, gve (core), hinic (core), ionic (core), mana (core), nfp (core), qed, qede, sfc, sfc_siena | 664 | 432 | 407 | `1011:0009` DECchip 21140 [FasterNet], `1011:0019` DECchip 21142/43, `104a:0981` 21x4x DEC-Tulip compatible 10/100 Ethernet, `104a:2774` 21x4x DEC-Tulip compatible 10/100 Ethernet, `10b7:1201` 3c982-TXM 10/100baseTX Dual Port A [Hydra], `10b7:1202` 3c982-TXM 10/100baseTX Dual Port B [Hydra] and 226 more; modules not in EL: 3c59x, e100, forcedeth, jme, ngbe, skge, sky2, tulip, txgbe |
| USB Ethernet adapters and docks | usb | asix, ax88179_178a, cdc_ether, cdc_mbim, cdc_ncm, lan78xx, qmi_wwan, r8152, r8153_ecm, rndis_host, smsc75xx, smsc95xx | 540 | 518 | 518 | `05ac:12a8` iPhone 5/5C/5S/6/SE/7/8/X/XR, `05ac:12ab` iPad, `05ac:1905`, `05c6:9091` Intex Aqua Fish & Jolla C Diagnostic Mode, `05c6:90db`, `0878:1400` and 16 more; modules not in EL: aqc111 |
<!-- /gen -->

### Graphics

**Intel**: the IDs per platform are the kernel's own header (`include/drm/intel/pciids.h`); "binds" / "needs
force_probe" is the `require_force_probe` flag of the platform's entry in `i915_pci.c` and `xe_pci.c`, in EL's source and
in the upstream one.

<!-- gen:intel-gpu -->
| Platform (the names of the kernel's ID header are the short ones) | Macro | IDs upstream | IDs in EL's header | EL 9.8 i915 | EL 9.8 xe | IDs claimed in EL's modules.alias | upstream i915 | upstream xe |
|---|---|---|---|---|---|---|---|---|
| Tiger Lake (11th gen Core) | TGL | 11 | 11 | binds | needs force_probe | i915 11, xe 11 | binds | needs force_probe |
| Rocket Lake | RKL | 6 | 6 | binds | needs force_probe | i915 6, xe 6 | binds | needs force_probe |
| DG1 (Iris Xe MAX) | DG1 | 5 | 5 | binds | needs force_probe | i915 5, xe 5 | binds | needs force_probe |
| Alder Lake-S | ADLS | 8 | 8 | binds | needs force_probe | i915 8, xe 8 | binds | needs force_probe |
| Alder Lake-P | ADLP | 18 | 18 | binds | needs force_probe | i915 18, xe 18 | binds | needs force_probe |
| Alder Lake-N | ADLN | 5 | 5 | binds | needs force_probe | i915 5, xe 5 | binds | needs force_probe |
| Raptor Lake-S | RPLS | 8 | 8 | binds | needs force_probe | i915 8, xe 8 | binds | needs force_probe |
| Raptor Lake-P | RPLP | 5 | 5 | binds | needs force_probe | i915 5, xe 5 | binds | needs force_probe |
| Raptor Lake-U | RPLU | 5 | 5 | binds | needs force_probe | i915 5, xe 5 | binds | needs force_probe |
| DG2 (Arc A-series) | DG2 | 25 | 25 | binds | needs force_probe | i915 25, xe 25 | binds | needs force_probe |
| Meteor Lake (Core Ultra 1xx) | MTL | 5 | 5 | binds | needs force_probe | i915 5, xe 5 | binds | needs force_probe |
| Arrow Lake (Core Ultra 2xx H/U/S) | ARL | 5 | 5 | binds | needs force_probe | i915 5, xe 5 | binds | needs force_probe |
| Lunar Lake (Core Ultra 2xx V) | LNL | 3 | 3 | not listed | binds | xe 3 | not listed | binds |
| Battlemage (Arc B-series) | BMG | 13 | 13 | not listed | binds | xe 13 | not listed | binds |
| Panther Lake (Core Ultra 3xx) | PTL | 12 | 12 | not listed | binds | xe 12 | not listed | binds |
| Wildcat Lake | WCL | 2 | 2 | not listed | binds | xe 2 | not listed | binds |
| Nova Lake-S | NVLS | 6 | 0 | not listed | not listed | none | not listed | needs force_probe |
| Nova Lake-P | NVLP | 5 | 0 | not listed | not listed | none | not listed | needs force_probe |
<!-- /gen -->

So on EL 9.8: `i915` for everything through Meteor Lake and Arrow Lake and the Arc A-series, `xe` for Lunar Lake, the Arc
B-series, Panther Lake and Wildcat Lake: the same split as the upstream kernel. The firmware files both name are all in
`linux-firmware` (table above).

**AMD**: `amdgpu` claims every AMD display device by class, then reads from the card which IP blocks it has. What it
can drive is the list of versions in `amdgpu_discovery.c`:

<!-- gen:amd-gc -->
| IP block handled by amdgpu (amdgpu_discovery.c) | Versions in EL 9.8 | Newest in EL 9.8 | In the upstream kernel only |
|---|---|---|---|
| GC (graphics core) | 35 | 12.0.1 | 11.5.4, 11.5.6, 11.7.0, 11.7.1, 12.1.0 |
| DCN (display) | 24 | 12.1.0 | 4.2.0, 4.2.1 |
<!-- /gen -->

Which product has which version is not in the packages. [A, from memory, not from a source read here: Ryzen 7040 / 8040
is GC 11.0.x, Ryzen AI 300 is GC 11.5.x, Radeon RX 7000 is GC 11.0.x, Radeon RX 9000 is GC 12.0.x: all within EL 9.8's
list; the versions only the upstream kernel has are 2026 products.] `amdgpu` names 583 firmware files; 575 are in
`linux-firmware`.

**NVIDIA**: `nouveau` claims every NVIDIA display device by class. Its chip table
(`drivers/gpu/drm/nouveau/nvkm/engine/device/base.c`) is the same in EL 9.8 as in Linux 7.2: 103 chips, through GA1xx
(RTX 30), AD1xx (RTX 40) and GB20x (RTX 50), and `linux-firmware` carries the GSP firmware it loads for them
(`nvidia/*/gsp/`). nouveau gives a desktop; it gives no CUDA, and its speed and power management were not measured
here. NVIDIA's own driver: section 5.

<!-- gen:gpu -->
| Device | IDs | Name (pci.ids) | EL 9.8 x86_64 | EL 9.8 aarch64 | Linux 7.2.11 (Fedora 45) | Note |
|---|---|---|---|---|---|---|
| AMD Ryzen 4000 / 5000 (Renoir, Lucienne, Cezanne, Barcelo) | `1002:1636` `1002:164c` `1002:1638` `1002:15e7` | Renoir [Radeon Vega Series / Radeon Vega Mobile Series]; Lucienne; Cezanne [Radeon Vega Series / Radeon Vega Mobile Series] and 1 more | amdgpu | amdgpu | amdgpu |  |
| AMD Ryzen 6000 / 7035 (Rembrandt) | `1002:1681` | Rembrandt [Radeon 660M / 680M] | amdgpu | amdgpu | amdgpu |  |
| AMD Ryzen 7020 (Mendocino), Ryzen 7000 / 9000 desktop (Raphael, Granite Ridge) | `1002:1506` `1002:164e` `1002:13c0` | Mendocino [Radeon 610M]; Raphael [Radeon 610M]; Granite Ridge [Radeon 610M] | amdgpu | amdgpu | amdgpu |  |
| AMD Ryzen 7040 / 8040 (Phoenix, Hawk Point) | `1002:15bf` `1002:15c8` `1002:1900` `1002:1901` | Phoenix1 [Radeon 740M / 760M / 780M Graphics]; Phoenix2 [Radeon 740M Graphics]; HawkPoint1 [Radeon 760M / 780M Graphics] and 1 more | amdgpu | amdgpu | amdgpu |  |
| AMD Ryzen AI 300 (Strix, Krackan, Strix Halo) | `1002:150e` `1002:1114` `1002:1902` `1002:1586` | Strix [Radeon 880M / 890M]; Krackan [Radeon 840M / 860M Graphics]; Krackan2 [Radeon 820M / 840M Graphics] and 1 more | amdgpu | amdgpu | amdgpu |  |
| AMD Radeon RX 6000 (Navi 21-24) | `1002:73bf` `1002:73df` `1002:73ff` `1002:743f` | Navi 21 [Radeon RX 6800/6800 XT / 6900 XT]; Navi 22 [Radeon RX 6700/6700 XT/6750 XT / 6800M/6850M XT]; Navi 23 [Radeon RX 6600/6600 XT/6600M] and 1 more | amdgpu | amdgpu | amdgpu |  |
| AMD Radeon RX 7000 (Navi 31-33) | `1002:744c` `1002:747e` `1002:7480` | Navi 31 [Radeon RX 7900 XT/7900 XTX/7900 GRE/7900M]; Navi 32 [Radeon RX 7700 XT / 7800 XT]; Navi 33 [Radeon RX 7600/7600 XT/7600M XT/7600S/7700S / PRO W7600] | amdgpu | amdgpu | amdgpu |  |
| AMD Radeon RX 9000 (Navi 44, 48) | `1002:7550` `1002:7590` | Navi 48 [Radeon RX 9070/9070 XT/9070 GRE]; Navi 44 [Radeon RX 9050 / 9060 XT] | amdgpu | amdgpu | amdgpu |  |
| NVIDIA GeForce GTX 900 / 1000 (Maxwell, Pascal) | `10de:13c2` `10de:1c03` `10de:1b06` | GM204 [GeForce GTX 970]; GP106 [GeForce GTX 1060 6GB]; GP102 [GeForce GTX 1080 Ti] | nouveau | nouveau | nouveau | silik hw nvidia install; nouveau claims it; NVIDIA's 580 legacy driver is the one with CUDA |
| NVIDIA GeForce RTX 2000 / GTX 1600 (Turing) | `10de:1f0a` `10de:1f82` | TU106 [GeForce GTX 1650]; TU117 [GeForce GTX 1650] | nouveau | nouveau | nouveau | silik hw nvidia install; nouveau claims it |
| NVIDIA GeForce RTX 3000 (Ampere) | `10de:2487` `10de:2501` `10de:2503` `10de:2520` `10de:2544` `10de:2560` | GA104 [GeForce RTX 3060]; GA106 [GeForce RTX 3060]; GA106M [GeForce RTX 3060 Mobile / Max-Q] | nouveau | nouveau | nouveau | silik hw nvidia install; nouveau claims it |
| NVIDIA GeForce RTX 4000 (Ada) | `10de:2786` `10de:2808` `10de:2882` | AD104 [GeForce RTX 4070]; AD106 [GeForce RTX 4060]; AD107 [GeForce RTX 4060] | nouveau | nouveau | nouveau | silik hw nvidia install; nouveau claims it |
| NVIDIA GeForce RTX 5000 (Blackwell) | `10de:2b85` `10de:2c09` `10de:2d05` `10de:2f04` `10de:2f06` | GB202 [GeForce RTX 5090]; GB203 [GeForce RTX 5070]; GB206 [GeForce RTX 5060] and 2 more | nouveau | nouveau | nouveau | silik hw nvidia install; nouveau claims it |
<!-- /gen -->

<!-- gen:gpu-cov -->
| Family | Bus | Modules in EL 9.8 x86_64 (package) | IDs upstream claims | of them in EL 9.8 x86_64 | in EL 9.8 aarch64 | Upstream IDs EL 9.8 does not claim |
|---|---|---|---|---|---|---|
| Intel (i915, xe) | pci | i915, xe | 441 | 394 | 0 | `8086:0be0` Atom Processor D2xxx/N2xxx Integrated Graphics Controller, `8086:0be1` Atom Processor D2xxx/N2xxx Integrated Graphics Controller, `8086:0be2` Atom Processor D2xxx/N2xxx Integrated Graphics Controller, `8086:0be3` Atom Processor D2xxx/N2xxx Integrated Graphics Controller, `8086:0be4` Atom Processor D2xxx/N2xxx Integrated Graphics Controller, `8086:0be5` Atom Processor D2xxx/N2xxx Integrated Graphics Controller and 41 more; modules not in EL: gma500_gfx |
| AMD (amdgpu, radeon) | pci | amdgpu, radeon | 861 | 861 | 861 | none |
| NVIDIA (nouveau) | pci | nouveau | 2 | 2 | 2 | none |
| Server and virtual (ast, mgag200, virtio, vmware, qxl, bochs, hyperv) | pci | ast, bochs (core), hyperv_drm (core), mgag200, qxl (core), virtio_gpu (core), vmwgfx (core) | 20 | 19 | 19 | `80ee:beef` VirtualBox Graphics Adapter; modules not in EL: vboxvideo |
<!-- /gen -->

### Storage, Thunderbolt / USB4, card readers, audio, cameras, platform devices

<!-- gen:parts -->
| Device | IDs | Name (pci.ids) | EL 9.8 x86_64 | EL 9.8 aarch64 | Linux 7.2.11 (Fedora 45) | Note |
|---|---|---|---|---|---|---|
| NVMe SSD (any, by class) | `144d:a80a` | NVMe SSD Controller PM9A1/PM9A3/980PRO | nvme | nvme | nvme |  |
| SATA AHCI (any, by class) | `8086:a0d3` | 500 Series Chipset Family On-Package SATA Controller (AHCI) | ahci | ahci | ahci (built in) |  |
| Intel VMD (RST) | `8086:9a0b` `8086:467f` `8086:a77f` `8086:7d0b` `8086:ad0b` | 11th Gen Core Processor Volume Management Device; Volume Management Device NVMe RAID Controller; RST Volume Management Device Controller and 2 more | vmd | no driver | vmd |  |
| Realtek PCIe card readers | `10ec:5227` `10ec:522a` `10ec:5249` `10ec:525a` `10ec:5260` `10ec:5261` `10ec:5264` `10ec:5228` | RTS5227 PCI Express Card Reader; RTS522A PCI Express Card Reader; RTS5249 PCI Express Card Reader and 5 more | rtsx_pci | no driver | rtsx_pci |  |
| Genesys Logic GL975x SD host | `17a0:9750` `17a0:9755` `17a0:9767` | GL9750 SD Host Controller; GL9755 SD Host Controller; GL9767 PCIe SD UHS-II & SD Express Card Reader Controller | sdhci_pci | sdhci_pci | sdhci_pci |  |
| O2 Micro / BayHub SD host | `1217:8621` `1217:8620` | OZ711 SD/MMC Card Reader Controller; OZ620 SD/MMC Card Reader Controller | sdhci_pci | sdhci_pci | sdhci_pci |  |
| Thunderbolt 4 / USB4: Intel (Tiger, Alder, Raptor, Meteor, Lunar Lake; Maple / Barlow Ridge) | `8086:9a1b` `8086:463e` `8086:a73e` `8086:7ec2` `8086:a833` `8086:e333` `8086:1134` `8086:5781` | 11th Gen Core Processor Thunderbolt DMA #0; Alder Lake-P Thunderbolt 4 NHI #0; Raptor Lake-P Thunderbolt 4 NHI #0 and 5 more | thunderbolt | thunderbolt | thunderbolt |  |
| USB4: AMD (Rembrandt, Phoenix, Strix, Krackan) | `1022:162e` `1022:1668` `1022:151c` `1022:1120` | Rembrandt USB4/Thunderbolt NHI controller #1; Pink Sardine USB4/Thunderbolt NHI controller #1; Strix USB4/Thunderbolt NHI controller #1 and 1 more | thunderbolt | thunderbolt | thunderbolt |  |
| Intel audio: Tiger / Alder / Raptor Lake | `8086:a0c8` `8086:51c8` `8086:51ca` `8086:54c8` `8086:7ad0` | 500 Series Chipset Family On-Package High Definition Audio (HD Audio); Alder Lake PCH-P High Definition Audio Controller; Raptor Lake-P/U/H cAVS and 2 more | snd_hda_intel, snd_soc_avs, snd_sof_pci_intel_tgl | snd_hda_intel | snd_hda_intel, snd_soc_avs, snd_sof_pci_intel_tgl |  |
| Intel audio: Meteor / Arrow / Lunar / Panther Lake | `8086:7e28` `8086:7728` | Meteor Lake-P HD Audio Controller; Core Ultra 200H/200V Series Processors HD Audio | snd_hda_intel, snd_sof_pci_intel_mtl | snd_hda_intel | snd_hda_intel, snd_sof_pci_intel_mtl |  |
| Intel audio: Meteor / Arrow / Lunar / Panther Lake | `8086:a828` | Core Ultra 200V Series Processors HD Audio | snd_hda_intel, snd_sof_pci_intel_lnl | snd_hda_intel | snd_hda_intel, snd_sof_pci_intel_lnl |  |
| Intel audio: Meteor / Arrow / Lunar / Panther Lake | `8086:e428` `8086:e328` | Core Ultra Processors (Series 3) HD Audio | snd_hda_intel, snd_sof_pci_intel_ptl | snd_hda_intel | snd_hda_intel, snd_sof_pci_intel_ptl |  |
| AMD audio coprocessor (ACP), every generation shares this ID | `1022:15e2` | Audio Coprocessor | snd_acp_pci, snd_pci_acp5x, snd_pci_acp6x, snd_pci_ps, snd_rn_pci_acp3x, snd_rpl_pci_acp6x, snd_sof_amd_acp63, snd_sof_amd_acp70, snd_sof_amd_rembrandt, snd_sof_amd_renoir, snd_sof_amd_vangogh | no driver | snd_acp_pci, snd_pci_acp3x, snd_pci_acp5x, snd_pci_acp6x, snd_pci_acp7x, snd_pci_ps, snd_rn_pci_acp3x, snd_sof_amd_acp63, snd_sof_amd_acp70, snd_sof_amd_rembrandt, snd_sof_amd_renoir, snd_sof_amd_vangogh | the generation is told by the revision, inside the driver |
| Intel IPU6 (MIPI camera of Tiger / Alder / Raptor / Meteor Lake laptops) | `8086:9a19` `8086:465d` `8086:a75d` `8086:7d19` | 11th Gen Core Processor Image Processing Unit; Alder Lake Imaging Signal Processor; Raptor Lake IPU and 1 more | **no driver** | no driver | intel_ipu6 | no driver in EL 9's kernel: a USB webcam (uvcvideo) |
| Intel IPU7 (Lunar / Panther Lake) | `8086:645d` `8086:b05d` | Core Ultra 200V Series Processors IPU; Core Ultra Processors (Series 3) IPU | **no driver** | no driver | intel_ipu7 | no driver in EL 9's kernel: a USB webcam (uvcvideo) |
| Intel Serial IO I2C (touchpad, touchscreen): Tiger / Alder / Raptor / Meteor / Arrow / Lunar / Panther Lake | `8086:a0e8` `8086:51e8` `8086:7a4c` `8086:7e78` `8086:7778` `8086:a878` `8086:e478` `8086:e378` | 500 Series Chipset Family On-Package I2C Controller #0; Alder Lake PCH Serial IO I2C Controller #0; 700 Series Chipset Family I2C Controller #0 and 4 more | intel_lpss_pci | no driver | intel_lpss_pci (built in) |  |
| Intel SMBus: the same platforms | `8086:a0a3` `8086:51a3` `8086:7e22` `8086:7722` `8086:e422` | 500 Series Chipset Family On-Package System Management Bus (SMBus); Alder Lake PCH-P SMBus Host Controller; Meteor Lake-P SMBus Controller and 2 more | i2c_i801 | no driver | i2c_i801 |  |
| Intel Integrated Sensor Hub | `8086:a0fc` `8086:51fc` `8086:7e45` `8086:a845` `8086:e445` | 500 Series Chipset Family On-Package Integrated Sensor Hub; Alder Lake-P Integrated Sensor Hub; Meteor Lake-P Integrated Sensor Hub and 2 more | intel_ish_ipc | no driver | intel_ish_ipc |  |
| Intel NPU (Meteor / Arrow / Lunar / Panther Lake), AMD NPU (Ryzen AI) | `8086:7d1d` `8086:ad1d` `8086:643e` `8086:b03e` | Core Ultra 200H/200V Series Processors NPU; Core Ultra 200 Series Processors NPU; Core Ultra 200V Series Processors NPU and 1 more | intel_vpu | no driver | intel_vpu |  |
| Intel NPU (Meteor / Arrow / Lunar / Panther Lake), AMD NPU (Ryzen AI) | `1022:1502` `1022:17f0` | Phoenix/Hawk Point Neural Processing Unit; Strix/Krackan/Krackan2/Strix Halo Neural Processing Unit | **no driver** | no driver | amdxdna | no driver in EL 9's kernel; amdxdna drives it |
<!-- /gen -->

<!-- gen:parts-cov -->
| Family | Bus | Modules in EL 9.8 x86_64 (package) | IDs upstream claims | of them in EL 9.8 x86_64 | in EL 9.8 aarch64 | Upstream IDs EL 9.8 does not claim |
|---|---|---|---|---|---|---|
| NVMe, AHCI, VMD | pci | ahci (core), nvme (core), vmd (builtin) | 93 | 87 | 77 | `1344:6004` 4100AT NVMe SSD (DRAM-less), `1c5f:0555` PBlaze5 510/516, `1dbe:5216` NVMe SSD Controller IG5216 [Shasta+] (DRAM-less), `1fa0:2283`, `2646:502f` OM3SGP4 PCIe 4 NVMe SSD (TLC), `8086:b07f`; built into the upstream kernel, so not compared: ahci |
| RAID and SAS controllers | pci | aacraid, hpsa (core), lpfc, megaraid_sas, mpi3mr (core), mpt3sas, mptsas (core), mptspi (core), qla2xxx, smartpqi (core) | 297 | 200 | 184 | `10df:d300` LPE41100/LPE42100 Series 64G/128G Fibre Channel Adapter, `1103:2640` RocketRAID 2640 SAS/SATA Controller, `1103:2710`, `1103:2720` RocketRAID 2720 PCIe Gen2 6Gb/s SAS/SATA Controller, `1103:2721`, `1103:2722` RocketRAID 2722 and 91 more; modules not in EL: 3w_9xxx, 3w_sas, arcmsr, isci, mvsas, pm80xx |
| Card readers and SD hosts | pci | cb710 (core), jmb38x_ms, rtsx_pci (core), sdhci_pci, tifm_7xx1 (core), via_sdmmc | 120 | 112 | 96 | `1179:0805` SD TypA Controller, `1217:9860`, `1217:9861`, `1217:9862`, `1217:9863`, `1aea:6601` AU6601 PCI-E Flash card reader controller and 2 more; modules not in EL: alcor_pci, toshsd |
| Thunderbolt / USB4 | pci | thunderbolt (builtin) | 37 | 37 | 37 | none |
| Intel audio (HDA, SOF, AVS) | pci | snd_hda_intel, snd_soc_avs, snd_soc_skl, snd_sof_pci_intel_apl, snd_sof_pci_intel_cnl, snd_sof_pci_intel_icl, snd_sof_pci_intel_lnl, snd_sof_pci_intel_mtl, snd_sof_pci_intel_ptl, snd_sof_pci_intel_tgl, snd_sof_pci_intel_tng | 160 | 158 | 155 | `8086:6e50`, `8086:d328`; modules not in EL: snd_sof_pci_intel_nvl, snd_sof_pci_intel_skl |
| AMD audio coprocessor | pci | snd_acp_legacy_mach, snd_acp_pci, snd_pci_acp5x, snd_pci_acp6x, snd_pci_ps, snd_rn_pci_acp3x, snd_rpl_pci_acp6x, snd_sof_amd_acp63, snd_sof_amd_acp70, snd_sof_amd_rembrandt, snd_sof_amd_renoir, snd_sof_amd_vangogh | 1 | 1 | 0 | none; modules not in EL: snd_pci_acp3x, snd_pci_acp7x |
| Intel IPU (MIPI cameras) | pci | none | 10 | 0 | 0 | `8086:1919` Xeon E3-1200 v5/E3-1500 v5/6th Gen Core Processor Imaging Unit, `8086:462e`, `8086:465d` Alder Lake Imaging Signal Processor, `8086:4e19` JasperLake IPU, `8086:645d` Core Ultra 200V Series Processors IPU, `8086:7d19` Core Ultra 200H/200V Series Processors IPU and 4 more; modules not in EL: intel_ipu6, intel_ipu7, ipu3_cio2, ipu3_imgu |
| Intel platform devices (LPSS, SMBus, MEI, sensor hub, SPI, thermal, NPU) | pci | dw_dmac_pci (builtin), i2c_i801 (core), idma64 (core), intel_ish_ipc (core), intel_lpss_pci, intel_pmc_core, intel_th_pci (core), intel_vpu (core), intel_vsec (core), mei_gsc (core), mei_me (core), processor_thermal_device_pci (core) | 289 | 239 | 0 | `8086:02a4` 400 Series Chipset Family On-Package SPI (flash) Controller, `8086:06a4` 400 Series Chipset Family SPI (flash) Controller, `8086:0f18` Atom Processor Z36xxx/Z37xxx Series Trusted Execution Engine, `8086:18e0` Atom Processor P5xxx Series SPI Controller, `8086:19e0` Atom Processor C3000 Series SPI Controller, `8086:1bca` C740 Series SPI Controller [Emmitsburg] and 44 more; modules not in EL: mei_txe, spi_intel_pci; built into the upstream kernel, so not compared: dw_dmac_pci, intel_lpss_pci |
| AMD platform devices (PSP, SMBus, sensor hub, NPU) | pci | amd_sfh (core), amd_xgbe, ccp (core), i2c_piix4 (core), k10temp (core), sp5100_tco (core) | 58 | 50 | 2 | `1022:1502` Phoenix/Hawk Point Neural Processing Unit, `1022:1641` Renoir 10GbE Controller Port 0 (XGBE0/1), `1022:1663` VanGogh Data Fabric; Function 3, `1022:17f0` Strix/Krackan/Krackan2/Strix Halo Neural Processing Unit, `1022:17f2`, `1022:17f3` and 2 more; modules not in EL: amdxdna; built into the upstream kernel, so not compared: ccp |
<!-- /gen -->

- **Audio.** Intel laptops since Tiger Lake use SOF: `snd_sof_pci_intel_tgl` / `_mtl` / `_lnl` / `_ptl` are there, and
  `alsa-sof-firmware` 2025.12.2 is in the set. AMD's audio coprocessor is one PCI ID for every generation; the driver
  picks by revision (`snd_pci_acp6x`, `snd_pci_ps`, `snd_sof_amd_acp63`, `snd_sof_amd_acp70` are there). Whether the
  speakers and microphones of a given laptop work depends on its codec and amplifier drivers and the topology file: not
  visible here.
- **Webcams.** USB webcams are `uvcvideo` (by class). The MIPI cameras of recent Intel laptops need IPU6 / IPU7, the
  sensor's driver and userspace (libcamera): EL 9.8 has none of the kernel side, and libcamera is not in the set.
- **Fingerprint.** `fprintd`, `fprintd-pam` and `libfprint` 1.94.6 are in the set. The readers libfprint lists (358 USB
  IDs, from the base's `60-autosuspend-fingerprint-reader.hwdb` in systemd-udev 252, which is taken from libfprint
  [A: an older list than libfprint 1.94.6 itself, so a reader can work and not be in it]) are in `kernel-aliases.tsv`
  as `libfprint:DRIVER`; `silik hw check` names them.
- **Touchpads** are I2C HID devices behind the platform's I2C controller: `i2c_hid_acpi`, `hid_multitouch`,
  `i2c_designware_platform`, `intel_lpss_pci` (IDs through Panther Lake, table above) and `pinctrl_amd` (built in) are there.

### Laptop platform drivers, CPU frequency and hybrid CPUs

<!-- gen:platform -->
| Part | Modules in EL 9.8 x86_64 | In the upstream kernel, not in EL 9.8 x86_64 | Modules in EL 9.8 aarch64 |
|---|---|---|---|
| ThinkPad | thinkpad_acpi, think_lmi | none | none |
| Lenovo IdeaPad / Yoga | ideapad_laptop | lenovo_ymc, lenovo_wmi_gamezone | none |
| Dell | dell_laptop, dell_wmi, dell_smbios, dell_wmi_sysman | dell_pc, alienware_wmi | none |
| HP | hp_wmi, hp_accel | hp_bioscfg | none |
| ASUS | asus_wmi, asus_nb_wmi | asus_armoury | none |
| Acer / MSI / LG / Huawei / Samsung | acer_wmi, msi_wmi | msi_ec, lg_laptop, huawei_wmi, samsung_galaxybook | none |
| Framework (ChromeOS EC) | none | cros_ec_lpcs, cros_charge_control, cros_ec_hwmon, cros_kbd_led_backlight | none |
| System76 / Tuxedo | none | system76_acpi, tuxedo_nb04_wmi_ab | none |
| AMD platform | amd_pmf, amd_pmc, amd_hsmp, amd_sfh, amd_3d_vcache, k10temp | none | none |
| Intel platform | intel_pmc_core, intel_hid, intel_vbtn, intel_ish_ipc, intel_vsec, intel_rapl_msr, intel_lpss_pci | none | none |
| Touchpad, touchscreen (I2C HID) | i2c_hid_acpi, hid_multitouch, i2c_designware_platform, pinctrl_tigerlake, pinctrl_alderlake, pinctrl_meteorlake, pinctrl_meteorpoint | none | i2c_hid_acpi, hid_multitouch, i2c_designware_platform |
| Sensors (rotation, light) | hid_sensor_hub (builtin), hid_sensor_accel_3d, hid_sensor_als | none | hid_sensor_hub |
| USB-C / Thunderbolt | thunderbolt (builtin), typec_ucsi (builtin), ucsi_acpi (builtin), typec_displayport | intel_pmc_mux | thunderbolt (builtin), typec_ucsi (builtin), ucsi_acpi (builtin), typec_displayport |
| Audio: Intel SOF | snd_sof_pci_intel_tgl, snd_sof_pci_intel_mtl, snd_sof_pci_intel_lnl, snd_sof_pci_intel_ptl, snd_soc_avs, snd_hda_intel | none | snd_hda_intel |
| Audio: AMD ACP | snd_pci_acp6x, snd_pci_ps, snd_sof_amd_rembrandt, snd_sof_amd_acp63, snd_sof_amd_acp70, snd_acp_pci | none | none |
| Webcam: USB | uvcvideo | none | uvcvideo |
| Webcam: Intel IPU6 / IPU7 (MIPI) | none | intel_ipu6, intel_ipu6_isys, intel_ipu7, intel_ipu7_isys, ipu_bridge, mei_vsc, ov01a10, ov02c10, ov02e10, ov2740, ov13b10, hi556, ov08x40 | none |
| Bluetooth | btusb, btintel, btrtl, btmtk, btbcm, btintel_pcie, hci_uart | none | btusb, btintel, btrtl, btmtk, btbcm, btintel_pcie, hci_uart |
| NPU | intel_vpu | amdxdna | none |
| SD card readers | rtsx_pci, rtsx_pci_sdmmc, rtsx_usb, sdhci_pci, sdhci_acpi | none | sdhci_pci, sdhci_acpi |
| NVMe / SATA / Intel VMD | nvme, ahci, vmd (builtin) | none | nvme, ahci (builtin) |
| Virtual machines (guest) | virtio_pci (builtin), virtio_net, virtio_blk, virtio_gpu, hv_vmbus, hv_netvsc, hv_storvsc, hyperv_drm, vmwgfx, vmxnet3, xen_netfront | none | virtio_pci (builtin), virtio_net, virtio_blk, virtio_gpu, hv_vmbus, hv_netvsc, hv_storvsc, hyperv_drm, vmwgfx, vmxnet3 |
<!-- /gen -->

<!-- gen:config -->
| Kernel config | What | EL 9.8 x86_64 | EL 9.8 aarch64 | Linux 7.2.11 (Fedora 45) x86_64 |
|---|---|---|---|---|
| `CONFIG_X86_AMD_PSTATE` | AMD P-State (amd-pstate) | y | not set | y |
| `CONFIG_X86_AMD_PSTATE_DEFAULT_MODE` | its default mode (3 = active, EPP) | 3 | not set | 3 |
| `CONFIG_X86_INTEL_PSTATE` | Intel P-State | y | not set | y |
| `CONFIG_INTEL_HFI_THERMAL` | Intel hybrid CPUs: Hardware Feedback Interface (Thread Director) | y | not set | y |
| `CONFIG_SCHED_MC_PRIO` | scheduler: core priorities (ITMT, preferred cores) | y | not set | y |
| `CONFIG_SCHED_CLUSTER` | scheduler: cluster level | y | y | y |
| `CONFIG_ACPI_PLATFORM_PROFILE` | platform profile (performance / balanced / low-power key) | m | not set | y |
| `CONFIG_AMD_PMF` | AMD Platform Management Framework | m | not set | m |
| `CONFIG_INTEL_IDLE` | intel_idle | y | not set | y |
| `CONFIG_USB4` | USB4 / Thunderbolt | y | y | m |
| `CONFIG_DRM_XE` | Intel Xe graphics driver | m | not set | m |
| `CONFIG_DRM_I915` | Intel i915 | m | not set | m |
| `CONFIG_DRM_AMDGPU` | AMD graphics | m | m | m |
| `CONFIG_DRM_NOUVEAU` | nouveau | m | m | m |
| `CONFIG_VIDEO_INTEL_IPU6` | Intel IPU6 camera | not set | not set | m |
| `CONFIG_CROS_EC` | ChromeOS EC (Framework) | not set | not set | m |
| `CONFIG_THINKPAD_ACPI` | ThinkPad ACPI | m | not set | m |
| `CONFIG_HYPERV` | Hyper-V guest | m | m | y |
| `CONFIG_ACPI` | ACPI | y | y | y |
| `CONFIG_ARM64_4K_PAGES` | ARM: 4K pages | not set | y | not set |
| `CONFIG_ARCH_QCOM` | ARM: Qualcomm platforms | not set | y | not set |
| `CONFIG_ARCH_BCM2835` | ARM: Raspberry Pi (BCM2835 family) | not set | not set | not set |
| `CONFIG_ARCH_APPLE` | ARM: Apple silicon | not set | not set | not set |
| `CONFIG_ARCH_TEGRA` | ARM: NVIDIA Tegra / Jetson | not set | y | not set |
| `CONFIG_ARCH_ROCKCHIP` | ARM: Rockchip | not set | not set | not set |
| `CONFIG_ARCH_MXC` | ARM: NXP i.MX | not set | y | not set |
| `CONFIG_ARCH_HISI` | ARM: HiSilicon | not set | y | not set |
| `CONFIG_ARCH_THUNDER2` | ARM: Marvell ThunderX2 | not set | y | not set |
| `CONFIG_ARCH_XGENE` | ARM: Ampere / APM X-Gene | not set | y | not set |
| `CONFIG_ARM_SMMU_V3` | ARM: SMMUv3 | not set | y | not set |
| `CONFIG_ARM_GIC_V3` | ARM: GICv3 | not set | y | not set |
| `CONFIG_ENA_ETHERNET` | Amazon ENA network (Graviton instances) | m | m | m |
| `CONFIG_PCI_HOST_GENERIC` | generic ECAM PCI host (virtual machines) | not set | y | not set |
| `CONFIG_DRM_VIRTIO_GPU` | virtio-gpu | m | m | m |
| `CONFIG_SYSFB_SIMPLEFB` | simple framebuffer (UEFI GOP) | not set | y | y |
<!-- /gen -->

- AMD: `amd-pstate` is built in and its default mode is 3 (active, EPP), as in the upstream kernel. Intel hybrid CPUs:
  `intel_pstate`, the Hardware Feedback Interface (Thread Director) and core priorities (ITMT) are built in.
- No `CONFIG_CROS_EC`: on a Framework laptop the EC's charge limit, fan and sensor readings have no driver.
- On aarch64 none of the x86 laptop drivers exist (they are x86 firmware interfaces).

### The bench: CAN, USB serial, test equipment

<!-- gen:can -->
| Module | EL 9.8 x86_64: package | EL 9.8 aarch64 | USB / PCI IDs in EL | IDs in Linux 7.2.11 (Fedora 45) |
|---|---|---|---|---|
| can | kernel-modules | yes | - | yes |
| can_raw | kernel-modules | yes | - | yes |
| can_bcm | kernel-modules | yes | - | yes |
| can_gw | kernel-modules | yes | - | yes |
| can_isotp | kernel-modules | yes | - | yes |
| can_j1939 | kernel-modules | yes | - | yes |
| can_dev | kernel-modules | yes | - | yes |
| vcan | **kernel-modules-extra** | yes | - | yes |
| vxcan | kernel-modules | yes | - | yes |
| slcan | **kernel-modules-extra** | yes | - | yes |
| gs_usb | kernel-modules | yes | 6 | 6 |
| peak_usb | kernel-modules | yes | 6 | 6 |
| kvaser_usb | kernel-modules | yes | 51 | 54 |
| ems_usb | **kernel-modules-extra** | yes | 1 | 1 |
| usb_8dev | kernel-modules | yes | 1 | 1 |
| esd_usb | **not in EL 9.8** | no | - | 3 |
| mcba_usb | **not in EL 9.8** | no | - | 1 |
| f81604 | **not in EL 9.8** | no | - | 1 |
| peak_pciefd | kernel-modules | yes | 6 | 6 |
| m_can_pci | kernel-modules | yes | 2 | 2 |
| mcp251x | kernel-modules | yes | - | yes |
| mcp251xfd | kernel-modules | yes | - | yes |
| ctucanfd_pci | **not in EL 9.8** | no | - | 1 |
<!-- /gen -->

<!-- gen:bench-cov -->
| Family | Bus | Modules in EL 9.8 x86_64 (package) | IDs upstream claims | of them in EL 9.8 x86_64 | in EL 9.8 aarch64 | Upstream IDs EL 9.8 does not claim |
|---|---|---|---|---|---|---|
| CAN: USB adapters | usb | ems_usb (extra), gs_usb, kvaser_usb, peak_usb, usb_8dev | 73 | 65 | 65 | `04d8:0a30`, `0ab4:0010`, `0ab4:0011`, `0ab4:0014`, `0bfd:0119`, `0bfd:011a` and 2 more; modules not in EL: esd_usb, f81604, mcba_usb |
| CAN: PCI / PCIe cards | pci | m_can_pci, peak_pciefd | 9 | 8 | 8 | `1760:ff00` CTU CAN FD PCIe Card; modules not in EL: ctucanfd_pci |
| USB serial adapters | usb | ark3116, belkin_sa, cdc_acm (core), ch341, cp210x, cypress_m8, digi_acceleport, f81534, ftdi_sio, io_edgeport, io_ti, ir_usb, iuu_phoenix, keyspan, mct_u232, mos7720, mos7840, mxuport, opticon, option, oti6858, pl2303, qcserial, quatech2, spcp8x5, ssu100, ti_usb_3410_5052, upd78f0730, whiteheat, xr_serial | 3147 | 3056 | 3082 | `03f0:0121` HP 39g+ [F2224A], 39gs [F2223A], 40gs [F2225A], 48gII [F2226A], 49g+ [F2228A], 50g [F2229A, NW240AA], `0403:bd90` PICAXE Download Cable [AXE027], `0403:e510`, `0421:069a` 130 [RM-1035] (Charging only), `0489:e123`, `04b7:4d22` and 85 more; modules not in EL: f81232, usb_serial_simple |
| USB test equipment and bridges (USBTMC, GPIB, I2C / SPI bridges) | usb | i2c_diolan_u2c (core), i2c_tiny_usb (core), usbtmc (core) | 19 | 5 | 5 | `06cb:0701`, `0957:0107` 82357A GPIB Interface, `0957:0718` 82357B GPIB Interface, `10c4:eac1` CP2615 I2S Audio Bridge, `1a86:5512` CH341 in EPP/MEM/I2C mode, EPP/I2C adapter, `2ac1:20c1` and 8 more; modules not in EL: agilent_82357a, dln2, i2c_cp2615, ni_usb_gpib, spi_ch341, usbio |
<!-- /gen -->

- **Vector**: no Linux kernel driver exists for the VN16xx family in either kernel; `silik win vm usb attach` gives it
  to Windows in the VM (`hardware.tsv`, kind `vm`).
- **PEAK PCAN-USB FD** (`0c72:0012`) and the rest of `peak_usb`'s six IDs, all six `gs_usb` IDs (candleLight, CANable
  with that firmware), 51 of the 54 Kvaser USB IDs: claimed. The three Kvaser ones missing are `0bfd:0119`, `011a`, `011b`.
- **`hardware.tsv` reconciled**: its "el9" field was compared with the alias table for all its rows with a kernel
  driver: none was wrong. Six rows were added (EMS CPC-USB/ARM7: yes, in kernel-modules-extra; esd CAN-USB/2, /3-FD,
  /Micro, Microchip CAN BUS Analyzer, Fintek F81604: no driver in EL 9.8). `tests/test_hw.py` now holds that field to
  the table (a wrong `yes` or `no` fails the tests).
- Debug probes and logic analysers are opened by programs through libusb (OpenOCD, st-link, sigrok): no kernel driver
  is involved; `silik doctor bench` checks that the device is the user's.

## 3. What needs a command

| For | Command | What it does |
|---|---|---|
| Knowing, on this machine | `silik hw check` | every PCI and USB device with the driver bound, or the driver that claims it and is not bound, or "no driver in this kernel" and what to do. Reads only |
| Knowing, before installing | `silik hw check --from FILE` | the same for a list saved on another system (section 7) |
| The whole workstation | `silik doctor` | has a `hardware` area: a row for each device without a driver, and for `kernel-modules-extra` |
| NVIDIA's driver | `silik hw nvidia install` | NVIDIA's repository, the module built on the machine (DKMS); `--source almalinux`: AlmaLinux's prebuilt open modules (section 5) |
| A driver the base lacks | `silik hw driver add wl` / `r8127` / `rtw88_usb` / `rtw89_usb` | a kmod package of ELRepo, a third party (section 6); `silik hw driver` lists them |
| vcan, slcan, EMS CPC-USB on a system installed without the ISO | `sudo dnf install kernel-modules-extra-$(uname -r)` | the base's own package (`silik doctor hardware` prints this line when it applies) |
| A fingerprint | Settings, Users (fprintd) | enrols it, when libfprint knows the reader |

## 4. What does not work on this base

No driver in EL 9.8's kernel and no maintained kmod found: the Intel MIPI cameras (IPU6 / IPU7), MediaTek MT7927 and
MT7902, the AMD NPU, the Framework EC, the CAN adapters of row 11 above, the newest AMD graphics cores, the Mellanox
ConnectX-9 / -10 (`15b3:1025`, `1027`), and everything on ARM that is not an ACPI server or a virtual machine. The full
list of IDs the upstream kernel claims and EL 9.8 does not, by family (old hardware included):

<!-- gen:gaps -->
| Area | Family | IDs without a driver | Which (names from pci.ids / usb.ids) | What to do |
|---|---|---|---|---|
| wifi | Intel Wi-Fi (iwlwifi) | 4 | PRO/Wireless 3945ABG [Golan] Network Connection; PRO/Wireless 3945ABG [Golan] Network Connection; PRO/Wireless 4965 AG or AGN [Kedron] Network Connection; PRO/Wireless 4965 AG or AGN [Kedron] Network Connection | no driver in EL 9's kernel: a cable, or a USB Wi-Fi adapter it drives |
| wifi | Realtek 802.11ac (rtw88) | 1 | RTL8813AE 802.11ac PCIe Wireless Network Adapter | no driver in EL 9's kernel: a cable, or a USB Wi-Fi adapter it drives |
| wifi | Realtek Wi-Fi 6 / 7 (rtw89) | 4 | RTL8922AE 802.11be PCIe Wireless Network Adapter; RTL8852BE-VT PCIe 802.11ax Wireless Network Controller; RTL8851BE PCIe 802.11ax Wireless Network Controller | silik hw driver add rtw89_usb |
| wifi | Realtek 802.11n / older ac (rtlwifi) | 10 | RTL8180L 802.11b MAC; RTL-8185 IEEE 802.11a/b/g Wireless LAN Controller; RTL8187SE Wireless LAN Controller; DWL-510 / DWL-610 802.11b [Realtek RTL8180L]; F5D6001 Wireless PCI Card [Realtek RTL8180] ... | no driver in EL 9's kernel: a cable, or a USB Wi-Fi adapter it drives |
| wifi | MediaTek (mt76) | 18 | MT7603E 802.11bgn PCI Express Wireless Network Adapter; MT7615E 802.11ac PCI Express Wireless Network Adapter; MT7663 802.11ac PCI Express Wireless Network Adapter; MT7902 802.11ax PCIe Wireless Network Adapter [Filogic 310]; MT7916A/MT7916D normal link PCIe Wi-Fi 6(802.11ax) 160MHz 2x2 Wireless Network Adapter [Filogic 630] ... | no driver in EL 9's kernel: a cable, or a USB Wi-Fi adapter it drives |
| wifi | Qualcomm Atheros (ath) | 25 | AR5212 802.11abg NIC (3CRDAG675); AR5210 Wireless Network Adapter [AR5000 802.11a]; AR5211 Wireless Network Adapter [AR5001A 802.11a]; AR5211 Wireless Network Adapter [AR5001X 802.11ab]; AR5212/5213/2414 Wireless Network Adapter ... | no driver in EL 9's kernel: a cable, or a USB Wi-Fi adapter it drives |
| wifi | Broadcom | 21 | Broadcom BCM4318 [AirForce One 54g] 802.11g WLAN Controller; BCM4301 802.11b Wireless LAN Controller; BCM4306 802.11bg Wireless LAN controller; BCM4306 802.11bg Wireless LAN Controller; BCM4311 802.11b/g WLAN ... | silik hw driver add wl |
| wifi | USB Wi-Fi adapters | 473 | GW-US54ZGL 802.11bg; NW-3100 802.11b/g 54Mbps Wireless Network Adapter [zd1211]; Aterm PA-WL54GU; Aterm WL300NU-G; Aterm WL300NU-AG ... | silik hw driver add rtw88_usb / rtw89_usb for the Realtek ones; else no driver in EL 9's kernel |
| bluetooth | Bluetooth (btusb: by class, and these IDs by name) | 1 | `0471:0215` | no driver in EL 9's kernel |
| ethernet | Realtek | 2 | RTL8127 10GbE Controller | silik hw driver add r8127 |
| ethernet | Broadcom | 3 | BCM4401-B0 100Base-TX; BCM4401 100Base-T; BCM4402 Integrated 10/100BaseT | no driver in EL 9's kernel |
| ethernet | NVIDIA Mellanox | 3 | CX9 Family [ConnectX-9]; CX10 Family [ConnectX-10]; CX10 Family [ConnectX-10 NVLink-C2C] | no driver in EL 9's kernel |
| ethernet | Other server cards (Chelsio, Marvell / QLogic, Solarflare, Pensando, Netronome, Emulex, Cisco, Huawei, Amazon, Microsoft, Google) | 232 | DECchip 21140 [FasterNet]; DECchip 21142/43; 21x4x DEC-Tulip compatible 10/100 Ethernet; 21x4x DEC-Tulip compatible 10/100 Ethernet; 3c982-TXM 10/100baseTX Dual Port A [Hydra] ... | no driver in EL 9's kernel |
| ethernet | USB Ethernet adapters and docks | 22 | iPhone 5/5C/5S/6/SE/7/8/X/XR; iPad; Intex Aqua Fish & Jolla C Diagnostic Mode | no driver in EL 9's kernel |
| gpu | Intel (i915, xe) | 47 | Atom Processor D2xxx/N2xxx Integrated Graphics Controller; Atom Processor D2xxx/N2xxx Integrated Graphics Controller; Atom Processor D2xxx/N2xxx Integrated Graphics Controller; Atom Processor D2xxx/N2xxx Integrated Graphics Controller; Atom Processor D2xxx/N2xxx Integrated Graphics Controller ... | no driver in EL 9's kernel |
| gpu | Server and virtual (ast, mgag200, virtio, vmware, qxl, bochs, hyperv) | 1 | VirtualBox Graphics Adapter | no driver in EL 9's kernel |
| storage | NVMe, AHCI, VMD | 6 | 4100AT NVMe SSD (DRAM-less); PBlaze5 510/516; NVMe SSD Controller IG5216 [Shasta+] (DRAM-less); OM3SGP4 PCIe 4 NVMe SSD (TLC) | no driver in EL 9's kernel |
| storage | RAID and SAS controllers | 97 | LPE41100/LPE42100 Series 64G/128G Fibre Channel Adapter; RocketRAID 2640 SAS/SATA Controller; RocketRAID 2720 PCIe Gen2 6Gb/s SAS/SATA Controller; RocketRAID 2722; RocketRAID 2740 ... | no driver in EL 9's kernel |
| storage | Card readers and SD hosts | 8 | SD TypA Controller; AU6601 PCI-E Flash card reader controller; AU6621 PCI-E Flash card reader controller; AU6625 PCI-E Flash card reader controller | no driver in EL 9's kernel |
| audio | Intel audio (HDA, SOF, AVS) | 2 | `8086:6e50`, `8086:d328` | no driver in EL 9's kernel |
| camera | Intel IPU (MIPI cameras) | 10 | Xeon E3-1200 v5/E3-1500 v5/6th Gen Core Processor Imaging Unit; Alder Lake Imaging Signal Processor; JasperLake IPU; Core Ultra 200V Series Processors IPU; Core Ultra 200H/200V Series Processors IPU ... | no driver in EL 9's kernel: a USB webcam (uvcvideo) |
| platform | Intel platform devices (LPSS, SMBus, MEI, sensor hub, SPI, thermal, NPU) | 50 | 400 Series Chipset Family On-Package SPI (flash) Controller; 400 Series Chipset Family SPI (flash) Controller; Atom Processor Z36xxx/Z37xxx Series Trusted Execution Engine; Atom Processor P5xxx Series SPI Controller; Atom Processor C3000 Series SPI Controller ... | no driver in EL 9's kernel |
| platform | AMD platform devices (PSP, SMBus, sensor hub, NPU) | 8 | Phoenix/Hawk Point Neural Processing Unit; Renoir 10GbE Controller Port 0 (XGBE0/1); VanGogh Data Fabric; Function 3; Strix/Krackan/Krackan2/Strix Halo Neural Processing Unit | no driver in EL 9's kernel |
| bench | CAN: USB adapters | 8 | `04d8:0a30`, `0ab4:0010`, `0ab4:0011`, `0ab4:0014`, `0bfd:0119` | no driver in EL 9's kernel: another adapter (gs_usb / candleLight, PEAK, Kvaser), or Windows in the VM: silik win vm usb attach VID:PID |
| bench | CAN: PCI / PCIe cards | 1 | CTU CAN FD PCIe Card | no driver in EL 9's kernel: a USB adapter it drives |
| bench | USB serial adapters | 91 | HP 39g+ [F2224A], 39gs [F2223A], 40gs [F2225A], 48gII [F2226A], 49g+ [F2228A], 50g [F2229A, NW240AA]; PICAXE Download Cable [AXE027]; 130 [RM-1035] (Charging only); CDMA Wireless Modem/Phone; GPS/GNSS/SPAN sensor ... | no driver in EL 9's kernel |
| bench | USB test equipment and bridges (USBTMC, GPIB, I2C / SPI bridges) | 14 | 82357A GPIB Interface; 82357B GPIB Interface; CP2615 I2S Audio Bridge; CH341 in EPP/MEM/I2C mode, EPP/I2C adapter; GPIB-USB-B ... | no driver in EL 9's kernel |
<!-- /gen -->

## 5. NVIDIA: the two ways, compared

| | Today: `silik hw nvidia install` | AlmaLinux's own: `silik hw nvidia install --source almalinux` |
|---|---|---|
| Repository | NVIDIA's (`cuda-rhel9.repo` on developer.download.nvidia.com) | `almalinux-release-nvidia-driver` 9-5.el9, in AlmaLinux's own `extras` repository; its repo file points to `nvidia.repo.almalinux.org/cuda/9/$basearch` (AlmaLinux's builds together with NVIDIA's packages), requires `epel-release` and enables CRB |
| Kernel module | built on the machine by DKMS for each kernel (`dnf module install nvidia-driver:latest-dkms`): needs `kernel-devel`, a compiler, and a rebuild at every kernel update | `kmod-nvidia-open` 620.70.06-3.el9, built by AlmaLinux (build host x64-builder03.almalinux.org, 09/11/2026) for kernel 5.14.0-687.66.1.el9_8; `weak-modules` links it into later kernels of the same kernel interface. No compiler, no DKMS |
| Which module | NVIDIA's closed module | NVIDIA's open modules (<https://github.com/NVIDIA/open-gpu-kernel-modules>: "can be used on any Turing or later GPU"): GeForce GTX 16xx / RTX 20xx and newer. Older cards (GTX 9xx, 10xx) are not driven by it |
| Driver version | in AlmaLinux's copy of the repository, the `latest-dkms` stream's newest driver is 610.57.04; the 615 and 620 branches exist only as `-open` streams (its `modules.yaml`, read 13/11/2026) | 620.70.06 |
| **Secure Boot** | DKMS signs the module with a key made on that machine: the person must enrol it (`mokutil --import /var/lib/dkms/mok.pub`, a password, the blue MOK screen at the next start). Until then the module does not load | the modules are signed by "AlmaLinux NVIDIA Module CA" (`modinfo` of the package's `nvidia.ko`), and the kernel image 5.14.0-687.66.2.el9_8 contains certificates named "AlmaLinux NVIDIA Module CA" and "AlmaLinux NVIDIA Module Signing" (strings of the decompressed `vmlinuz`): **nothing to enrol** [A: not booted; the names match, the key ids were not compared] |
| ARM | not set up by `silik` (x86_64 repository) | `kmod-nvidia-open` exists for aarch64 too |
| After a kernel update | DKMS rebuilds, if `kernel-devel` of the new kernel is there (`silik doctor graphics` has a row for a kernel without the module) | works at once if the kernel interface is unchanged; else no NVIDIA module until AlmaLinux's rebuild (this time: kernel built 05/11, kmod 09/11) |

Read: AlmaLinux's wiki page <https://wiki.almalinux.org/documentation/nvidia.html> (its source,
<https://github.com/AlmaLinux/wiki/blob/master/docs/documentation/nvidia.md>: "These packages are based on the NVIDIA
open source drivers and are secureboot-signed. The drivers are built using kernel kmods meaning upon
installation/update there are no DKMS compilations required"; `sudo dnf install almalinux-release-nvidia-driver`, then
`sudo dnf install nvidia-open-kmod nvidia-driver`; `nvidia-smi` is in `nvidia-driver-cuda`), the packages themselves
(<https://repo.almalinux.org/almalinux-nvidia/cuda/9/x86_64/Packages/>, the copy on repo.almalinux.org of the
repository), and the kernel package. Not read: NVIDIA's own repository (developer.download.nvidia.com was not reachable
from the build machine), so that it equals AlmaLinux's copy is [A].

**Proposal** [PROPOSAL, the owner decides]: make AlmaLinux's packages the default for Turing and newer cards (the
RTX 3050 of the first target is one), and keep NVIDIA's DKMS driver for older cards. The gain is no compiler on the
machine and no key to enrol with Secure Boot. The cost is the days between a kernel update and its kmod when the kernel
interface changes: `silik update` should then hold the kernel back (item 2 of `docs/ESTRATEGIA.md`). **Not switched**:
neither way was run on a machine with an NVIDIA card. `--source almalinux` is there to try it on the Ryzen laptop.

## 6. Drivers the base lacks: ELRepo's kmod packages

A kmod package adds a module beside the base's kernel; the kernel itself stays the base's. ELRepo's `kernel-ml` and
`kernel-lt` replace the kernel: **not used, never offered** (the vendors' EDA tools are certified against EL 9's kernel).

ELRepo's packaging repository (<https://github.com/elrepo/packages>, commit d53baecf of 28/10/2026) has an `el9` recipe
for 111 packages. For the gaps of this page:

| Gap | ELRepo package | Its recipe says | Offered as |
|---|---|---|---|
| Realtek RTL8922AE, RTL8851BE, RTL8852BE-VT (PCIe); RTL8851BU, RTL8852BU (USB) | `kmod-rtw89_usb` | modules `rtw89_8851be`, `rtw89_8852bte`, `rtw89_8922ae`, `rtw89_8851bu`, `rtw89_8852bu`; rebuilt 16/10/2026 against 5.14.0-687.58.1.el9_8 | `silik hw driver add rtw89_usb` |
| USB Wi-Fi with RTL8723DU, RTL8812AU, RTL8814AU, RTL8821AU, RTL8821CU, RTL8822CU | `kmod-rtw88_usb` | those modules; rebuilt 16/10/2026 against 687.58.1.el9_8 | `silik hw driver add rtw88_usb` |
| Realtek RTL8127 10G | `kmod-r8127` | Realtek's driver 11.016.00, built against 687.5.3.el9_8 (20/05/2026) | `silik hw driver add r8127` |
| Broadcom BCM43xx (bcma cards) | `kmod-wl` | Broadcom's hybrid driver 6.30.223.271 ("Redistributable, no modification permitted"), rebuilt 16/10/2026; it blacklists `b43`, `bcma`, `brcmfmac`, `brcmsmac` | `silik hw driver add wl` |
| NVIDIA | `kmod-nvidia` 595.112.07, `kmod-nvidia-580xx`, `-470xx` | built against 687.12.1.el9_8 (10/2026) | not offered: section 5 has two better sources |
| MediaTek MT7927 / MT7902, IPU6 / IPU7, AMD NPU, Framework EC, esd / Microchip / Fintek CAN | none (`mt7921e-kmod`'s el9 recipe is of 2022, for EL 9.0) | | nothing |

- `silik hw driver add NAME` prints what the package is and that it comes from ELRepo, a third party, before it runs
  anything, then: `sudo dnf -y install elrepo-release` (ELRepo's repository file and keys; the package is in AlmaLinux's
  own `extras` repository) and `sudo dnf -y install kmod-NAME`. `--dry-run` prints the two lines.
- **Secure Boot**: the recipes sign the modules with ELRepo's key, and `elrepo-release` installs its certificate as
  `/etc/pki/elrepo/SECURE-BOOT-KEY-elrepo.org.der`; the kernel does not trust it until the person enrols it
  (`sudo mokutil --import ...`, said by the command) [A: elrepo.org's own page on this was not reachable; the path is
  the package's].
- All four recipes are `ExclusiveArch: x86_64`: `silik hw driver add` refuses on aarch64.
- What was not checked: that the built packages are in ELRepo's repository today (elrepo.org and its mirrors were not
  reachable from the build machine; the recipes and their change logs were), and that any of them drives a device.
  **Not run.**

## ARM (aarch64)

The same kernel version, built for aarch64. **Which of the families above it lacks** (modules EL 9.8 has on x86_64
and not on aarch64):

<!-- gen:arm -->
| Area | Family | Modules EL 9.8 has on x86_64 and not on aarch64 |
|---|---|---|
| ethernet | Marvell Aquantia (atlantic) | atlantic |
| ethernet | Other server cards (Chelsio, Marvell / QLogic, Solarflare, Pensando, Netronome, Emulex, Cisco, Huawei, Amazon, Microsoft, Google) | be2net, enic, sfc, sfc_siena |
| gpu | Intel (i915, xe) | i915, xe |
| storage | NVMe, AHCI, VMD | vmd |
| storage | RAID and SAS controllers | aacraid |
| storage | Card readers and SD hosts | rtsx_pci, tifm_7xx1 |
| audio | Intel audio (HDA, SOF, AVS) | snd_soc_avs, snd_soc_skl, snd_sof_pci_intel_apl, snd_sof_pci_intel_cnl, snd_sof_pci_intel_icl, snd_sof_pci_intel_lnl, snd_sof_pci_intel_mtl, snd_sof_pci_intel_ptl, snd_sof_pci_intel_tgl, snd_sof_pci_intel_tng |
| audio | AMD audio coprocessor | snd_acp_legacy_mach, snd_acp_pci, snd_pci_acp5x, snd_pci_acp6x, snd_pci_ps, snd_rn_pci_acp3x, snd_rpl_pci_acp6x, snd_sof_amd_acp63, snd_sof_amd_acp70, snd_sof_amd_rembrandt, snd_sof_amd_renoir, snd_sof_amd_vangogh |
| platform | Intel platform devices (LPSS, SMBus, MEI, sensor hub, SPI, thermal, NPU) | i2c_i801, idma64, intel_ish_ipc, intel_lpss_pci, intel_pmc_core, intel_th_pci, intel_vpu, intel_vsec, mei_gsc, mei_me, processor_thermal_device_pci |
| platform | AMD platform devices (PSP, SMBus, sensor hub, NPU) | amd_sfh, i2c_piix4, k10temp, sp5100_tco |
<!-- /gen -->

In words: no Intel graphics (`i915`, `xe`: an Arc card in an ARM machine has no driver), no Aquantia `atlantic`, no
Realtek PCIe card readers, none of the x86 platform and laptop drivers, no SOF or AMD audio; `amdgpu`, `nouveau`,
`iwlwifi`, the Realtek / MediaTek / Qualcomm Wi-Fi drivers, `r8169`, `igc`, `e1000e`, the Intel and Mellanox server
cards, NVMe, AHCI, xHCI, Thunderbolt, `btusb`, `uvcvideo` and all the CAN and USB serial drivers are there. PCI and USB
alias counts are in the first table of section 1. `silik hw check --from FILE --arch aarch64` answers for a device list.

**Which ARM machines this kernel boots at all.** From its own config and files (aarch64 `kernel-core`):

- ACPI is on, with the server model (`CONFIG_ACPI=y`, `CONFIG_ACPI_CCA_REQUIRED=y`, `CONFIG_ARM_SMMU_V3=y`,
  `CONFIG_ARM_GIC_V3=y`), UEFI boot (`CONFIG_EFI=y`), 4K pages (`CONFIG_ARM64_4K_PAGES=y`).
- Platform support compiled in: `ARCH_HISI`, `ARCH_MXC` (NXP), `ARCH_QCOM`, `ARCH_SEATTLE` (AMD), `ARCH_TEGRA` (NVIDIA
  Jetson: `ARCH_TEGRA_194_SOC`, `ARCH_TEGRA_234_SOC`), `ARCH_THUNDER`, `ARCH_THUNDER2` (Marvell / Cavium), `ARCH_XGENE`
  (APM / Ampere), `ARCH_VEXPRESS`, `ARCH_BCM_IPROC`; Ampere errata workarounds are in. **Not set:** `ARCH_BCM2835`
  (Raspberry Pi), `ARCH_APPLE`, `ARCH_ROCKCHIP`.
- It ships 394 device trees (qcom 182, freescale 142, arm 20, hisilicon 14, nvidia 10, amd 8, ...): none for a Snapdragon X
  laptop (`x1e*`, `x1p*`), the Snapdragon 8cx Gen 3 (`sc8280xp*`), a Raspberry Pi (`bcm2711*`, `bcm2712*`) or an Apple machine.
- Virtual machines: `virtio_pci` built in, `virtio_net`, `virtio_blk`, `virtio_gpu`, the generic ECAM PCI host, the
  Hyper-V guest drivers (`hv_vmbus`, `hv_netvsc`, `hv_storvsc`, `hyperv_drm`, `pci_hyperv`), VMware's, Amazon's `ena`.

| Machine | EL 9.8's aarch64 kernel | Source |
|---|---|---|
| ACPI / SBSA servers and workstations (Ampere Altra and AmpereOne, and the systems of Red Hat's hardware catalog) | the intended target: UEFI + ACPI | Red Hat lists the 64-bit ARM architecture as supported (<https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/interactively_installing_rhel_from_installation_media/system-requirements-and-supported-architectures_rhel-installer>) and certifies systems in <https://catalog.redhat.com/en/hardware>; the kernel's ACPI model on ARM: <https://docs.kernel.org/arch/arm64/arm-acpi.html>. [A: which Ampere models are certified was not read; the catalog was not reachable] |
| Cloud instances (AWS Graviton, Azure, Google) | the drivers are there (`ena`, `gve`, `mana`, NVMe, virtio) | module lists above; AlmaLinux publishes aarch64 cloud images (<https://repo.almalinux.org/almalinux/9/cloud/>) [A: not started here] |
| KVM / QEMU `virt` machines with UEFI (also UTM and Parallels on Apple silicon) | virtio drivers, 4K pages (Apple's CPUs have no 64K pages) | Red Hat's solution 6545411, "Can I run RHEL virtualized in a Mac using the Apple M1 processor?" (<https://access.redhat.com/solutions/6545411>): RHEL 9 for aarch64 works there, RHEL 7 and 8 do not [from the search engine's extract of that page; the page was not reachable]. Our aarch64 ISO was started in `qemu-system-aarch64` under emulation (`docs/STATUS.md`) |
| Hyper-V on Windows 11 for ARM (a Snapdragon X laptop's own Windows) | the Hyper-V guest drivers are in the aarch64 kernel | a Red Hat knowledge base thread reports the RHEL 8 / 9 ARM installer running, slowly, on a Surface Pro 11 under Hyper-V (<https://access.redhat.com/node/7078765>) [search extract]; no Red Hat support statement for it was found. **Not tried here** |
| Snapdragon X laptops on bare metal | **no**: no device tree for them, and no `DRM_MSM`, `PHY_QCOM_QMP`, `PHY_QCOM_EDP`, `QCOM_PDC`, `PCIE_QCOM` in the config (display, USB, PCIe have no drivers) | the aarch64 config and file list read here |
| Raspberry Pi 3 / 4 / 5 | **not with this kernel** (`ARCH_BCM2835` not set). AlmaLinux's own Pi image uses another kernel: `raspberrypi2-kernel4` 6.6.74 in its `raspberrypi` repository | <https://repo.almalinux.org/almalinux/9/raspberrypi/aarch64/os/Packages/>, <https://github.com/AlmaLinux/raspberry-pi>, <https://wiki.almalinux.org/documentation/raspberry-pi>. SilikOS's packages are noarch and would install there; **not tried**, and a kernel other than the base's is outside what the EDA vendors support |
| Apple silicon on bare metal | **no** (`ARCH_APPLE` not set, no device tree) | the config read here |
| NVIDIA Jetson (Tegra 194 / 234) | platform support is compiled in, with 10 NVIDIA device trees [A: nothing more was read; not tried] | the config and file list |

## 7. Will my computer work? `silik hw check`

```
silik hw check                       this machine: every PCI and USB device, the driver bound to it or what is missing
silik hw check --all                 also the devices that often have no driver (bridges, memory controllers)
silik hw check --from FILE           a list saved on another system (before installing)
silik hw check --from FILE --arch aarch64     ...for an ARM machine
silik hw check --json                the same as data
```

On this machine it reads `/sys` (the driver bound to each device) and the running kernel's own
`/lib/modules/$(uname -r)/modules.alias`; when a device has no driver it says whether a package of the base has one
(`kernel-modules-extra`), whether a newer kernel does, and what to do. It runs nothing but `lspci` for the names, and
changes nothing. Exit code 0 when every device that needs a driver has one, 1 otherwise.

**The list to bring from another system:**

| System | Command | Notes |
|---|---|---|
| Any Linux (a live USB stick will do) | `lspci -nn > list.txt; lsusb >> list.txt` | `lspci -nnk` adds the subsystem IDs, which a few drivers match on; `lsusb -v` adds the classes, by which webcams, Bluetooth, storage and audio are matched |
| Windows 10 / 11, PowerShell | `(Get-PnpDevice -PresentOnly).HardwareID \| Out-File list.txt` | lines like `PCI\VEN_8086&DEV_A0F0&SUBSYS_00748086&REV_20`, `PCI\VEN_8086&DEV_A0F0&CC_028000`, `USB\VID_0C72&PID_000C`: the forms Microsoft documents (<https://learn.microsoft.com/en-us/windows-hardware/drivers/install/identifiers-for-pci-devices>, <https://learn.microsoft.com/en-us/windows-hardware/drivers/install/standard-usb-identifiers>); the file is UTF-16, which is read. [A: the command was not run on a Windows machine here; the parser was tested on lines written after that documentation] |

The answer for each device is one of: `driver` (a driver of EL 9.8's kernel claims the ID), `maybe` (it claims the ID
for some subsystem IDs or interfaces the list does not give), `none` (no driver; what to do), `partial` (only the
card's bus has a driver), `program` (no kernel driver needed: OpenOCD, sigrok, libfprint), `quiet` (no driver, in a
class that often has none: bridges, memory controllers), `unknown` (a USB device no driver names, in a list without
classes). On this machine also `ok` (a driver is bound) and `unbound` (claimed, not bound). The last line of the
output is always: *a match says a driver of the kernel claims the device's ID, not that the device was tried*.

Tried on public probes of real laptops (the Linux Hardware Database, <https://github.com/linuxhw/LsPCI> and
<https://github.com/linuxhw/LsUSB>, CC BY 4.0; cut-down copies in `tests/hw/`): for a ThinkPad X1 Carbon Gen 12 (Core
Ultra, 2024) it lists 27 devices, 23 claimed, 2 without a driver (the IPU6 camera and the SPI flash controller), 2 quiet;
for a ThinkPad T14s Gen 4 (Ryzen 7040) 40 devices, 22 claimed, none without, and the AMD NPU shown as a device a newer
kernel drives. Those are statements about ID tables, not about those laptops.

## 8. How to make the tables again

```
bash tools/fetch_hw_facts.sh build/hwfacts        # needs docker or podman and the network; several minutes, about 11 MB kept
python3 tools/gen_hwdb.py --facts build/hwfacts   # kernel-aliases.tsv, pci.tsv, the tables of this page
python3 tools/gen_hwdb.py --check                 # the committed files agree with each other (also a unit test)
```

To be done again at each new minor release of the base (9.9: new IDs arrive with it), and whenever
`tools/hwdb/families.tsv` (the families and named devices, written by hand) changes.

Not reachable from the build machine, so not read (their content is cited above only through what is said next to
each): git.kernel.org (read through github.com/torvalds/linux), vault.almalinux.org (AlmaLinux's kernel source
package), elrepo.org and its mirrors (ELRepo's built packages), wiki.almalinux.org (read through its source on
GitHub), developer.download.nvidia.com, docs.redhat.com and access.redhat.com (search-engine extracts only),
learn.microsoft.com.
