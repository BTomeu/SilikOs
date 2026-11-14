# SilikOS for industry: vendors' tools and identical laboratories (13/11/2026)

**Nothing on this page has been tried with any vendor's real installer.** No vendor's program has been downloaded,
run or stored. What is here is what the public requirements pages say, and how each one was read:

- **read on the vendor's page**: the vendor's own text was opened (the source of its documentation or its
  repository). Only 7 of 39.
- **a search engine's extract [A]**: the vendor's website could not be reached from the work machine (its host is
  not allowed there); what is said comes from the extract the search engine gives of the official page. It has to be
  confirmed on the page (the URL is in `silik vendor list`).
- **not confirmed [A]**: nothing was found.

Assumptions are marked [A]. The package names are checked (see "What was run").

## What there is

```
silik vendor list [--json]              the tools: what the vendor says of EL 9, for which version, how, when and where it was read
silik vendor check TOOL... [--json]     this system against the published requirements: ok / warn / bad / unknown / info,
silik vendor check --all --json           and on each row that is not ok, the command that fixes it
silik vendor prepare TOOL...            runs those commands (each printed; --dry-run runs nothing) and says what is left to do by hand
silik vendor lib libtinfo.so.5          which EL 9 package holds the library a program asks for
silik manifest export [FILE]            the machine's state in a JSON (--with-host adds name, user and MAC)
silik manifest diff FILE                what differs between this machine and the file (exits 0 if they are the same)
silik manifest apply FILE               the dnf transaction and the `silik` commands that bring this machine to the file
                                          (--prune to remove packages, --kernel to touch the kernel, --dry-run)
```

In the COMMAND bar: `vendor/list`, `vendor/check`, `vendor/TOOL`, `sys/manifest` (EN, CA, ES).

**What `silik vendor check` checks** (each check is fixed in the code; the data file only chooses which):

| Check | What it looks at | Who fixes it |
|---|---|---|
| vendor support | this system's EL 9 minor version against the ones the vendor names | nobody: the list is the vendor's |
| names an installer reads | `ID`, `VERSION_ID`, `/etc/redhat-release` (the base's) | `silik identity base` if it compares the visible name |
| packages, repositories | the EL 9 names of what the vendor asks for (`rpm -q`), and whether EPEL and CRB are there | `prepare`: `dnf install` |
| minimum versions, disk, memory | the figures the project gives (Zephyr, Yocto, ESP-IDF) | by hand |
| licence loader | `/lib64/ld-lsb-x86-64.so.3`: lmgrd asks for it by this name, and EL 9 has no `redhat-lsb-core` | `prepare`: a link |
| licence host id | the MAC addresses, and whether NetworkManager sets a random one (profile or default value) | by hand: `nmcli` (printed) |
| host name | that it is fixed and that it resolves | by hand: `hostnamectl` |
| `/usr/tmp`, locale, X11, SELinux | that they are there; SilikOS's session is X11 | `prepare` (link, package) or by hand |
| limits and kernel settings | `ulimit` and a few `sysctl`: only reported | never from here: `sudo sysctl -w` is done by the person |
| the vendor's udev rules | whether the vendor's file is there (it is never copied) | the vendor's installer |
| serial ports, USB instruments | the rules of `silik-dev` (uaccess): no `dialout` group, USBTMC for the user | `prepare`: `silik-dev` |
| CAN driver | whether the kernel's (SocketCAN) or the vendor's (`pcan`, linuxcan) is loaded, and whether the latter has blacklisted the kernel's | by hand |
| kernel headers | `kernel-devel` of the running kernel, for the modules the vendor compiles (NI, Keysight) | `prepare` |

`prepare` only runs `dnf` (install packages, enable a repository) and two links. It never touches a network
profile, a kernel setting, a module or a vendor's file (a test holds this for every tool).

## The tools

Packages: how many names the recipe carries; [A] means they do not come from the vendor's list (users' reports, or
the package that holds a library the tool asks for).

