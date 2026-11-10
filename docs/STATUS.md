# SilikOS — what has been run (09-10/11/2026)

Build machine: a cloud container (Ubuntu 24.04, kernel 6.18, 4 cores, no KVM, Docker; network through a proxy to
Docker Hub, repo.almalinux.org, dl.fedoraproject.org and vault.centos.org).

## Verified here

| What | How | Result |
|---|---|---|
| The six packages build | `tools/build_rpms.sh` (rpmbuild 4.18, noarch `.el9`) | 6 RPMs + repodata |
| Every dependency name exists | `tools/check_deps.sh` in an `almalinux:9` container with BaseOS, AppStream, CRB, extras, EPEL 9 | all Requires and Recommends found (`winetricks` was not in EPEL 9: dropped) |
| The whole install resolves | `dnf install --assumeno build/repo/*.rpm` there | 752 packages, 1.2 GB, no conflict reported (the resolver does not see file conflicts: the next row found one) |
| The desktop packages install for real | `dnf install` / `rpm -U` of `silik-tools`, `silik-command`, `silikos-branding`, `silikos-desktop` in an AlmaLinux 9.8 container with gnome-shell 40.10 | installed, after a fix: `silikos-desktop` shipped `/etc/dconf/profile/user`, which the `dconf` package owns on EL 9 (the transaction was refused; the ISO installation would have stopped there) |
| `silik`, the COMMAND bar and the branding install with their real dependencies | `dnf install` there (gtk3 3.24.31, python3-gobject 3.40.1, Python 3.9.25) | installed; `silik status`, `--dry-run` actions and `silik-command --list` run |
| The COMMAND bar draws on EL9's GTK | Xvfb in that container, Catalan, Cascadia Mono | window, list, twin line, key footer as designed (also on Ubuntu's GTK, light / dark, EN / CA) |
| Unit tests | `python3 -m unittest discover -s tests` on Python 3.12 and 3.9 | 27 / 27 on both |
| Python 3.9 syntax | `vermin -t=3.9-` on `silik` and `silik-command` | no newer feature |
| The kickstart parses | `ksvalidator -v RHEL9` (pykickstart) | valid |
| An EL6 userland runs on a current kernel | `centos:6` container: glibc 2.12, python 2.6, yum, kernel vsyscall page execute-only (`xonly`) | runs |
| `silik eda setup` on an EL6 box | the real command against a `centos:6` container (Docker's CLI standing in for podman): vault repositories, `yum install` | 36 of 36 packages (csh, ksh, xterm, openmotif, libXp x86_64 + i686, glibc.i686, redhat-lsb-core, fonts...) |
| An X11 program of the EL6 box shows on the host's display | `silik eda run x6 -- xterm ...` against an Xvfb display, screenshot | xterm of CentOS 6.10 drawn |
| The installer ISO builds | `tools/build_iso.sh`: AlmaLinux 9.8 boot ISO + kickstart + repository, 1.5 GB, 1 min | `inst.ks=` in the ISO's and the EFI image's `grub.cfg`; entries read "Install SilikOS 0.1" |
| The ISO boots under UEFI | QEMU (TCG) + OVMF: GRUB menu, default entry, kernel 5.14.0-687.5.3.el9_8 starts | boots (QEMU's default CPU model lacks x86-64-v2, which EL9 needs: use `-cpu max`; real CPUs since 2009 have it) |
| The installer takes the kickstart and finds the package sources | the ISO's kernel + installer in QEMU (TCG, `-cpu max`), graphical, screenshots | summary screen: network connected by itself, Installation Source = repo.almalinux.org, Software Selection = Workstation (the six SilikOS packages from the ISO's repository and EPEL resolve); disk, user and time zone left to the person, as designed |
| The installer says SilikOS | the rebuilt ISO (label `SilikOS-9-8-x86_64`, `images/product.img`) in QEMU: UEFI menu, welcome and summary screens, screenshots | "Install SilikOS 9.8", "WELCOME TO SILIKOS 9.8", "SILIKOS 9.8 INSTALLATION", the SilikOS sidebar and logo; network, source and Workstation selection still resolve with the SilikOS product configuration |
| The installed system's names | `silikos-branding` 0.2.0 on AlmaLinux 9.8 (container, `dnf install`) | `PRETTY_NAME="SilikOS 9.8"`, boot entries "SilikOS (kernel) 9.8", `ID` / `VERSION_ID` / `/etc/redhat-release` untouched, `dnf` works; a reinstall of the base's release package re-applies the names (trigger); `identity base` / `silikos` switch; removal restores the base's file and boot splash theme |
| The installer in the Silik look | the ISO with `installer/product` (stylesheet, Cascadia Mono, a fontconfig alias) in QEMU, welcome and summary screens, screenshots | ink sidebar with the mark, every text in Cascadia Mono, inverse-video selection, ink "Continue", no blue |
| The Silik layout on GNOME Shell | `silikos-desktop` 0.5.0 in an AlmaLinux 9.8 container run with systemd: Xvfb, `gsd-xsettings`, `gnome-shell --x11` 40.10 (software rendering), driven with xdotool, screenshots | the session opens on the desktop; title bar = mark (the Start key) + command line (a click opens the COMMAND bar) + clock + system menu; status bar with the last command `silik` ran and workspace / base / kernel / host; EN and CA strings; 0 `JS ERROR` in the shell's log |
| The rail as the task bar | same session | favourites digit first with their icon, an ink edge on running ones, the focused one in inverse video; an application with two windows (two Files windows) lists both below its key and a click on one raises that window; other open applications under "open"; workspace cells 1-4; Super+3 raises the rail's key 3 |
| Start | same session: a click on the mark and the Super key | a pane hanging from the mark: categories (only those that have applications), applications as rows with their description, a filter as you type, Up / Down, Tab changes category, Esc closes, the mark in inverse video while open |
| The windows view on paper | the rail's "Windows" key there; a search typed in it | windows spread on the sheet with ink captions, workspace strip, search results as paper rows with the choice in inverse video; the title bar stays ink |
| One family of icons | `silikos-desktop` 0.6.0, same session: rail, Start, Alt+Tab, the windows view, Files; two test entries without a line icon | an application shows its own line icon, or the generic one of its kind (the terminal for xterm), or its initial in an ink frame (the test entries); they follow inverse video; Files shows the SilikOS folders and file types (`tools/gen_icons.py`, 49 icons over Adwaita) |
| The background | `tools/gen_wallpaper.py`, rendered by librsvg on the host and by the shell there | a wafer map whose filled dies draw the mark, inside a drawing-sheet frame; light and dark twins |
| The GTK theme without Adwaita's blue | `/usr/libexec/silikos/gtk-theme` there (GTK 3.24.31): the theme is made from libgtk-3's own stylesheet; `gtk3-widget-factory`, Files, gedit, screenshots | 0 occurrences of the accent colour in the result; checks, radios, switches, scales, progress bars, tabs, focus rings and selection are ink; ink title bars on client-side (Files, gedit) and on window-manager decorated windows (xterm) |
| The shell theme | `/usr/libexec/silikos/shell-theme` there, user-theme extension, screenshots | ink panel and menus in Cascadia Mono, square menus without the pointer, calendar with today in inverse video, the base's logo gone from the panel |

Found by booting the ISO and fixed: the installer did not bring the network up by itself, so the package sources
failed until it was turned on by hand (the kickstart now activates a wired connection).

Two bugs were found by running `silik eda` for real and fixed: the vault repository file was written empty
(`podman exec` without `-i`), and a missing optional helper (`xhost`) stopped the command.

## Not verified (and why)

| What | Why | Who can |
|---|---|---|
| A complete installation from the ISO (752 packages) and the first boot of the installed system | no KVM here: emulated it would take many hours | any PC with virtualisation, or the Ryzen machine itself |
| BIOS (non-UEFI) boot of the ISO | not tried | a VM |
| The boot splash (plymouth theme `silikos`) on a screen, the About logo, the login logo, the firmware's boot entry name | set and listed, not seen: no real boot here | after the first installation |
| Places that still name the base | by design: the package source URL in the installer, repository names in `dnf`, `/etc/redhat-release`, `ID=` | — |
| The desktop in a real login session (GDM, the Super+Space key binding through gnome-settings-daemon, X11 as the default, the login logo, a hardware-accelerated shell, HiDPI scaling of the rail and status bar, several monitors, a full-screen window) | the shell was run by hand in a container, without GDM or a session manager; one 1440x900 screen, scale 1 | after the first installation |
| The login screen in the Silik look | not done: GDM draws with the shell's built-in stylesheet (a file of the `gnome-shell` package), only its logo is set | — |
| Icons inside applications other than Files (toolbars use Adwaita's line icons; a program that draws its own colour pictures keeps them); the file-type icons other than folder and text sheet on screen (only rendered to a sheet with librsvg) | not looked at | after the first installation |
| ES strings of the shell extension on screen; Start with a full application set (the container has seven) and its scrolling; the Super key opening Start under a real session (here it was sent with xdotool); the overview's application grid beyond two icons; GTK 4 / Qt applications (they do not read the GTK 3 theme) | not run | after the first installation |
| The clock's colon | Cascadia Mono has no U+2236: without another font it drew as a box in the container; with `dejavu-sans-fonts` (now required) it draws | — |
| `silik eda create` with podman itself (`--userns keep-id`, the home folder and X authority mounts), `import-vm` (libguestfs) | Docker stood in for podman here; no libguestfs | the Ryzen machine |
| Cadence / Synopsys tools | no installers or licences | the owner |
| Wine, the Windows virtual machine, RDP RemoteApp, Altium | no KVM, no Windows, no licences | the owner |
| NVIDIA driver (RTX 3050), hybrid graphics, Wi-Fi, suspend | hardware | the owner |
| The passt port forward of `silik win vm create`, `virt-install` option names | not run | the Ryzen machine |
| ARM | no ARM machine; see `docs/HARDWARE.md` | later |
