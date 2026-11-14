# SilikOS, explained from zero

This document explains what SilikOS is, why it exists, how it is made and where it stands, for somebody who knows
nothing about it. The technical detail is in the other documents of `docs/`; here is the idea.

---

## 1. The problem

An electronics engineer uses, on a normal day:

- **Chip and board design tools** (EDA): Cadence Virtuoso, Synopsys, KiCad, circuit simulators
  (SPICE), layout tools.
- **Microcontroller tools**: compilers for ARM, debuggers, programmers (ST-LINK, J-Link), the makers' IDEs
  (STM32CubeIDE, Code Composer Studio).
- **Bench tools**: CAN bus readers, serial and RS485 ports, logic analysers, oscilloscopes.
- **Windows programs** that have no alternative (Altium, LTspice, CANoe, some makers' tools).

Today that means having it scattered: a virtual machine with an old Red Hat for the chip tools, a Windows
for the Windows programs, and a laptop where each thing is installed by hand and breaks at the first update.

The big EDA tools (Cadence, Synopsys) only work officially on **Red Hat Enterprise Linux (RHEL)**.
Not on Ubuntu and not on Windows.

## 2. The idea

**SilikOS is an operating system for electronics engineers that has everything in one place:**
chip and board design, microcontrollers, the bench and Windows programs, with a
desktop of its own and with SilikStudio (SilikVolt's software) as the central piece.

The decision that makes it possible: **not to make a new operating system, but to put a compatible one on top of one
that already exists.**

```
┌──────────────────────────────────────────────────────────────┐
│  SilikOS: what we put in                                     │
│  desktop, tools, bench, Windows, security, updates           │
├──────────────────────────────────────────────────────────────┤
│  AlmaLinux 9: the base, UNTOUCHED                            │
│  kernel, libraries, packages: identical to Red Hat 9         │
└──────────────────────────────────────────────────────────────┘
```

**AlmaLinux 9** is a free system that aims for binary (ABI) compatibility with Red Hat Enterprise Linux 9. A program
made for Red Hat 9 works on it as it is. That is why **we never touch the base**: not the kernel, not the libraries,
not the files that installers check. If we touched it, we would lose the compatibility, which is all the value.

Everything that is SilikOS is **packages on top** (RPM, Red Hat's format), which are installed and removed like
any other.

## 3. What somebody who starts it sees

### The desktop

The desktop is GNOME (Red Hat's), but rearranged with an extension of our own so that it is the **Silik
interface**, the same visual family as SilikStudio. It has three looks, which are changed with one command:

- **island** (the default): a floating piece at the bottom with the applications, Start and the clock;
- **bar**: a bar at the bottom, in a more classic style;
- **silik**: a command line at the top, a rail of keys on the left and a status bar, like a terminal.

By default it is **ink on paper**: black and white, clean, with no decorative colours. For more life, there are
**accents** (steel, cobalt, indigo, violet, spark yellow). Each accent has a normal level and a vivid level, and it
also makes the icons of folders and files carry a colour for what they hold: code, design, physical, data… The
original ink is always there.

The pieces that float (the island or the bar, Start and the COMMAND bar) are of **glass**: paper that is a little
translucent over what is behind it, blurred, with its thin ink frame and a soft shadow. Which glass is a choice:

| `silik look --glass …` | in the COMMAND bar | what it is |
|---|---|---|
| `off` | `look/glass-off` | opaque paper, no glass |
| `on` (the current one) | `look/glass` | paper at 86 % over the blurred background |
| `clear` | `look/glass-clear` | paper at 70 % over the blurred background |
| `crystal` | `look/glass-crystal` | paper at 72 %: the windows behind are also seen, blurred |
| `crystal-thin` | `look/glass-crystal-thin` | paper at 55 %, more blurred |

With `on` and `clear` the background is seen, not the windows: what is under the text is always the same and costs
nothing while nothing changes (the blur is made once and kept). With the two crystal ones the windows behind Start
and the COMMAND bar are seen, and they follow what those do (if one moves, closes or has text passing, the glass
shows it): this costs a blur at each frame in which a window underneath changes, only while the piece is
open. The island and the bar, which are always there, only show the windows right under them. In every mode the
text can be read (4.5:1 at least) even with black behind: the thinner the paper, the darker the grey text
becomes, and at the thinnest it is ink. The measurements of each mode are in `docs/STATUS.md`.

The **background** is an engineering drawing sheet, and there is a set of eight, each with its dark twin:
`silik look --wallpaper wafer | plain | grid | scope | pcb | mesh | schematic | cells` (the current wafer map, a blank
sheet, a grid of dots, an oscilloscope, a printed circuit, a finite-element mesh, a schematic, rows
of standard cells), and `NAME-dark` puts the dark twin on the desktop; in the COMMAND bar, `look/wallpaper-…`. They go
from the calmest (`plain`) to the densest (`cells`), so that the glass can be judged over different backgrounds. The
mark is there, as it is, on `wafer` and on `grid`; on the others it is not. A picture of your own chosen in Settings
is not touched unless it is asked.

The system menus, the calendar, the notifications, the volume indicator, the dialogs and the window switcher
(Alt+Tab) are of the same **paper and ink**: a thin ink frame, corners of 6 px (4 on the keys), Cascadia Mono, what
is chosen in inverse video (or with the accent). They are opaque paper, not glass. The title bar of the Silik look
and the lock and login screens stay dark, with the keys and the password field as everywhere else.

When the laptop is in **saver** mode (`silik power saver`), the glass rests: the pieces go back to opaque paper and
get the glass back on leaving it (`silik look --glass-saver off` turns this off).

### The COMMAND bar

**Super+Space** opens a bar where you type what you want: the name of an application or an address such as `eda/try`,
`dev/can`, `win/vm-usb` or `look/island`. Everything the desktop does goes through one command, `silik`, and **it
always shows the line it runs**: nothing is done out of sight.

The bar **stays loaded** after the first time: closing it hides it, and the next Super+Space only
asks it to come back. On the test bench it appears in about 50 ms instead of about 190 (`docs/STATUS.md`).

### The `silik` command

It is the brain of the system. Examples:

```
silik status                     what this system is
silik update                     updates everything (it also does so by itself every day)
silik rollback                   takes the system back to how it was before the last update (docs/ROLLBACK.md)
silik look island --accent cobalt the look and the colour
silik eda try                    the chip tools do real jobs and say whether they work
silik dev can up can0 500k       brings a CAN reader up at 500 kbit/s
silik win open programa.exe      opens a Windows program in a closed box
silik secure status              checks the security of the system
silik doctor                     says whether the machine is well and what to do
```

**`silik doctor`** is the check of the whole machine with one command. It looks, at once, at seven areas: the system
(packages, a pending restart, the last automatic update, disk, memory, failed services), security (the
summary of `silik secure status`), graphics (the card and the driver; NVIDIA, Wayland or X11), the bench (the CAN
readers with their state and bus errors, and the USB adapters SilikOS knows: whether they are yours and what you have
to run), the chip tools, Windows (Wine, the box, the virtual machine) and the network (whether the update servers are
found, the proxy). Each line says **ok**, **warn**, **bad** or **unknown** (unknown when it cannot see it, never ok)
and the exact command that fixes it. It changes nothing. It takes a few tenths of a second (0.14–0.27 s on a clean
EL 9). The list of adapters (`hardware.tsv`, 143 devices) comes from the tables of the kernel's drivers and from the
rules of the original projects, with the source on each line; none has been tried with a real device yet.

## 4. What it carries

| Area | What is there | Where it comes from |
|---|---|---|
| **Chips (EDA)** | ngspice, Xschem, Magic, KLayout, Netgen, Yosys, Icarus Verilog, Verilator, NVC (VHDL), Qucs-S, DEVSIM (device simulation); KiCad is on its way | built by us, or from EPEL |
| **Old tools** | the versions of Cadence/Synopsys made for Red Hat 6 or 7 work inside **boxes** (containers) with that old system | `silik eda create` |
| **Microcontrollers** | ARM compiler, gdb, OpenOCD, dfu-util, ST-LINK, stm32flash, esptool, SDCC (8051, STM8, Z80); the makers' IDEs are installed with `silik dev install` from your download | EPEL and built by us |
| **Bench** | CAN (PEAK, Kvaser, candleLight, CANable; CAN FD), SavvyCAN, cantools (DBC files), python-can, serial and RS485 ports, Modbus, Wireshark, PulseView and sigrok (logic analysers, 131 decoders; also the cheap 24 MHz ones with the fx2lafw firmware) | EL 9, EPEL and built by us |
| **Windows** | Wine for the programs that work on it, inside a box that does not see your files; a Windows virtual machine for the rest, to which a whole USB device can be handed (for example a Vector VN1630, which only has a driver for Windows) | built by us (Wine 11) |
| **SilikStudio** | the first key of the desktop | its own repository |

What is not open source (Cadence, Altium, the makers' IDEs, CANoe) **we never carry**: each person
installs it from their own download and with their own licence. SilikOS provides the place for it to work.

**Power and performance.** `silik power` chooses the profile: performance, balanced, saver or **automatic**, which is
the factory one: full speed when plugged in (a desktop computer always is) and balanced on battery. It uses the
tools of the base itself (tuned and tuned-ppd), so the system menu shows the same profile. Compressed
memory (zram) is offered but never turned on by itself, and the SSD is trimmed every week. For firmware there is
`silik dev ccache`: measured building the HAL of an STM32G4, building the same again goes from 8.7 s to 2.9 s, but the
first build is a quarter slower, which is why it is optional. For a laptop, `silik power` says what is being used and
what the battery has (watts, hours left, health) as the kernel gives it; `silik power check` lists the
settings that decide the consumption, with the command that changes each one; `silik power charge 80` limits the
battery's charge on the laptops that allow it; and `silik power profiles silikos` puts behind "saver" a profile of
our own that adds what the base's leaves out (USB, PCI devices, Wi-Fi). This profile does not come enabled. **Not one
watt has been measured**: none of this has been run on a real laptop yet (consumption, hours of battery).

## 5. Security and updates

Security comes in three layers: what comes from the factory, what is turned on if asked, and what SilikOS is not.

### From the factory, without doing anything

- **SELinux** on (Red Hat's), a **firewall** that closes incoming connections and **ssh** off. Nothing listens
  outside the machine: the network discovery services (rpcbind, avahi, cups-browsed) come turned off and
  `silik listen` turns them on again one by one.
- **The system updates itself every day** with everything the base publishes. It never restarts on its own: when a
  restart is needed, the desktop says so. Before each update a **snapshot** of the system is taken, and
  `silik rollback` goes back to it.
- **The SilikOS repository cannot be faked with old copies**: the system remembers the last revision it has
  seen and refuses metadata that is older, from another channel, for another architecture or unsigned. When it
  refuses some, `silik update`, `silik doctor` and the status bar say so.
- **Each tool package that goes into the ISO carries the certificate of where it was built** (GitHub's attestation:
  this repository, the `main` branch, its workflow). What does not carry one stays out.
- **USB with the screen locked**: a new device is refused (USBGuard). A keyboard or a mouse is
  accepted, so that the screen can be unlocked. What was refused stays refused until it is plugged in again or
  `silik usb allow` is said.
- **Windows programs in a box** (bubblewrap) that does not see the SSH keys or the documents. A file that has
  never been run here is asked about first, and the default answer is **isolated**: `silik win open --isolated`
  gives it a screen of its own (it cannot read the keyboard or take pictures of the other windows), outgoing
  network only, no keys, no graphics card and no sound.
- The bench's USB adapters (CAN readers, serial ports, probes) belong to **whoever sits in front of the screen**,
  with no special permissions.

### If asked

| Command | What it does | What it costs |
|---|---|---|
| `silik secure status` | some thirty lines, each **ok**, **warn**, **bad** or **unknown**, with the command that fixes it | nothing: it only looks |
| `silik secure level hardened` | 19 settings at once: the kernel locks down and only loads signed modules, memory is zeroed when it is handed out, strict IOMMU, ten wrong passwords lock the account for ten minutes, the login screen shows no users… | unsigned modules no longer load (NVIDIA built on the machine before its key is enrolled, VirtualBox), there is no hibernation, and some kernel debugging tools do not work. Each setting can be left out with `--without`, and `silik secure level default` undoes it all |
| encrypting the disk | it is ticked in the installer; afterwards `silik disk tpm enroll` binds the disk to the machine's TPM chip with a **PIN** | the PIN has to be typed at each start. If Secure Boot changes or the disk is put in another machine, the PIN no longer opens it and the passphrase or the recovery key is needed |

`docs/HARDENED.md` says what each setting costs, one by one; `docs/DISK.md`, the disk; `docs/USB.md`, USB.

### What it is not

- **It is not GrapheneOS or Qubes.** The base is not touched (it is the condition of the compatibility with Red Hat),
  so the kernel and the libraries are those of RHEL 9, hardened no further than settings allow.
- **The session is X11** (the EDA tools ask for it): two programs of the same session can see each other's
  keyboard. That is why the isolated Windows box has its own display server.
- **The programs the user starts are not confined** (neither the EDA tools nor the IDEs): what protects from them is
  the user account, not a box.
- **Nothing is impenetrable.** It has been audited twice by attacking it (13 and 14/11/2026). The first found holes
  in our code, and they were fixed. The second found no way from a normal user to root; what it found in
  the package chain and in the Windows box was fixed, and what is left open is in `docs/SECURITY.md`.

## 6. How it is made and how it is checked

Everything is in a GitHub repository. There are three ways to check that it works, from the fastest to the most real:

1. **Automatic tests** (more than 1600 right now): they check the code of `silik`, the files of the desktop, the
   colour rules…, in seconds.
2. **The test bench**: a real GNOME desktop inside a container, where the packages are installed and
   screenshots are taken. All the pictures of the colours, the icons, SavvyCAN or PulseView come from here.
3. **The real installation**: GitHub builds the **ISO** (the installation disk), installs it unattended in a virtual
   machine, starts the installed system, checks it (168 checks the last time) and saves screenshots.
   Three more tests do the same with the encrypted disk, the hardened level and the rollback.
   It is the test that counts.

Each tool we build ourselves goes through a **real trial** on a clean system: the simulator has to simulate, the
decoder has to decode, the window has to open. That it "installs" is not enough.

**House rule:** the file `docs/STATUS.md` has two tables, *verified* and *not verified*. Nothing moves to the first
without having been run for real. Assumptions are marked [A].

## 7. What is good about it and what is not

Plainly. Each point says where it was seen; "seen" means run, not thought.

### What is good about it

| What | Where it was seen |
|---|---|
| **Compatibility with Red Hat 9 intact**: the base is not touched, and a test watches it at every change | the automatic tests; the CI's installation |
| **All in one**: chips, microcontrollers, bench and Windows in one unattended installation, with the tools tried doing real work (13 of 13 EDA tools, 7 of 7 microcontroller tools) | CI, installed system in a virtual machine |
| **One command, `silik`, that shows what it does**: nothing happens out of sight, and `--dry-run` touches nothing | the whole system |
| **Less memory than the stock base**: 160 to 175 MB less than AlmaLinux Workstation, on the same machine | workflow Compare, 14/11/2026 |
| **The desktop costs no time**: the shell with our extension starts as fast as the stock one (1.39–1.45 s against 1.43–1.49 s) | workflow Compare, three runs |
| **Rolling back an update** on a real disk | CI, 70 checks |
| **Encrypted disk bound to the TPM with a PIN**: it opens with the PIN; it does not open if Secure Boot or the machine changes | CI, 90 checks, software TPM |
| **Hardened level**: the kernel refuses an unsigned module | CI, 96 checks |
| **USB blocked with the screen locked** | CI, with devices plugged into the virtual machine |
| **Isolated Windows box** that does not reach the screen, the bus or the keys of the session | CI, with SELinux on |
| **Installation without a network**: a 4.6 GB ISO that carries everything | workflow Offline ISO, 133 checks |
| **It tells the truth about itself**: `docs/STATUS.md` separates the verified from the not verified, and a missing check is a failure, not a silence | the CI itself |

### What is not good about it

| What | Why | What can be done about it |
|---|---|---|
| **It has never been started on real hardware** | everything is virtual machine and container | a week on the Ryzen and on the laptop: it is the step that is really missing |
| **Not one watt measured, not one hour of battery** | there has been no laptop | the same |
| **It reaches the desktop a little later than the base** (0.08 to 0.71 s, within the noise of the measurement) | the X11 session, which EDA needs | nothing: it is a decision taken |
| **The package repository is not published or signed** | GitHub Pages and the key are missing, and they are the owner's | until then, an installed system does not receive SilikOS's news (it does receive the base's) |
| **The isolated Windows box still sees the local network** (the router, a NAS) | the box's network is "outgoing only", not "internet only" | 4 to 6 hours of work; not started |
| **It takes more room**: 8.1 GB against 5.3 GB of the base, 1557 packages against 1231 | it carries the tools | they are packages: what is not used can be removed |
| **GNOME 40 and X11 are old** | they are those of RHEL 9 | EL 10 is studied (`docs/EL10.md`), not done |
| **The vendors' tools (Cadence, Synopsys, Altium) have not been tried** | we have no licence for any | whoever has one, `silik eda` and `docs/EDA.md` |
| **No bench adapter tried** (CAN, probes, analysers) | there has been none | the team's bench |
| **On ARM there is no Wine and none of the vendors' EDA tools** | they do not exist for ARM | `silik` says so instead of failing |
| **One maintainer and no user yet** | it is a prototype | use it |

### What it will never do

- Carry software that is not open source, licences or keys.
- Touch the base to be "more secure" or "faster": it would lose the one thing that makes it useful for EDA.
- Choose or erase a disk on its own at installation.
- Say that something works without having run it.

## 8. Where we stand (14/11/2026)

**Seen on an installed system (virtual machine with KVM, on GitHub, SELinux on):**

| Test | Result | Run |
|---|---|---|
| Unattended installation, desktop, tools, Windows, USB, audit | 168 checks ok, 0 bad | CI 43566415197 |
| Hardened level: set it, restart, check, take it off | 96 ok, 0 bad | CI 43560389589 |
| Encrypted disk + Secure Boot + TPM with PIN, nine starts | 90 ok, 0 bad | CI 43560389589 |
| Update and roll back | 70 ok, 0 bad | CI 43560389589 |
| ISO without a network, on a machine without a network card | 133 ok, 0 bad | Offline ISO 43560436638 |
| Beside the stock AlmaLinux | 160–175 MB less memory; desktop 0.08–0.71 s later | Compare 43560434143 |

Two USB checks of the first row (`silik usb allow`, and that the daemon refuses a user without sudo) had
never been run because of an error in the test script, found and fixed on 14/11: they now run and pass.

The automatic tests are more than 1600, and they pass in GitHub's CI on x86_64 and on ARM.

**Done and tried on the test bench, not yet on a real installation:**
- The status bar that says "repository refused".
- The CAN tools and the bench (SavvyCAN, cantools, PulseView…): with no real adapter.
- The times of Start and of the COMMAND bar (the test bench draws without a graphics card).

**Only the owner can do it:**
- **Turn on GitHub Pages** (Settings → Pages → Source: GitHub Actions): without it no installed system can receive
  SilikOS's news.
- **The signing key** of the packages (`docs/SIGNING.md`): now the repository comes out unsigned and no system
  accepts it.
- **Protection rules** for the `main` branch and the `v*` tags on GitHub.
- **Choose the licence** of the code.
- **Try it on hardware**: `docs/FIRST-HOUR.md`.

**Not tried anywhere:** no real hardware (not the Ryzen, not a laptop, not a real TPM, not a probe, not a
CAN adapter, not an installation USB stick).

**On ARM (aarch64):**
- The SilikOS packages are the same for the two architectures, and they are built and tested on GitHub's ARM
  machines at every change.
- The desktop, the ARM compiler, gdb, stlink and the bench tools exist for ARM; dfu-util, stm32flash,
  OpenOCD and ngspice are built with our recipes.
- What does not exist on ARM, `silik` says so instead of failing: Wine, the EDA vendors' tools, the NVIDIA
  driver.
- The ARM ISO has not been installed anywhere. On the Snapdragon X: as a Hyper-V virtual machine (not tried).
  Detail: `docs/HARDWARE.md`.

**Next steps proposed:**
- Try it from an external disk, entering through the computer's boot menu, without touching the internal disk
  (`docs/FIRST-HOUR.md` §2): the ISO already has an entry for this. It has never been done on hardware.
- Use it for a week on the Ryzen and on a laptop, and note where it fails.
- Publish and sign the repository (the owner's steps).
- Close the local network to the isolated Windows box.

## 9. Small glossary

| Word | It means |
|---|---|
| **Base** | AlmaLinux 9, the system underneath, identical to Red Hat 9 |
| **Package (RPM)** | a file that installs a program and knows how to remove it and update it |
| **EPEL** | an official repository of extra packages for Red Hat, maintained by Fedora |
| **ISO** | the file of the installation disk |
| **Kickstart** | the recipe that tells the installer what to put in, without questions |
| **CI** | the automatic tests GitHub runs at every change |
| **Box / container** | an isolated system inside the system: for old tools or programs that are not trusted |
| **Wine** | a layer that makes Windows programs work on Linux without Windows |
| **SocketCAN** | the way Linux sees a CAN reader: as a network interface, `can0` |
| **DBC** | the file that says what each frame of a CAN bus means (voltage, current, state…) |
| **uaccess** | the rule that gives a USB device to the person who sits in front of the screen |
| **Accent** | the optional colour of the desktop; by default there is none (ink) |
| **TPM** | a chip on the board that keeps a key and only gives it if the machine has started as always |
| **Secure Boot** | the firmware only starts a signed system |
| **Lockdown** | the kernel does not let itself be modified while it runs, not even by the administrator |
| **Attestation** | GitHub's certificate that says where and how a file was built |
| **USBGuard** | the service that decides which USB devices are accepted |