| Recipe | Tool | Version read | What the vendor says of EL 9 | Packages | Read on the vendor's page (13/11/2026) | Tried by installing it |
|---|---|---|---|---|---|---|
| **Licences** | | | | | | |
| `flexlm` | FlexNet (lmgrd and the vendor's daemon) | FlexNet Publisher 11.19 | RHEL 9 only; AlmaLinux is not named | - | no: a search engine's extract [A] | no |
| **FPGA** | | | | | | |
| `vivado` | AMD Vivado / Vitis | 2026.1 | yes: AlmaLinux 9 is named (9.4, 9.5, 9.6, 9.7) | 1 [A] | no: a search engine's extract [A] | no |
| `quartus` | Altera Quartus Prime Pro | 25.3 | RHEL 9 only; AlmaLinux is not named | - | no: a search engine's extract [A] | no |
| `libero` | Microchip Libero SoC | v2026.1 | yes: AlmaLinux 9 is named (9.6) | - | no: a search engine's extract [A] | no |
| `radiant` | Lattice Radiant | 2026.1 | RHEL 9 only; AlmaLinux is not named (9.6) | - | no: a search engine's extract [A] | no |
| **Computing and simulation** | | | | | | |
| `matlab` | MathWorks MATLAB / Simulink | R2026b | yes: AlmaLinux 9 is named | 56 | yes | no |
| `matlab-r2026a` | MathWorks MATLAB / Simulink | R2026a | RHEL 9 only; AlmaLinux is not named | 54 | yes | no |
| `matlab-r2025b` | MathWorks MATLAB / Simulink | R2025b | RHEL 9 only; AlmaLinux is not named | 55 | yes | no |
| `ansys` | Ansys | 2026 R1 | RHEL 9 only; AlmaLinux is not named | - | no: a search engine's extract [A] | no |
| `comsol` | COMSOL Multiphysics | 6.4 | RHEL 9 only; AlmaLinux is not named | 1 | no: a search engine's extract [A] | no |
| **Chip design and RF** | | | | | | |
| `cadence` | Cadence (Virtuoso, Spectre, Xcelium, Innovus) | 2025.x (IC23.1, IC25.1) | yes: AlmaLinux 9 is named | 21 [A] | no: a search engine's extract [A] | no |
| `synopsys` | Synopsys (Custom Compiler, HSPICE, VCS, Design Compiler) | Y-Foundation (2026.03, 2026.06, 2026.09) | yes: AlmaLinux 9 is named | 19 [A] | no: a search engine's extract [A] | no |
| `siemens` | Siemens EDA (Calibre, Questa, Xpedition) | - | not confirmed | - | no [A] | no |
| `ads` | Keysight ADS | ADS 2026 Update 2.0 | RHEL 9 only; AlmaLinux is not named | - | no: a search engine's extract [A] | no |
| **Microcontrollers and probes** | | | | | | |
| `stm32cubeide` | STM32CubeIDE | v2.1.0 (RN0114 Rev 37, 02/2026) | has a Linux version; no EL 9 named | - | no: a search engine's extract [A] | no |
| `stm32cubeprog` | STM32CubeProgrammer | v2.22.0 (RN0109 Rev 33) | has a Linux version; no EL 9 named | 1 | no: a search engine's extract [A] | no |
| `stm32cubemx` | STM32CubeMX | - | not confirmed | - | no [A] | no |
| `jlink` | SEGGER J-Link Software / Ozone | - | not confirmed | - | no: a search engine's extract [A] | no |
| `trace32` | Lauterbach TRACE32 | - | not confirmed | - | no: a search engine's extract [A] | no |
| `mcuxpresso` | NXP MCUXpresso IDE | v25.06 | has a Linux version; no EL 9 named | - | no: a search engine's extract [A] | no |
| `s32ds` | NXP S32 Design Studio | - | not confirmed | - | no [A] | no |
| `ccs` | TI Code Composer Studio | 20.4 | not confirmed | - | no: a search engine's extract [A] | no |
| `modustoolbox` | Infineon ModusToolbox | - | has a Linux version; no EL 9 named | - | no: a search engine's extract [A] | no |
| `aurix` | Infineon AURIX Development Studio | - | not confirmed | - | no [A] | no |
| `e2studio` | Renesas e2 studio | 2026-07 | has a Linux version; no EL 9 named | - | no: a search engine's extract [A] | no |
| `mplabx` | Microchip MPLAB X IDE | v6.30 | not confirmed | - | no: a search engine's extract [A] | no |
| **Open projects with requirements of their own** | | | | | | |
| `esp-idf` | Espressif ESP-IDF | v5.5.6 | has a Linux version; no EL 9 named | 11 | yes | no |
| `zephyr` | Zephyr RTOS and the Zephyr SDK | main (4.5.99), SDK 1.0.1 | has a Linux version; no EL 9 named | 18 + 4 [A] | yes | no |
| `yocto` | Yocto Project (build machine) | 5.2 (walnascar) | yes: AlmaLinux 9 is named | 36 | yes | no |
| **CAN** | | | | | | |
| `peak` | PEAK PCAN (USB, PCIe) | PCAN driver for Linux 8.x | in EL 9's kernel | 1 | no: a search engine's extract [A] | no |
| `kvaser` | Kvaser (USB, PCIe) | linuxcan (Kvaser Linux Drivers and SDK) | in EL 9's kernel | 1 | no: a search engine's extract [A] | no |
| `vector` | Vector CANoe / CANalyzer and the VN interfaces | Vector Driver Package 26.30.0 for Linux | no: Windows VM | - | no: a search engine's extract [A] | no |
| **Bench and instruments** | | | | | | |
| `ni` | NI Linux Device Drivers (NI-DAQmx, NI-488.2), LabVIEW | 2026 Q3 | RHEL 9 only; AlmaLinux is not named (9.6) | 2 [A] | no: a search engine's extract [A] | no |
| `visa-open` | Instruments, the open way (PyVISA + pyvisa-py, USBTMC) | - | in EL 9's kernel | 2 | yes | no |
| `visa-ni` | NI-VISA | NI Linux Device Drivers 2026 Q3 | RHEL 9 only; AlmaLinux is not named (9.6) | - | no: a search engine's extract [A] | no |
| `visa-keysight` | Keysight IO Libraries Suite for Linux | 2025 | RHEL 9 only; AlmaLinux is not named (9.0 to 9.4) | - | no: a search engine's extract [A] | no |
| `visa-rs` | Rohde & Schwarz VISA | 5.12.x | not confirmed | - | no: a search engine's extract [A] | no |
| `saleae` | Saleae Logic 2 | - | has a Linux version; no EL 9 named | 2 [A] | no: a search engine's extract [A] | no |
| `digilent` | Digilent WaveForms / Adept Runtime | Adept Runtime 2.27.9 | not confirmed | - | no: a search engine's extract [A] | no |

(MATLAB: what was read from the vendor is the list of packages MathWorks publishes for AlmaLinux 9 and RHEL UBI 9,
in the repository of its container images; its requirements page only in extracts [A]. Zephyr, ESP-IDF,
Yocto and pyvisa-py: the source of their documentation. `silik vendor check TOOL` shows the sentence read and the URL.)

Three things that come out of reading it, and that a buyer has to know:

- **SilikOS is 9.8 and several vendors name specific minors**: Vivado 2026.1 goes up to 9.7, Libero, Radiant and
  NI to 9.6, Keysight IO Libraries 2025 to 9.4 [A: extracts]. `silik vendor check` says it as a `warn`. The real way
  out is a laboratory channel frozen at the minor the vendor supports (idea 2).
- **Cadence gives Alma 9 "limited support"** and Synopsys names it as a binary-compatible system [A: extracts].
- **The microcontroller tools almost never name EL 9** (Ubuntu and Fedora). Working is not the same as being
  supported: none has been tried here.

## What was run (13/11/2026, container `almalinux:9`, AlmaLinux 9.8 x86_64, with CRB and EPEL 9)

| What | How | Result |
|---|---|---|
| Every package name exists | `bash tools/check_deps.sh --vendor` | 145 names: 144 resolve, `dfu-util` is built by SilikOS; `redhat-lsb-core` does not exist in EL 9 |
| Each list installs together | `dnf install --assumeno` of each tool's list (nothing downloaded) | 16 tools with packages, no dependency problem |
| `silik vendor prepare flexlm vivado cadence` for real | inside the container | packages installed, the link made; afterwards the rows are `ok` |
| `silik manifest` there and back | export A, prepare, export B, `apply A --prune`, `apply B` | `diff A` and `diff B` say "the same"; `dnf downgrade` of glibc to A's version included; export in 0.4 s |
| The version comparison | `rpm_vercmp` against `rpm.vercmp` of the same rpm 4.16 | 2401 valid pairs, no difference |
| The installed package | `tools/build_rpms.sh`, `dnf install` of silik-tools and silik-dev | `silik vendor` finds `/usr/share/silikos/vendors.conf`; the USBTMC rule is there |
| The USBTMC rule uses the form of the base's rules | `50-udev-default.rules` and `70-uaccess.rules` of systemd-udev 252-67.el9_8 | the base reads `ID_USB_INTERFACES` the same way (printers, PTP) |

**Not run:** no vendor's installer; nothing on an installed SilikOS with a desktop (NetworkManager, SELinux and
the session come out `unknown` in the container, as they must); no USBTMC instrument, no CAN adapter with the
vendor's driver; `silik manifest apply` with settings, boxes or kernel arguments for real (only with stand-ins); ARM.

