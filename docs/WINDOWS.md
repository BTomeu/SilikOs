# Windows programs on SilikOS

| Route | For | Commands |
|---|---|---|
| Wine, in a sandbox | programs Wine runs (many utilities, older tools) | a double-click, or `silik win open FILE`; `silik win run PREFIX -- prog.exe`, `silik win install PREFIX setup.exe` |
| Windows virtual machine | programs Wine does not run | `silik win vm create --iso Win11.iso`, `silik win vm start`, `silik win vm app --exe 'C:\...\X2.EXE' --user U` |

## A double-click

A double-click on an `.exe`, `.msi` or `.lnk` in Files runs `silik win open FILE`. Nothing else is needed: the first
time, `silik` makes the Wine prefix `default` (the user never has to know what a prefix is), the folder `~/Windows`
and the sandbox, and prints every command it runs, as it does for everything.

| File | What runs in the prefix |
|---|---|
| `.exe` | `wine FILE ARGS` |
| `.msi` | `wine msiexec /i FILE ARGS` (FILE as a Windows path: `W:\...`, `Z:\...`) |
| `.bat`, `.cmd` | `wine cmd /c FILE ARGS` |
| `.lnk` | `wine start FILE` (Wine follows the shortcut; `silik` does not wait for its program) |

- **Installers and portable programs are not told apart.** Whatever is opened runs in the prefix `default`; an
  installer installs into it, a portable program runs from where it is. To keep a program apart from the rest (a
  broken install then touches nothing else): `silik win open --prefix NAME setup.exe`, or
  `silik win install NAME setup.exe`. Prefixes are folders under `~/.local/share/silikos/wine/`; `silik win rm NAME`
  removes one, with its programs.
- Without a terminal (a double-click), a console program or a batch file gets Wine's console window, as it gets one
  on Windows; from a terminal its output stays in the terminal.
- A double-click on a `.bat` or `.cmd` opens the text editor, as it does for a shell script; "Open With" offers
  "Windows program", and `silik win open FILE.bat` runs it.
- How the double-click gets there: the package `silik-win` has the desktop entry `org.silikvolt.Win.desktop`
  (`Exec=silik win open %f`, not shown in the applications list) and `/etc/xdg/mimeapps.list`, which makes it the
  default for the Windows file types. That file is in the layer the specification keeps for add-ons
  (`XDG_CONFIG_DIRS`): it is read before the distribution's own list in `/usr/share/applications` (where EL 9 gives
  `.exe` to the archive manager) and after the user's `~/.config/mimeapps.list`; no package of the base or of EPEL
  owns it. EL 9's file-type database (shared-mime-info 2.1) has no type for `.lnk`, and calls `.bat` and `.cmd` plain
  text: `silik-win` adds the two types (`/usr/share/mime/packages/silik-win.xml`).
- When a program cannot start (Wine is not installed, the sandbox is busy: below), a double-click has no terminal to
  say so: `silik` also sends a desktop notification (`notify-send`).
- The COMMAND bar takes a path to a Windows file the same way (twin line `silik win open /path/setup.exe`).

## Installed programs are applications

An installer makes its start-menu shortcuts; Wine's `winemenubuilder` writes a desktop entry and icons for each. After
every `open`, `run` and `install`, `silik win sync` (also a command of its own) turns them into applications of this
desktop:

- an entry per program in `~/.local/share/applications/silik-win/PREFIX/`, with the program's Windows name, its
  icon (copied to `~/.local/share/icons/hicolor/…/apps/silik-win-PREFIX-…`) and the command
  `silik win run PREFIX -- 'C:\…\Program.lnk'`: it starts through `silik`, in the sandbox, like everything else;
- `StartupWMClass` is kept (Wine gives a window the name of its `.exe` as its class), so that a running program is
  the same item as its entry in the rail and in the applications list;
- entries of uninstalled programs (their shortcut is gone) and of removed prefixes are removed, with their icons;
- entries Wine wrote straight into `~/.local/share/applications/wine/` (a program run with `--no-sandbox`, or Wine
  used by hand on one of these prefixes) are moved to their prefix and treated the same.

`silik win apps [--json]` lists them. In the COMMAND bar each is an address, `win/<program>`, with the same twin
command line; `win/PREFIX program.exe` still runs a command in a prefix.

What comes out of a prefix is not trusted: the command of an entry is always `silik win run PREFIX -- …`, an icon is
copied only if it is a plain file, a window class is kept only if it is a Windows program's (`….exe`). A program does
choose its own name and icon in the applications list, as on Windows.

## The sandbox

With bubblewrap installed (`silik-win` requires it), Wine never runs with the user's whole account. What a Windows
program sees:

