# The first hour with SilikOS

For somebody who has never seen SilikOS and has a board, a probe and a CAN adapter on the table. The aim: from the
ISO to flashing the board and seeing the CAN bus, in less than an hour (it is the aim: nobody has timed it yet),
without asking anybody anything. If you had to ask at some step, that step is wrong: write it down
(section 9).

Each step says how far it has been tried. **Nothing in this guide has been done on real hardware yet**: the
installation and the commands have run in a virtual machine (GitHub's CI, 13/11/2026); the probe, the board and the
CAN adapter have not.

## 0. What you need

| What | Detail |
|---|---|
| An x86_64 PC with UEFI | a disk that can be erased whole: the installation takes 14-15 GB of it (measured in the CI). The test virtual machine has 4 GB of memory; less has not been tried |
| A 4 GB USB stick | for the installer |
| A wired network during the installation | the installer downloads 2.5 GB (`docs/NUMBERS.md`) |
| The probe | ST-LINK (or a Nucleo, which carries one), J-Link or CMSIS-DAP |
| The CAN adapter | PCAN-USB, Kvaser, candleLight / CANable, or another with a driver in the kernel (`docs/DRIVERS.md`) |

If the laptop is very new, read `docs/DRIVERS.md` first: it says which Wi-Fi, which network and which graphics have
a driver.

## 1. The ISO

There is no ISO to download from a fixed link yet. Three ways:

- **From the CI, the network ISO (2 GB)**: on GitHub, Actions → CI → the last **green** run of `main` → Artifacts
  → `silikos-iso` (you must be signed in to GitHub; it downloads a `.zip` with the ISO inside; it is kept 14 days).
  It is the ISO that the same run installed and checked. Until 14/11/2026 this artifact was kept only with a
  version tag, and there is none: this guide sent you to an artifact that did not exist.
- **From the CI, the offline ISO (4.6 GB)**: Actions → Offline ISO → Run workflow; when it ends green, Artifacts →
  `silikos-offline-iso`. It carries every package: the installation downloads nothing (`docs/OFFLINE.md`). It needs
  an 8 GB USB stick.
- **Build it**: on any Linux with `xorriso`, `mtools`, `cpio`, `curl` and `gpg`: `bash tools/build_iso.sh`
  (`docs/BUILD.md`).

**Without an installer** (14/11/2026): the workflow **Disk image** keeps a disk image of SilikOS already
installed (Actions → Disk image → the last green run → Artifacts → `silikos-disk-image`, 8 GB). Written to a disk
of 40 GB or more as it is (balenaEtcher takes the `.img.xz`; **it erases that disk**), the disk starts SilikOS on
any x86_64 computer with UEFI; its first start takes the whole disk and asks for the language, the keyboard and
the user: skip sections 1 and 2. (`silikos10-disk-image` is the same of the SilikOS 10 lab.) It is not encrypted. `docs/DISK.md` says what it is and what was seen of it (virtual machines only).

Copy it to the USB stick (replace `sdX` with your USB stick; **it erases the USB stick**):

```bash
sudo dd if=SilikOS-9.8-x86_64-netinstall.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

From Windows [A: not tried here]: a program that writes the image as it is, byte for byte (balenaEtcher; or
Rufus, choosing "DD Image" when it asks for the mode). A stick made with Ventoy or by copying the files onto it by
hand will not do: the menu looks for the installer and its kickstart by the label of the ISO's volume.

Tried: the ISO is built and installed at every run of the CI. As a USB stick, with UEFI and Secure Boot on, in a
virtual machine (workflow External disk, job `medium`, run 43589350760 of 14/11/2026): the firmware
starts it, the menu shows the external disk's entry, and that entry starts the installer up to its
first screen ("WELCOME TO SILIKOS 9.8"). From a USB stick on a real machine: no.

## 2. Install

1. Start from the USB stick. In the menu, **Install SilikOS 9.8**.
2. Choose the language.
3. **Installation Destination**: choose the disk yourself. The installer erases none until you confirm it, but
   look carefully at which ones are ticked: with more than one disk it may tick them all [read in the installer's
   code, not seen]; untick the ones you do not want touched. Leave
   "Automatic": it lays the disk out so that an update can be undone afterwards (`silik rollback`).
   Tick **Encrypt my data** and give it a long passphrase: the installer does not tick it by itself, and without
   encryption whoever has the laptop in their hands reads its disk (`docs/DISK.md`; afterwards, `silik disk`).
4. Create your user and begin. When it finishes, restart and take the USB stick out.

Tried: an unattended installation in a virtual machine (168 checks ok in run 43566415197). With the screens by
hand and on a real disk: no.

### On an external disk, to start it from the boot menu

To try SilikOS without touching the computer's disk: the whole system on an external disk, and the computer's boot
menu (F12, F9 or Esc at power-on, depending on the maker) to choose. **Tried in virtual machines, not yet on a real
disk or a real computer** (`tests/install/external.sh`, workflow External disk: the installation
with UEFI onto a USB disk beside another disk that stands for "the computer's own", and the start after it; in
its last run, 43603388840 of 14/11/2026, also the whole desktop, encrypted: 25 checks ok, none failed). What
follows was seen there, except what is marked [A]. Detail: `docs/DISK.md`.

Before you begin:

- If Windows has BitLocker, have the **recovery key** at hand (account.microsoft.com/devices/recoverykey)
  before you touch anything in the firmware [A: not tried with Windows beside it].
- Unplug the other external disks and USB sticks that are not needed: then the disk screen shows only
  what you want.
- The external disk **will be erased whole**.

1. Plug in the external disk (best an SSD in a USB 3 enclosure, on a USB 3 port) and the installer's USB stick.
2. Start from the installer's USB stick (the firmware's boot menu). In SilikOS's menu, the **third entry**:
   **Install SilikOS 9.8 on an external disk (the boot order of this computer is kept)**. With this entry:
   - the installer does not put itself first in the computer's boot list and removes no entry from it (seen: the
     list, the same before and after the installation);
   - **the computer's disks do not appear on the screen**: the installer shows only the disks that are on USB,
     so the internal disk cannot be ticked by mistake. Seen in the test (run
     43587008261): the test names no disk and erases every disk the installer shows; the disk that stands for "the
     computer's own" comes out identical byte for byte. **Only the ISOs built from commit 27309ef (14/11/2026)
     onwards have this.**
3. **Installation Destination**: the external disk must be there (and perhaps the installer's USB stick). Tick the
   external disk; go by the size and the name. If no disk appears there, your external disk is not on USB
   (Thunderbolt, eSATA): go back and use the first entry, looking very carefully at what you tick.
   Leave "Automatic". [A: that is how the base's installer is; not seen here, the test does not go through the screens]
   If the disk already had partitions, the installer asks to free space: "Reclaim space" → "Delete all" →
   "Reclaim space"; it touches only the ticked disk.
4. Tick **Encrypt my data** with a long passphrase: an external disk is lost more easily than a computer.
   It will be asked for every time you start, on SilikOS's boot screen: the dark background, the mark, the text
   "Please enter passphrase for disk…" and an entry box (seen in a virtual machine, run 43603388840: the
   passphrase typed once opens the disk, and the login screen comes up after it). If the screen ever stayed black without asking anything: in the GRUB
   menu, key `e`, delete `rhgb quiet` from the line that begins with `linux`, Ctrl+X, and it asks in text.
5. Create the user, begin, and when it finishes shut down, take the installer's USB stick out and start with the
   firmware's boot menu: choose the external disk.

Afterwards (seen in the test, except what is marked):

- **Shut the system down before you unplug the disk.** If it is pulled out while it runs, the system goes down at once.
- **The first time it is started from the external disk, the base's boot loader adds itself to the computer's list
  with the name `almalinux` and puts itself first** (and on a machine with a TPM it restarts once). From then on,
  with the disk plugged in, the computer starts SilikOS by itself; without the disk, what it had [A: a firmware
  skips the entry of a disk that is not there; not seen on a real one]. To put the computer's own system first
  again: the firmware's setup, or from SilikOS `sudo efibootmgr` (the list) and
  `sudo efibootmgr -o NUMBER,NUMBER,...` (the order).
- The computer's disk is not touched: in the test, the disk that stands for "the computer's own" is identical byte
  for byte after the installation and after two starts from the external disk.
- `silik disk check` says what there is to know about a system on an external disk.
- **The TPM**: `silik disk tpm enroll` ties the disk to *this* computer. If the disk has to go from one computer
  to another, leave it with the passphrase and nothing else.
- **On another computer**: the disk as installed starts on another computer through USB, also with
  Secure Boot on. For it to start plugged in through SATA or NVMe as well, `silik disk check` gives two commands (a
  package of the base and `dracut`) that rebuild its start-up files with every driver.
- USB protection and the saver profile leave the disk the system is on alone (USBGuard allows it; the profile
  does not put it to sleep).

## 3. The first minute on the desktop

- The piece at the bottom is the island: the mark on the left opens **Start** (or the Super key).
- **Super+Space** opens the COMMAND bar: you type an address (`sys/`, `dev/`, `look/`...) and below it you see the
  command that will run. Everything the desktop does is a `silik` command that you can copy.
- Open a terminal (it is in Start, among the pinned ones).

## 4. How the machine is

```bash
silik doctor          # system, security, graphics, hardware, bench, EDA, Windows, network: ok / warn / bad and the command that fixes it
silik hw check        # each device with its driver, or "no driver in this kernel" and what to do
```

If `silik doctor` says `bad` for anything other than "the disk is not encrypted", write it down.

Tried: in a virtual machine. With your hardware: it is the first thing we want to know.

## 5. The probe and the board

```bash
silik dev tools       # the ARM compiler, OpenOCD, dfu-util, the ST-LINK tools... and what is missing
silik dev try         # the tools do real work: they compile a program for Cortex-M4, link it, debug it
```

Connect the probe (no need to be root: the rules already give the probe to whoever sits at the screen):

```bash
silik dev try probe   # does OpenOCD see the probe?
st-info --probe       # (ST-LINK) which board is there
```

Flash an ELF with OpenOCD (replace `stm32g4x` with your family):

```bash
openocd -f interface/stlink.cfg -f target/stm32g4x.cfg -c "program build/firmware.elf verify reset exit"
```

STM32CubeIDE does not come with the system (it is ST's): download it from ST's website and

```bash
silik dev install ~/Downloads/en.st-stm32cubeide_*.sh.zip
```

Tried: `silik dev try` passes in a virtual machine (7 jobs). With a probe and a board: no. `silik dev install` with
ST's real installer: no.

## 6. The CAN bus

```bash
silik dev can                     # the adapters it sees
silik dev can up can0 500k        # prints the three `ip link` commands it runs, and runs them
candump can0                      # what goes over the bus
cansend can0 123#DEADBEEF         # sends a frame
```

- CAN FD: `silik dev can up can0 500k --fd 2M`. Listening only, without even acknowledging frames: `--listen`.
- With windows: SavvyCAN (in Start, category Bench). With a DBC: `candump can0 | cantools decode file.dbc` (the package
  silik-pylab; `silik dev tools` says whether it is there).

Tried: the commands, in a virtual machine without an adapter. With an adapter and a bus: no.

## 7. The serial port

```bash
silik dev serial                  # the ports and what they are
picocom -b 115200 /dev/ttyACM0    # Ctrl-A Ctrl-X to leave
```

## 8. If you want to go one step further: an automatic test (experimental)

```bash
mkdir trial && cd trial
silik hil new                     # an example: a simulated ECU, its DBC and a plan
silik hil run ecu.plan            # 23 steps; no hardware needed
```

The plan is a text file: which frames are sent, what is expected and within how long, which requirement each step
verifies. `bench.plan` is the same for a real board (`docs/HIL.md`). It has run only with the simulated ECU.

## 9. If something fails

- **The installer's USB stick does not appear in the firmware's boot menu**: write it again (above, section 1) and
  try another port. [A]
- **The screen stays black when the installer or the system starts** (laptops with NVIDIA graphics) [A: not
  seen; it is the base's usual remedy]: in the menu, key `e` on the entry, add `nomodeset` at the end of the
  line that begins with `linux`, and Ctrl+X. With the system installed: `silik hw nvidia` says what is there and what to do.
- **The installer finds no network** (the network ISO downloads the packages): a cable, or the phone through USB, or
  the Wi-Fi in "Network & Host Name" and then open "Installation Source" again. Or use the offline ISO.
- An update broke something: `silik rollback` (it goes back to how it was before the last update) and
  restart.
- To explain it, send these two outputs:

```bash
silik doctor --json > doctor.json
silik hw check --json > hardware.json
```

- And write down **where you got stuck**: which step, what you expected and what happened. This list is what it
  takes to turn this into a product.

## What stays written of your hour

If you reached the end, tell us how long it took and the model of the PC. The `hardware.json` of your machine is
the first row of the list of tried hardware: today that list is empty.