## The manifest

A sorted JSON (two exports of the same machine are the same bytes), without secrets and without machine name,
user or MAC unless `--with-host` is asked for:

| Section | What it holds | `apply` |
|---|---|---|
| `base` | id, version, architecture | another architecture: it stops; another minor: it says so |
| `repos` | the ids of the enabled repositories (no URL) | enables `epel` and `crb`; the others must be defined on the machine |
| `packages` | each package: `name-epoch:version-release.arch @repository` | `dnf install` / `dnf downgrade` of the exact versions; removing, only with `--prune` |
| `kernel` | the kernel's packages (and `kmod-*`), the running kernel, the command line without what names disks | packages and arguments (`grubby`), only with `--kernel`; none of its packages is ever removed |
| `settings` | look, accent, glass, power, automatic updates | the corresponding `silik` commands |
| `boxes` | the boxes (name, image, EL) | `silik eda create`; a box's contents are not in it; none is ever deleted |
| `tools` | versions of the open bench and EDA tools; where the vendors' IDEs are | only reports (an IDE is the vendor's) |

To add a section: an entry in `MANIFEST_SECTIONS` of `silik` (name, export, compare, plan).

Limit: the exact versions must still be in the repositories. AlmaLinux's keep only the latest; that is why
"20 identical machines six months from now" needs a frozen channel (idea 2). Today: identical if it is applied soon,
or against a mirror of one's own.