| | |
|---|---|
| the system (`/usr`, `/etc`) | read-only |
| its prefix (drive `C:`, and its own home folder `PREFIX/home`) | read-write |
| `~/Windows`, made on first use: drive `W:` | read-write. This is where documents for and from Windows programs go |
| `~/Downloads` (the folder `XDG_DOWNLOAD_DIR` names) | read-only: installers come from there. `SILIK_WIN_SHOW` (a colon list, may be empty) replaces it |
| the folder of an opened file that is none of the above | read-only, while the prefix's programs run. The file alone if it is directly in the home folder, in a hidden folder, or in a system folder |
| **the rest of the home folder** (SSH keys, design data, licence files, browser profiles…) | **not there**: the paths do not exist in the sandbox |
| `/tmp`, `$XDG_RUNTIME_DIR` | its own, empty at start |
| processes | its own only (a process namespace) |
| environment | `HOME`, `PATH`, `USER`, the locale, `DISPLAY`, the Wine switches; nothing else (no tokens). The session bus address is set to one that does not exist: left unset, a library starts a bus of its own inside (below) |
| the X11 display, the sound sockets (PulseAudio, PipeWire), the GPU devices (`/dev/dri`, `/dev/nvidia*`) | passed |
| network | on; `--no-net` gives the sandbox no network |

