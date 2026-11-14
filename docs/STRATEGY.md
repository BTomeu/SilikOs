# SilikOS: strategy memo (12/11/2026)

Research by an agent (web + a read of the repository), reviewed. No number is invented; assumptions are
marked [A]. The websites of Cadence and Synopsys could not be reached from the session: what we say about them comes
from the search engine's extracts of their official pages and has to be confirmed on each release's page.

## 1. Where it is unique today

**What nobody else puts together.** No desktop distribution has been found that does all of these at once:
- it is binary RHEL 9;
- it has EL6/7/8 boxes for the old releases of Cadence and Synopsys, with the host's network and hostname thought out
  for FlexLM;
- it carries 11 open EDA tools built for EL 9, and each one does a real job (`silik eda try`);
- it has a Wine of its own inside a box;
- it carries the bench tooling: SocketCAN, SavvyCAN, sigrok and OpenOCD;
- it shows each command it runs.

**The others do only a part:**
- **IIC-OSIC-TOOLS:** it is an Ubuntu container with PDKs. It is not a system and is of no use for the commercial tools.
- **nix-eda / LibreLane:** reproducible, but only for the open digital flow.
- **Bluefin LTS** (EL10 + bootc): it has atomic updates, but does not allow local layering. That breaks the
  installers of the commercial EDA tools, which ask for RPMs.
- **Fedora Electronic Lab:** it was left without a maintainer.
- **Pop!_OS COSMIC:** it has polish and NVIDIA, but runs on Ubuntu.

**The base has become stronger:**
- Synopsys Y-2026 lists AlmaLinux 9.x as a supported binary-compatible system.
- Cadence 2025.x adds Alma 9 and Rocky 9, with "limited support".
- MATLAB R2026a lists RHEL 9 (from 9.2 on).

**What is real:** the ISO installs unattended in the CI (86 checks), there are the unit tests, and Start and `silik`
are faster (measured).

**What is not yet:**
- Nothing has been run on real hardware: NVIDIA, Wi-Fi, suspend, CAN adapters, flashing a board.
- No vendor tool has been tried, and neither has the Windows VM.
- There is no public or signed package repository.
- The CI is stopped by GitHub's billing.

Today it is an **excellent prototype verified in a VM**, not yet a product.

## 2. Gaps that matter, by impact and effort

1. **A signed and public package repository, and the CI running.**
   - Highest impact and low effort, but it depends on the owner: the key, the host and the billing.
   - Without it, SilikOS's packages are never updated on the installed machines.
2. **Real hardware and a list of certified hardware.**
   - NVIDIA with AlmaLinux's precompiled open modules (`nvidia-open-kmod`): they are signed with the kernel's key and
     work with Secure Boot without MOK.
   - `silik update` should hold a new kernel back until there is a module for it.
   - `silik hw report`, run on the Ryzen, makes a row of the list. Only what has been run goes into the list.
3. **Rolling back with one command.**
   - EL 9.6+ carries snapm and boom-boot: LVM thin snapshots with an entry in the boot menu.
   - Step: `silik snap` / `silik rollback`, with a snapshot before each risky update.
   - It needs a disk with LVM thin [A: how to offer it without the kickstart choosing the disk].
4. **Getting ready for the vendor tools, without distributing them.**
   - Verifiable recipes for Virtuoso/Spectre, MATLAB, CubeIDE, J-Link, Vivado, Zephyr and Yocto.
   - Each recipe checks the prerequisites, the udev rules, the hostid/lmgrd and the base's version.
   - Known problems:
     - CubeIDE only lists Ubuntu and Fedora.
     - J-Link's RPMs have had broken dependencies.
     - PEAK's chardev driver and SocketCAN cannot live together: `silik dev can` has to detect it.
5. **PDKs and the digital flow.** Without a PDK, the open chip tools are a demo. Step: `silik eda pdk add
   ihp-sg13g2|sky130|gf180`, with the user's explicit permission, and a trial RTL→GDS inside podman.
6. **The Windows VM with a real VN1630.** Vector's Linux driver is for Ubuntu only, and desktop CANoe
   is Windows only. Step: try it on the Ryzen.
7. **An ISO without a network and a minimal first start.** It should ask the profile (chips / embedded / bench),
   NVIDIA yes or no, and the disk prepared for rolling back.

### Four product lines (owner, 14/11/2026)

The owner orders them like this, and starts with the first "because it is the only one that makes SilikOS and
SilikStudio a product nobody copies in a weekend":

1. **A bridge between the SIL and the real bus.** A real ECU on the table, through `can0`, talking to the rest of the
   car emulated in SilikSIL. It needs the two pieces at once: the system's adapters and the virtual ECUs.
   - **Started on 14/11/2026**: `svsil bench --bridge BUS=IFACE --real NODE` in SilikStudio and `silik sil bridge` here,
     with one command (also with two adapters, for an ECU that is on two buses like the VCU). Tried on
     real SocketCAN interfaces (`vcan0`, `vcan1`) with the EL 9 kernel in a virtual machine; not with an
     adapter or with an ECU (`docs/DEV.md`, `docs/STATUS.md`).
   - **The limit that was measured**: it is only of use in real time, and the emulation is an interpreter. On the build
     machine (one thread of a shared Xeon at 2.1 GHz), the ecoRacing car with the VCU real and the seven other ECUs
     emulated with their firmware holds real time (x1.000; at the worst moment 3.1, 6.3 and 69.7 ms behind in
     three runs, from the scheduling of a shared machine). With the VCU emulated it does not: the whole car runs at
     x0.41 (the VCU alone is 76 % of the cost). What would move it [PROPOSAL, not started]: one thread per MCU inside
     each quantum and real-time priority for the run. Not measured outside the build machine.