## What an industrial buyer would pay for (PROPOSAL: ideas, none is done or promised)

In order of value for effort [A: it is a judgement, not a datum]:

1. **A list of vendors' tools tried for real.** Each row of this page with "tried by installing it: yes,
   version, date, machine". It is what no other distribution publishes. It needs evaluation licences and hours.
2. **A signed repository with a frozen "laboratory channel".** A snapshot of EL 9.x + EPEL + SilikOS per minor
   (9.6, 9.8), which does not move. `silik manifest apply` stops depending on what the mirrors keep, and the customer
   stays on the minor their vendor supports.
3. **Fleet manifest.** `silik manifest diff` against a reference file at each start, and a report of
   which machines of the laboratory have drifted. The piece for a single machine is already there.
4. **An ISO without network and a mirror for isolated rooms (`silik mirror`).** Chip companies work without
   Internet: the frozen channel on a disk, with the keys, and `silik update` pointing at it.
5. **Licence server mode.** A minimal installation with a fixed name and MAC, `lmgrd` as a service, the firewall
   open only on the licence's ports, and `silik vendor check flexlm` as the diagnosis.
6. **A list of certified hardware.** Workstations and laptops on which everything has been run (graphics, suspend,
   probes).
7. **Support aligned with EL 9 until 31/05/2032**, with a single party responsible.
8. **Evidence folders for tool qualification (ISO 26262, IEC 61508).** The signed manifest of the machine
   that compiled, the compiler's versions, and the record of each command: raw material for the customer's
   file. It is not a certification and must not be sold as one.

## Decisions that are the owner's

- Getting evaluation licences (or installers with their account) to turn rows into "tried".
- Whether SilikOS follows the latest minor (9.8) or also offers the one most vendors name (9.6).
- The frozen channel depends on the signed repository (key, host), which was already the first pending decision.