How it is built, and why it is one sandbox per prefix and not one per program: the programs of a prefix must talk
to one `wineserver`; the wineserver knows them by process id, and it is the wineserver that opens their files. So a
prefix has one sandbox while its programs run. `bwrap` starts it with the prefix's wineserver as its first program
(new user, process, IPC, host-name and control-group namespaces, the mounts above, capabilities dropped), and each
program enters it with `nsenter`, then `setpriv --no-new-privs --pdeathsig KILL`, `setsid` (it cannot type into the
terminal it was started from) and `env` (its whole environment). When the last program ends the wineserver leaves
(Wine's default is 3 s later [A]; the Ubuntu build used here leaves at once) and the sandbox with it. The two lines
are printed, and they are the real ones:

```
$ env -i /usr/bin/bwrap --unshare-user --unshare-pid --unshare-ipc --unshare-uts --unshare-cgroup-try --new-session --cap-drop ALL --info-fd 4 --ro-bind /usr /usr … --bind ~/.local/share/silikos/wine/default … --bind ~/Windows ~/Windows --ro-bind ~/Downloads ~/Downloads --remount-ro / --chdir … -- env HOME=… WINEPREFIX=… wineserver --foreground 4>$XDG_RUNTIME_DIR/silik-win/default/session.json &
$ env -i nsenter --preserve-credentials -t 16971 -U -m -p -i -u -C -- setpriv --no-new-privs --pdeathsig KILL setsid --wait env -C ~/Downloads DISPLAY=:0 HOME=… WINEDEBUG=-all WINEPREFIX=… wine ~/Downloads/setup.exe
```

Consequences to know:

- **What a sandbox shows is fixed when it starts.** Opening a file from a folder it does not show (not `~/Windows`,
  not `~/Downloads`) works when no program of that prefix is running: the new sandbox shows that folder. While
  programs of the prefix are running it does not: `silik` says so (exit code 75, and a notification) and asks to
  close them (`silik win stop PREFIX` ends them all) or to put the file in `~/Windows`. The same for `--no-net`
  against a running sandbox that has the network, and the other way round.
- The folder is shown and not copied: an installer finds the files next to it, nothing is duplicated. The price is
  that the whole folder is readable by the prefix's programs for that time.
- `--no-sandbox` runs Wine with the user's whole account, and says so in capitals. Wine then writes its own menu
  files into the home folder (`silik win sync` adopts the entries). A prefix runs either in the sandbox or outside
  it, not both at once.
- Without `bwrap`, `silik` says in one line that the programs run without the sandbox, and runs them.
- The status bar's last command is the short form: `nsenter ... WINEDEBUG=-all WINEPREFIX=… wine setup.exe`.

**What the sandbox does not do:**

- **The display, and through it the files.** X11 does not separate its clients: a program with the display can read
  the keyboard and the screen and send keys to other windows, e.g. type a command into an open terminal. So under
  X11 (the desktop's session) the sandbox keeps honest programs from reaching your files by mistake, but it does not
  stop a hostile one: for a program you do not trust, the Windows VM (`silik win vm`).
- Sound: a program can play and record.
- Network (unless `--no-net`): it is this machine's network, with what listens on `localhost`.
- The programs of one prefix are not protected from each other (they can read each other's memory through the
  wineserver). For a program that must not reach the others, or must have no network at all: a prefix of its own.
- The kernel: there is no system-call filter. A program can make its own namespaces inside the sandbox; a kernel
  bug is as reachable as for any program of the user.
- What is visible read-only can be read: `/etc` (host name, user names, what any user can read there), device
  information in `/sys`, `~/Downloads`.
- `root`: the sandbox is made for an ordinary user. Do not run Windows programs as root.

A sandbox lives as long as any process of it. Wine's server leaves 3 s after its last program, and the sandbox with it.
Found on an installed system (11/11/2026): with SDL2 installed (Qucs-S brings it; Wine loads it when it is there), a
library inside found no session bus and started one (`dbus-launch --autolaunch`), which never ends: every Windows
program left a sandbox and two processes behind. The sandbox is now told that there is no bus
(`DBUS_SESSION_BUS_ADDRESS` names a socket that does not exist), and `silik win stop` and the next start of a prefix
end whatever an earlier sandbox of it left (`$ kill -KILL ...`, only processes of that sandbox's process namespace
that have the prefix's runtime folder mounted).

## Limits

- **Wine is our own build**, `silik-wine` (Wine 11.0 from WineHQ's source, under `/opt/silik-wine`, built by the
  workflow Wine and carried by the ISO). EPEL 9's Wine is not installable on EL 9.8 (seen 10/11/2026:
  `wine-core-8.0-1.el9` needs `mesa-libOSMesa`, which EL 9.8's Mesa 25 no longer builds).
- EL 9's SELinux policy does not let a user's program run Wine's kind of code (`selinuxuser_execmod` is off):
  `silik-win` carries a rule (`silikos_wine.cil`) that gives Wine's three programs the policy's own Wine domain
  (`wine_t`). The boolean stays off for everything else. **`wine_t` is not a confinement**: in the base's policy it
  is an unconfined domain (read with `seinfo -t wine_t -x` on EL 9.8 by the audit of 13/11/2026: `unconfined_domain_type`,
  and among its attributes the right to load policy and to set enforcing). It is there so that Wine's kind of code
  runs at all. What holds a Windows program is bubblewrap (no capabilities, no new privileges, its own namespaces);
  with `--no-sandbox`, or without bubblewrap installed, nothing does.
- **`--no-net` takes the network away and nothing else**: the program still has this session's X11 display, and
  with it the keyboard and the other windows (above). It is not how to run a program you do not trust.
- **A double click runs it.** `.exe`, `.msi`, `.lnk` and `.bat` files open with `silik win open`, without a
  question: a file that arrived by mail is one click from running with the reach described above. Whether to ask
  first for a file in `~/Downloads` is the owner's to decide (the audit's finding B2).
- **.NET and HTML: Wine Mono and Wine Gecko are packages of the system** (`silik-wine-mono`, `silik-wine-gecko`:
  upstream's binary archives unpacked under `/opt/silik-wine/share/wine`, `wine/silik-wine-addons.spec`). WineHQ's
  Wine otherwise offers to download them with a dialog: "Wine Mono Installer" the first time a prefix is made (behind
  a double-click it stopped the first program: seen on the installed system and in a container), "Wine Gecko
  Installer" when a program first asks for an HTML document (seen in a container: the program waits behind it). With
  the packages Wine finds both, asks nothing, downloads nothing and copies nothing into the prefix. On a system
  without one of them `silik` sets a prefix up with that library left out (`WINEDLLOVERRIDES=mscoree=` / `mshtml=`),
  so that the set-up never waits; a program that then needs it gets Wine's dialog.
- Kernel-mode drivers do not exist under Wine [A: Wine's design, none tried here]: anti-cheat and copy-protection
  (DRM) drivers, and the drivers of hardware keys. Programs that insist on them need the virtual machine.
- USB dongles (licence keys), serial ports, programmers and debug probes: the sandbox passes no USB or serial
  device, and Wine has no Windows driver for them. Use the virtual machine with the device passed to it
  [A: not tried].
- Printing from a sandboxed program: the print service's socket is not passed [A: not tried].
- A window's process id as the display knows it (`_NET_WM_PID`) is the number inside the sandbox.
- Programs Wine does not run at all (Altium is expected to be one): the virtual machine.

## The virtual machine

- A user session KVM guest (UEFI, TPM 2.0 emulated, 8 GB / 4 CPUs / 80 GB by default) with the guest's RDP port
  forwarded to `127.0.0.1:3389`. Enable Remote Desktop in Windows; `silik win vm app` then opens one program as a
  window of this desktop (RDP RemoteApp, FreeRDP), with the shared folder `~/Windows` as a drive (never the whole
  home folder: a program in the VM could otherwise write ~/.bashrc or an autostart entry), the clipboard shared.
- Its screen until Remote Desktop is on: VNC (virt-viewer) with a VGA card. EL 9's qemu-kvm has no SPICE and no QXL
  (seen on AlmaLinux 9.8: `qemu-kvm -spice` is an invalid option, no QXL device); the first command line asked for
  both and would have been refused (fixed 12/11/2026; the new one not run either: no KVM here).
- On ARM (aarch64): Windows 11 for ARM, `virt` machine, AAVMF (edk2-aarch64), the installation disc on USB, disk and
  network virtio with virtio-win's ARM64 drivers (`--drivers virtio-win.iso`, "Load driver" in Setup), a RAM
  framebuffer; without `/dev/kvm` (a VM in Hyper-V on a Windows on ARM laptop) it says why it cannot.
- `silik win routes [--json]` says which of these ways the machine has, from what it sees (Wine, KVM, virt-install;
  on ARM also the page size, an x86_64 emulator, a Hyper-V host). There is no Wine for ARM in SilikOS: the route there
  is Windows 11 for ARM in the virtual machine, which runs x86 programs through Windows' own emulation (PROPOSAL,
  with the other routes and what the vendors say: `docs/ARM.md`).
- Windows and the programs need their own licences.

## Altium Designer

Expected [A: from public reports, not tried here]: it does not run usably under Wine (.NET, DirectX, licensing
service). Plan: try it in a Wine prefix once (`silik win install altium Setup.exe`), then use the virtual machine. In
the virtual machine the 2D editors work without a GPU; the 3D view needs DirectX acceleration, which a KVM guest only
has with a GPU passed through to it. On the Ryzen 7 5800HS + RTX 3050 laptop that would mean giving the RTX 3050 to
the guest while the desktop stays on the Radeon graphics: possible in principle, laptop-specific in practice, not
tried.

## Run so far (10/11/2026)

Run, on the build machine (Ubuntu 24.04, kernel 6.18, Wine 9.0, as an ordinary user) with programs compiled for the
purpose (a console program, a window, an installer that makes a start-menu shortcut):

- the first `silik win open hello.exe` makes the prefix and the sandbox and runs the program (7 s the first time;
  the prefix is 690 MB with that Wine); a window draws (screenshot); `.bat`, `.cmd`, `.lnk` run; `.msi` reaches
  `msiexec` (with a file that is not a package: no real package was installed);
- inside: the home folder's `.ssh` and `Documents` are not there, `~/Downloads` and the system refuse writes,
  `W:\` takes them; no variable of the outside (a test token, the session bus) is in the environment; no
  capabilities, no new privileges; with `--no-net` only `lo`;
- a display that asks for its key, with the key file in the home folder and under the runtime folder (where GDM
  puts it);
- the same sandbox with EL 9's own `bwrap` 0.6.3, `nsenter` and `setpriv` 2.37.4 binaries;
- two programs of a prefix at once; a file from another folder while the sandbox runs is refused with exit code 75
  and opens once it has ended; `--no-sandbox`; `bwrap` absent; `stop`; `rm`;
- the installer's shortcut becomes an application (`silik win sync`), its window's class (`xprop`) is its entry's
  `StartupWMClass`, uninstalling removes it;
- on AlmaLinux 9.8 (container): the packages install (`dnf install`), `.exe` / `.msi` / `.lnk` have
  `org.silikvolt.Win.desktop` as their default (`gio mime`, `xdg-mime query default`), and a double-click in Files
  (nautilus 40.2) on an `.exe`, on one with the executable bit, and on an `.msi` runs `silik win open FILE`; GLib
  launches a synced entry with the right arguments.

Run on an installed SilikOS (the CI's virtual machine, run 42864994059, 10/11/2026: kernel 5.14, SELinux enforcing,
bubblewrap 0.6.3, `silik-wine` 11.0), from the test user's session: the first `silik win open hello.exe` sets the
prefix up and runs the program in its sandbox (exit 0); the program writes to `W:\` and does not see a file of
`~/.ssh`; its SELinux domain is `wine_t`.

Run in the test container (11/11/2026, silik-wine 11.0, sandboxed): a 32-bit program; an installer that makes a
start-menu shortcut (its program is then `win/silik-test` in `silik win apps`); a Windows Installer package built
with wixl (`silik win open silik.msi` installs it). The same three on an installed SilikOS (the CI's virtual machine, run
42968357962): all pass, and the installed program, typed as `win/silik-test` in the COMMAND bar, opens its window and
is in the rail under its name.

Not run: the rail and the applications list of the real shell with a Wine window; sound, a GPU, NVIDIA devices, a
Wayland session; a real `.msi`; a 32-bit program on the installed system (one ran in the Wine workflow's container);
a real third-party installer; a real .NET application (only a program compiled for the test); the virtual machine
route, Altium.