2. **Power electronics bench** [PROPOSAL, not started]. Instrument control over SCPI and automatic
   analysis: from the double pulse to Eon, Eoff and Qrr, and from the I-V and C-V curves to the datasheet values.
3. **Remote bench** [PROPOSAL, not started]. Sharing a CAN reader, a serial port or a logic analyser over the
   network, with one command and encrypted.
4. **An open chip flow that works the first time** [PROPOSAL, not started]. The open PDKs (sky130, gf180, IHP)
   installed, and a trial from schematic to layout, DRC, LVS and extraction (point 5 of the list above).

## 3. What not to do

- **More looks and accents.** Three looks and six accents are enough; from now on, polish and add none.
- **Keep investing in a shell of our own on GNOME 40.** EL10 carries GNOME 47 and Wayland.
- **Altium inside Wine.** The history says the VM is the way.
- **Build what is already in EPEL**, or GHDL (on EL 9 there is no viable Ada compiler).
- **Snapdragon X1 on bare metal**, or convert SilikOS to bootc on EL 9.
- **Measure progress by the CI's checks.** The metric is the rows of real hardware and real tools.

## 4. "Minimalist premium" that is not cosmetic

- **One sheet of numbers per release** (`silik bench system`), measured on the reference machine: boot to
  the desktop, latency of Start and of the COMMAND bar, update time, rollback time.
- **Recovery with one command:** `silik rollback`, with an automatic snapshot before risky changes.
- **Reproducibility:** `silik manifest export/apply`, the exact list of packages to have the laboratory's machine
  the same as yours.
- **Two public lists:** the certified hardware and the vendor tools, each row with a date and a state (tried / not
  tried).
- **Silence:** no telemetry, and the system never restarts on its own.
- **Transparency as the central message:** each action shows the command it runs, and "ok" is never said of what is
  not seen.
- **One support horizon:** until 31/05/2032, in line with EL 9.

## 5. Risks

- **EL 9's cycle.** Full support ends on 31/05/2027 and maintenance on 31/05/2032. New laptops may not
  work with the 5.14 kernel [A].
- **Migration to EL 10.**
  - It removes Xorg and carries GNOME 47.
  - The extensions of GNOME 45 and later are ES modules: `silik-shell` has to be ported, not just rebuilt.
  - Third-party packages for EL 10 will be x86-64-v3 [A].
  - SilikOS 10 when the two big EDA vendors support EL 10 [A: ~2027–28].
- **GNOME 40 is ageing:** GTK4 applications do not take the GTK3 theme.
- **ARM:** the X1 has little support; ARM stays as a VM or as an EL 10 experiment.
- **NVIDIA:** the module can arrive later than the kernel. That is why holding the kernel back and rolling back are
  needed.
- **One maintainer and dependence on GitHub:** it must be possible to move the repository to another host.
- **Cadence's "limited" support on Alma:** `silik identity base` helps, but the commercial risk is there.

Sources:
- https://www.cadence.com/en_US/home/support/computing-platform-support/support-road-map-2024x-2027x.html
- https://www.cadence.com/en_US/home/support/computing-platform-support/support-road-map-2022x-2025x.html
- https://community.cadence.com/cadence_technology_forums/pcb-design/f/licensing-and-installation/65488/cadence-tool-compatibility-and-installation-support-on-almalinux
- https://www.synopsys.com/support/licensing-installation-computeplatforms/compute-platforms/release-specific-support/supported-y-foundation.html
- https://github.com/iic-jku/IIC-OSIC-TOOLS
- https://github.com/fossi-foundation/nix-eda
- https://fossi-foundation.org/librelane
- https://openroad-flow-scripts.readthedocs.io/en/latest/index2.html
- https://docs.projectbluefin.io/blog/bluefin-lts-ga/
- https://wiki.almalinux.org/sigs/Atomic
- https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/configuring_and_managing_logical_volumes/managing-system-upgrades-with-snapshots_configuring-and-managing-logical-volumes
- https://www.redhat.com/en/blog/rhel-10-plans-wayland-and-xorg-server
- https://endoflife.date/almalinux
- https://almalinux.org/blog/2025-08-06-announcing-native-nvidia-suport/
- https://wiki.almalinux.org/documentation/nvidia.html
- https://forums.almalinux.org/t/technical-incident-report-nvidia-driver-almalinux-9-7-kernel-incompatibility/7216
- https://www.mathworks.com/support/requirements/matlab-linux.html
- https://www.vector.com/en/product/canoe-server-editions/
- https://docs.yoctoproject.org/5.2/ref-manual/system-requirements.html
- https://docs.zephyrproject.org/latest/develop/getting_started/installation_linux.html
- https://community.st.com/t5/stm32cubeide-mcus/stm-cube-ide-installation-problem-in-rhel/td-p/783224
- https://forum.segger.com/index.php/Thread/5002-JLink-broken-Linux-RPM-install-packages
- https://www.peak-system.com/PCAN-Linux.358.0.html
- https://codeweavers.com/compatibility/crossover/altium-designer
- https://fedoraproject.org/wiki/Electronic_Lab
- https://www.cnx-software.com/2026/09/25/qualcomm-releases-linux-developer-preview-snapdragon-x2/