Sources:
- https://community.revenera.com/s/article/workaround-for-lsb-component-in-rhel
- https://community.flexera.com/t5/FlexNet-Publisher-Forum/FNP-on-RHEL-9/m-p/248927
- https://www.keil.com/support/docs/4044.htm
- https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Supported-Operating-Systems
- https://docs.amd.com/r/en-US/ug973-vivado-release-notes-install-license/Checking-Required-Libraries
- https://access.redhat.com/discussions/6995923
- https://www.intel.com/content/www/us/en/docs/programmable/683706/25-3/operating-system-support.html
- https://onlinedocs.microchip.com/oxy/GUID-D6BA99C6-E1C8-44EB-9669-702FBBAA3897-en-US-28/GUID-B0DCEFFF-6CEC-4D57-B4B0-90540F2BBC8A.html
- https://onlinedocs.microchip.com/oxy/GUID-D6BA99C6-E1C8-44EB-9669-702FBBAA3897-en-US-28/GUID-6EC547F0-2A3C-43E9-AB1C-F822E7AB53CF.html
- https://coredocs.s3.amazonaws.com/Libero/2025_2/Tool/libero_soc_v2025_2_release_notes.pdf
- https://www.latticesemi.com/Radiant
- https://github.com/mathworks-ref-arch/container-images/blob/main/matlab-deps/r2026b/almalinux9/base-dependencies-amd64.txt
- https://github.com/mathworks-ref-arch/container-images/blob/main/matlab-deps/README.md
- https://www.mathworks.com/support/requirements/matlab-linux.html
- https://github.com/mathworks-ref-arch/container-images/blob/main/matlab-deps/r2026a/ubi9/base-dependencies.txt
- https://github.com/mathworks-ref-arch/container-images/blob/main/matlab-deps/r2025b/ubi9/base-dependencies.txt
- https://www.cadence.com/en_US/home/support/computing-platform-support/support-road-map-2024x-2027x.html
- https://www.cadence.com/en_US/home/support/computing-platform-support/support-road-map-2022x-2025x.html
- https://community.cadence.com/cadence_technology_forums/pcb-design/f/licensing-and-installation/65488/cadence-tool-compatibility-and-installation-support-on-almalinux
- https://community.cadence.com/cadence_technology_forums/f/custom-ic-skill/62692/ic-23-1-installation-configuration-failure-on-rhel-9
- https://www.synopsys.com/support/licensing-installation-computeplatforms/compute-platforms/release-specific-support/supported-y-foundation.html
- https://www.synopsys.com/support/licensing-installation-computeplatforms/compute-platforms/platform-notice/2025-y-foundation-centos-support-changes.html
- https://synopsys.com/support/licensing-installation-computeplatforms/licensing/scl-supported-os.html
- https://www.europractice.stfc.ac.uk/tools/siemens.html
- https://community.altera.com/discussions/quartus-prime/license-setup-for-questa-on-red-hat/295884
- https://www.keysight.com/jp/ja/lib/software-detail/computer-software/pathwave-advanced-design-system-ads-software-2212036/ads-2026-update-2-0-linux.html
- https://ansyshelp.ansys.com/public/views/secured/corp/v261/en/installation/unix_sysprereqs.html
- https://www.drd.com/wp-content/uploads/2026/03/ansys-platform-support-strategy-plans-march-2026.pdf
- https://www.comsol.com/system-requirements/64/general
- https://www.st.com/resource/en/release_note/rn0114-stm32cubeide-release-v210-stmicroelectronics.pdf
- https://community.st.com/t5/stm32cubeide-mcus/stm-cube-ide-installation-problem-in-rhel/td-p/783224
- https://www.st.com/resource/en/release_note/rn0109-stm32cubeprogrammer-release-v2220-stmicroelectronics.pdf
- https://dev.st.com/stm32cube-docs/prog/2.23.0/en/docs/markup/CubeProg_How_To_Start/CubeProg_Installation.html
- https://kb.segger.com/Linux_specifics
- https://segger.com/products/development-tools/ozone-j-link-debugger/technology/system-requirements
- https://forum.segger.com/index.php/Thread/5002-JLink-broken-Linux-RPM-install-packages
- https://forum.segger.com/index.php/Thread/6318-SOLVED-Unable-to-install-Segger-JLink-on-Linux-udev-rules-error-possible-conflic
- https://support.lauterbach.com/kb/articles/linux-why-isn-t-linux-booting-after-installing-usb-driver-file-10-lauterbach-rules
- https://www2.lauterbach.com/pdf/installation.pdf
- https://www.nxp.com/mcuxpresso/ide
- https://software-dl.ti.com/ccs/esd/documents/ccs_linux_host_support.html
- https://software-dl.ti.com/ccs/esd/CCSv20/CCS_20_4_1/exports/CCS_20.4.1_ReleaseNote.htm
- https://software-dl.ti.com/ccs/esd/CCSv20/CCS_20_0_1/exports/CCS_20.0.1_ReleaseNote.htm
- https://documentation.infineon.com/modustoolbox/docs/general-information
- https://www.renesas.com/en/document/rln/e-studio-2026-07-release-note
- https://www.renesas.com/en/document/mat/quick-start-guide-linux-hosted-version-e-studio
- https://developerhelp.microchip.com/xwiki/bin/view/software-tools/x/requirements
- https://developerhelp.microchip.com/xwiki/bin/view/software-tools/x/archive/linux/
- https://github.com/espressif/esp-idf/blob/release/v5.5/docs/en/get-started/linux-macos-setup.rst
- https://github.com/espressif/esp-idf/blob/release/v5.5/docs/en/get-started/establish-serial-connection.rst
- https://github.com/zephyrproject-rtos/zephyr/blob/main/doc/develop/getting_started/installation_linux.rst
- https://github.com/zephyrproject-rtos/zephyr/blob/main/doc/develop/getting_started/index.rst
- https://github.com/zephyrproject-rtos/zephyr/blob/main/doc/develop/toolchains/zephyr_sdk.rst
- https://github.com/yoctoproject/poky/blob/walnascar/documentation/ref-manual/system-requirements.rst
- https://github.com/yoctoproject/poky/blob/walnascar/documentation/tools/host_packages_scripts/almalinux_essential.sh
- https://github.com/yoctoproject/poky/blob/walnascar/documentation/poky.yaml.in
- https://docs.yoctoproject.org/5.2/ref-manual/system-requirements.html
- https://www.peak-system.com/fileadmin/media/linux/index.php
- https://www.peak-system.com/PCAN-Linux.358.0.html
- https://github.com/torvalds/linux/blob/v6.12/drivers/net/can/usb/peak_usb/pcan_usb_core.c
- https://kvaser.com/?p=30789
- https://old.can-cia.org/fileadmin/resources/documents/publications/cnlm_issues/march_2024/cnlm_24-1_p30_socketcan_versus_linuxcan-make_the_right_choice_adam_raymer_kvaser.pdf
- https://github.com/torvalds/linux/blob/v6.12/drivers/net/can/usb/kvaser_usb/kvaser_usb_core.c
- https://www.vector.com/us/en/download/
- https://www.vector.com/en/product/canoe-server-editions/
- https://www.ni.com/en/support/documentation/compatibility/26/ni-linux-device-drivers-2026-q3-compatibility.html
- https://www.ni.com/docs/en-US/bundle/ni-platform-on-linux-desktop/page/supported-drivers-for-linux-distributions.html
- https://github.com/pyvisa/pyvisa-py/blob/main/docs/source/installation.rst
- https://github.com/torvalds/linux/blob/v6.12/drivers/usb/class/usbtmc.c
- https://helpfiles.keysight.com/IO_Libraries_Suite/English/IOLS_Linux/IOLS/Content/Introductory_Topics/Whats_New_For_Linux_Users.htm
- https://helpfiles.keysight.com/IO_Libraries_Suite/English/IOLS_Linux/IOLS/Content/Introductory_Topics/Reference_Topics/Revision_Matrix.htm
- https://www.rohde-schwarz.com/us/applications/r-s-visa-application-note_56280-148812.html
- https://support.saleae.com/logic-software/sw-installation
- https://support.saleae.com/troubleshooting/linux-permission-requirements-for-logic-software
- https://forum.digilent.com/topic/28753-repository-w-signed-packages-for-digilent-waveforms-rpm/
- https://forum.digilent.com/topic/28525-digilent-adept-runtime-package-header-is-not-signed/
- https://forum.digilent.com/topic/20462-waveform-install-on-linux-mint20/
- https://endoflife.date/almalinux
