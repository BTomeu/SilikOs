# Windows programs on SilikOS

| Route | For | Commands |
|---|---|---|
| Wine, in a sandbox | programs Wine runs (many utilities, older tools) | a double-click, or `silik win open FILE`; `silik win run PREFIX -- prog.exe`, `silik win install PREFIX setup.exe` |
| Wine, isolated | the same programs, when you do not trust one with your session: a display of its own | the first answer of the question a new file gets; `silik win open --isolated FILE`; `silik win isolate PREFIX` |
| Windows virtual machine | programs Wine does not run | `silik win vm create --iso Win11.iso`, `silik win vm start`, `silik win vm app --exe 'C:\...\X2.EXE' --user U` |

## A double-click

A double-click on an `.exe`, `.msi` or `.lnk` in Files runs `silik win open FILE`. A file that was not run here
before is asked about first (below); nothing else is needed: the first time, `silik` makes the Wine prefix `default`
(the user never has to know what a prefix is; `isolated` for a program run isolated), the folder `~/Windows` and the
sandbox, and prints every command it runs, as it does for everything.

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

## The first time a file runs

A file that arrived a minute ago must not be one click from this session's keyboard and screen. The first time a
file is opened (`silik win open`, `silik win install`, `silik win run PREFIX -- /a/file/of/this/system`) the owner
is asked, in a window after a double-click (`/usr/libexec/silik-win-ask`: GTK 3, the COMMAND bar's paper and ink),
as text in a terminal; English, Catalan, Spanish:

```
silik: setup-tool-1.2.exe has not been run here before
  File       /home/u/Downloads/setup-tool-1.2.exe (12.3 MB)
  From       https://downloads.example.org/tools/setup-tool-1.2.exe
  SHA-256    175f04f8ced6277b9d20a639f11c6ae544c411db84cdd43f419cc5398d7f275b
  Signature  carries a signature block (not checked: nothing on this system checks it)
  [1] Run isolated (default)
  [2] Run in the normal box
  [3] Cancel
```

- **From** is the address a download tool wrote on the file (the attribute `user.xdg.origin.url`: `curl --xattr`,
  `wget --xattr`; Firefox writes none on Linux [A: not run here]), else whether it lies in the Downloads folder. It
  is the sender's word.
- **Signature** says whether the program carries an Authenticode block, never that it is good: nothing in the base
  verifies one, and a publisher's name read out of a block nobody verified would be the attacker's to choose, so no
  name is shown. The SHA-256 is what can be compared with the publisher's page.
- The answer is kept, by the file's SHA-256, in `~/.local/share/silikos/win-approved` (mode 0600; a line a file:
  delete a line to be asked again). The same file opens the same way from then on without a question; a changed
  file is a new file.
- No question: `--yes` (scripts; not kept as an answer); `--isolated`, or a prefix marked isolated (the careful
  way is already chosen); `--no-sandbox` (typed, and said in capitals); a file inside a prefix (installed there);
  a program of the system (`/usr`, and the folder of a Wine installed under `/opt`: Wine Mono's compiler is there).
- With no terminal and no window to ask in, the file does not run (exit code 2). When the program cannot run
  isolated here (no Xephyr, no display), the question says why, offers the normal box and Cancel, and Cancel is
  the default.

`silik dev install FILE` (ST's and TI's installers; ST's runs as root) asks the same way before it runs anything:
the command and whose rights it gets, the file and the installer inside an archive with their SHA-256, where the
file says it came from; `--yes` for scripts, and without a terminal and without `--yes` nothing runs.

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
choose its own name and icon in the applications list, as on Windows; the name of a program of an isolated prefix
ends with "(isolated)" ("(aïllat)", "(aislado)"), so that it cannot pass for another application of this desktop.

## The sandbox

With bubblewrap installed (`silik-win` requires it), Wine never runs with the user's whole account. What a Windows
program sees:

| | |
|---|---|
| the system (`/usr`, `/etc`) | read-only |
| its prefix (drive `C:`, and its own home folder `PREFIX/home`) | read-write |
| `~/Windows`, made on first use: drive `W:` | read-write. This is where documents for and from Windows programs go. A prefix of isolated programs has its own, `~/Windows/PREFIX`, and does not see the rest (below) |
| `~/Downloads` (the folder `XDG_DOWNLOAD_DIR` names) | read-only: installers come from there. `SILIK_WIN_SHOW` (a colon list, may be empty) replaces it |
| the folder of an opened file that is none of the above | read-only, while the prefix's programs run. The file alone if it is directly in the home folder, in a hidden folder, or in a system folder |
| **the rest of the home folder** (SSH keys, design data, licence files, browser profiles…) | **not there**: the paths do not exist in the sandbox |
| `/tmp`, `$XDG_RUNTIME_DIR` | its own, empty at start |
| processes | its own only (a process namespace) |
| environment | `HOME`, `PATH`, `USER`, the locale, `DISPLAY`, the Wine switches; nothing else (no tokens). The session bus address is set to one that does not exist: left unset, a library starts a bus of its own inside (below) |
| the X11 display, the sound sockets (PulseAudio, PipeWire), the GPU devices (`/dev/dri`, `/dev/nvidia*`) | passed (isolated: none of them; below) |
| network | on; `--no-net` gives the sandbox no network |
| the kernel's session keyring | a new, empty one (the session's, with what it links, is not inherited) |
| system calls | a filter of the kernel (seccomp) refuses the ones a Windows program has no use for: the kernel's keyrings (`keyctl`, `add_key`, `request_key`), namespaces of its own (`unshare`, `clone` with a namespace flag, `clone3`), mounting, `bpf`, `perf_event_open`, `userfaultfd`, `io_uring`, `open_by_handle_at`, typing into a terminal (`ioctl TIOCSTI`) |

How it is built, and why it is one sandbox per prefix and not one per program: the programs of a prefix must talk
to one `wineserver`; the wineserver knows them by process id, and it is the wineserver that opens their files. So a
prefix has one sandbox while its programs run. `bwrap` starts it with the prefix's wineserver as its first program
(new user, process, IPC, host-name and control-group namespaces, the mounts above, capabilities dropped, the
system-call filter read from a file: `--seccomp`), and each program enters it with `nsenter`, then
`setpriv --no-new-privs --pdeathsig KILL`, `setsid` (it cannot type into the terminal it was started from) and `env`
(its whole environment). A program that enters takes a new session keyring and loads the same filter just before
`nsenter` runs (a filter stays for a program and all it starts; `setns`, which `nsenter` needs, is not refused: with
`unshare` and the namespace flags gone, a program of the box has no namespace to enter but its own). When the last program ends the wineserver leaves
(Wine's default is 3 s later [A]; the Ubuntu build used here leaves at once) and the sandbox with it. The two lines
are printed, and they are the real ones:

```
$ env -i /usr/bin/bwrap --unshare-user --unshare-pid --unshare-ipc --unshare-uts --unshare-cgroup-try --new-session --cap-drop ALL --info-fd 4 --seccomp 5 --ro-bind /usr /usr … --bind ~/.local/share/silikos/wine/default … --bind ~/Windows ~/Windows --ro-bind ~/Downloads ~/Downloads --remount-ro / --chdir … -- env HOME=… WINEPREFIX=… wineserver --foreground 4>$XDG_RUNTIME_DIR/silik-win/default/session.json 5<$XDG_RUNTIME_DIR/silik-win/default/seccomp.bpf &
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
- Without `bwrap`, `silik` says in one line that the programs run without the sandbox, and runs them; not those of
  a prefix of isolated programs, which then do not run at all (exit code 69), and `--no-sandbox` is refused for them
  the same way.
- `silik win stop PREFIX` asks the prefix's wineserver to end its programs (`wineserver -k`, for at most 10 s); if
  the box is still there after that (a program can stop its own wineserver, which then never answers), it ends the
  box's first process (`$ kill -KILL PID`), and the kernel ends every process of the box with it.
- The status bar's last command is the short form: `nsenter ... WINEDEBUG=-all WINEPREFIX=… wine setup.exe`.

## Isolated: a display of its own

X11 does not separate its clients: a program with the session's display can read every key typed in any window,
take pictures of the screen, read the clipboard and type into other windows, a terminal included. The normal box
passes that display. `--isolated` does not:

| | the normal box | isolated |
|---|---|---|
| display | the session's X server | an X server of its own: Xephyr, one window of the session titled "SilikOS: isolated Windows programs (PREFIX)", which is the program's whole screen. The box is given that server's socket and key, nothing of the session's |
| network namespace | the session's | its own, always. (The session's X server also listens on an abstract socket, which has no file to hide: a box that shares the network namespace reaches it, and EL 9's login lets every program of the user in without the key) |
| network | this machine's, `localhost` included | through `pasta` (the package passt): out to the network as the user's own connections, by the interface of the default route and no other (`--outbound-if4`, `--outbound-if6`); nothing that listens on this machine is reachable, by `localhost`, by its own address or by the address of another of its networks (a bridge of virtual machines or containers, a second card); no port of the box is opened. Without passt, or with `--no-net`: none |
| keyboard, screen, clipboard of the session | readable, writable | not reachable. No clipboard bridge: text does not cross; files do, through the prefix's own folder |
| the shared folder, drive `W:` | `~/Windows` | `~/Windows/PREFIX` (`~/Windows/isolated`), its own: the rest of `~/Windows` is not there. A file that lies in it, or in the prefix, runs isolated in that prefix whatever was answered for it before, never in a prefix of the normal box and never with `--no-sandbox` |
| the terminal the command was typed in | passed (a console program keeps it) | not passed: pipes that `silik` copies while the command runs (output and exit code; what is typed, for a console program), closed when it ends |
| sound (PulseAudio, PipeWire) | passed | not passed; `--sound` passes it (a program can then record) |
| GPU devices | passed | not passed: OpenGL is drawn in software (Mesa llvmpipe) |
| the Downloads folder | shown, read-only | not shown: the opened file alone (its folder when it lies in one of its own) |
| the session bus, the keyring daemon, the COMMAND bar's socket | not there | not there |

- **Which prefix.** `silik win open --isolated FILE` uses the prefix `isolated`, never `default`: the programs of
  one prefix are not protected from each other, so the ones you trust and the ones you do not never share one.
  `--prefix NAME --isolated` makes another; an existing prefix that is not marked is refused (exit code 69: a
  program run isolated in it could change the programs that run there on the session's display), and so is the
  answer "isolated" of the question for a file opened with `--prefix` or `silik win install` into such a prefix.
  A prefix made isolated is marked (`~/.local/share/silikos/win-isolated`,
  beside the prefixes and not inside one: a program cannot take its own mark away) and runs isolated from then on,
  its installed programs' entries too, with no switch; `silik win isolate PREFIX` marks an existing one,
  `--off` takes the mark away, no name lists them. A marked prefix never falls back to the session's display: where
  it cannot run isolated it does not run (exit code 69).
- **Its screen.** 1280x800, or `SILIK_WIN_SCREEN=WIDTHxHEIGHT`. The nested server has no window manager, so
  windowed programs run on Wine's own desktop (`wine explorer /desktop=silik,1280x800 PROGRAM`: title bars, a task
  bar, drawn by Wine); a console program typed in a terminal writes to it and reads what is typed, through `silik`
  (it is not given the terminal itself: it would keep it). The session's keyboard layout is
  given to the server (`setxkbmap -display :N ...`: Xephyr's own switches change the layout's name only). The
  server never grabs the session's keyboard (`-no-host-grab`): keys go to the box only while its window has the
  focus, as with any window.
- **The box and its window end together.** One small process (`silik-win-box` in `ps`) holds the X server and
  `bwrap` and ends the one when the other goes: closing the window ends every program of the box, with or without
  a window of its own; when the last program has gone the window closes; `silik win stop PREFIX` ends both.

The lines, as printed:

```
$ setpriv --pdeathsig TERM Xephyr -displayfd 3 -auth $XDG_RUNTIME_DIR/silik-win/isolated/Xauthority -nolisten tcp -nolisten local -noreset -no-host-grab -screen 1280x800 -title 'SilikOS: isolated Windows programs (isolated)' -name silik-win-isolated -extension RECORD -extension XTEST -extension SECURITY -extension DOUBLE-BUFFER -extension XVideo -extension X-Resource -extension MIT-SCREEN-SAVER :153 3>…/display &
$ env XAUTHORITY=…/Xauthority setxkbmap -display :153 -rules evdev -model pc105 -layout es -variant cat
$ env -i /usr/bin/bwrap --unshare-user --unshare-pid --unshare-ipc --unshare-uts --unshare-cgroup-try --unshare-net --new-session --cap-drop ALL --die-with-parent --info-fd 4 --seccomp 5 … --ro-bind /tmp/.X11-unix/X153 /tmp/.X11-unix/X153 --ro-bind …/Xauthority …/Xauthority … --bind ~/Windows/isolated ~/Windows/isolated … -- env … DISPLAY=:153 … wineserver --foreground 4>…/session.json 5<…/seccomp.bpf &
$ pasta --quiet --config-net -t none -u none -T none -U none --no-map-gw --outbound-if4 enp3s0 --no-netns-quit --pid …/pasta.pid --userns /proc/16971/ns/user --netns /proc/16971/ns/net >…/pasta.log 2>&1
$ env -i nsenter --preserve-credentials -t 16971 -U -m -p -i -u -n -C -- setpriv --no-new-privs --pdeathsig KILL setsid --wait env -C … DISPLAY=:153 … wine explorer /desktop=silik,1280x800 ~/Downloads/setup.exe
```

**What isolated does not do** (for a program that is hostile and capable, the Windows VM is still the answer):

- The nested server is the wall, and it is a program: a fault in Xephyr's handling of requests is a way to the
  session. It runs outside the box, as the user.
- No hardware graphics: programs that need Direct3D at speed are slow or do not start [A: not tried].
- Its screen has one size; on a HiDPI screen its text is small (the scale is not passed) [A: not tried].
- What an isolated program leaves in its folder (`~/Windows/PREFIX`) is its word, not yours: a file named like one
  of yours, a link to a file elsewhere in the home (a program of this session that opens it opens that file;
  `silik win open` does not follow such a link), a desktop file. Take out of it what you asked the program for.
- The programs of the normal box see that folder too (it is inside `~/Windows`): they are the ones you trust.
- With network (pasta) it reaches the local network and the internet as this machine does: other machines of the
  network, the router, a cloud's metadata address (169.254.169.254) where the machine is a cloud one. Not this
  machine's own services or its other networks.
- In its own window it draws what it likes, a login or a password question of this system included. The window's
  title bar, "SilikOS: isolated Windows programs (PREFIX)", is what says where a question comes from: SilikOS
  never asks for a password inside that window. Its entry in the applications list ends with "(isolated)".
- It can change its window's size among the sizes Xephyr offers (RandR), not leave the window or cover the screen.
- The kernel, `/etc` and `/sys` read-only: as for the normal box, below.

**The round of 14/11/2026** (a second agent, told to get out of the isolated box or to make the owner run
something un-isolated; EL 9 container, a hostile program standing in for Wine; each line was run before and after):

| What the program did | Now |
|---|---|
| started from a terminal, it left a helper that kept the terminal: it read the password typed at the next prompt, turned the echo on, wrote to it | an isolated program gets pipes, never the terminal |
| replaced the library beside a program in `~/Windows` that the owner had approved for the normal box; the owner's next start of that program ran its code on the session's display | an isolated prefix has its own folder and does not see `~/Windows` |
| swapped a file in `~/Windows` after `silik` had taken its SHA-256 (approved) and before Wine opened it | the same; a file in an isolated prefix's folder runs isolated whatever its SHA-256 |
| `silik win install work setup.exe`, the question answered "isolated": it ran isolated in the unmarked prefix `work`, replaced a program there, which then ran on the session's display | refused (exit 69) |
| with no `bwrap` on the `PATH`, a marked prefix's program ran with the whole account | refused (exit 69); `--no-sandbox` too |
| stopped its wineserver (SIGSTOP): `silik win stop` returned 0, twice, with everything running | the box's first process is killed |
| made a user namespace, root in it: a network device, a mount; read and added keys of the user keyring | the system-call filter |
| reached a server of this machine listening on every address, through the address of a bridge | connections leave by the default route's interface only |
| a link in `~/Windows` to a program elsewhere in the home: opening it showed that folder to the box | such a link is not followed |
| an entry named Firefox, with its icon, in the applications list | "Firefox (isolated)" |

**The first run on an installed system** (CI, 14/11/2026: EL 9's kernel, SELinux enforcing, a GNOME session on
display :0; the code before the round above) showed four more things, each then reproduced in the container:

- **The box's server took the session's display number.** Left to choose (`-displayfd`), with no abstract socket
  (`-nolisten local`) and its lock taken only afterwards, Xephyr made the first free socket *file* its own: it
  removed the session's `/tmp/.X11-unix/X0`, bound its own there, and took the file away when it ended. The session
  kept working through its abstract socket; the box never reached the session's server (asked from inside, the
  socket did not carry the session's mark). `silik` now gives the number: 100 or more, with no socket, lock or
  abstract listener (`Xephyr … :153`).
- **pasta is confined on EL 9** (SELinux domain `pasta_t`, package passt-selinux). It may search `/proc/PID` of a
  program of the session and open the namespace files there, but not open the folder `/proc/PID/ns`, which it does
  to watch for the namespace's end; and it may write files in the runtime folder (`user_tmp_t`), not in `/tmp`. So:
  `--no-netns-quit` (and `silik` ends pasta itself: the process that holds the box does, `silik win stop` does, the
  prefix's next start does), `--pid` and pasta's own words in the prefix's runtime folder (`pasta.log`; they are
  said when pasta fails). No rule was added to SilikOS's own SELinux module. [A] until the next run on an
  installed system: the policy was read (`sesearch`), not enforced here.
- **The first isolated open of a file refused itself** (exit 75, "a running sandbox is not changed"): the set-up of
  the new prefix had started its sandbox without the file, and Wine's services were still there 5 s later. The
  set-up's sandbox now shows what the program that follows needs.
- **A question nobody could answer**: `silik win run PREFIX -- /opt/silik-wine/…/mcs.exe` (Wine Mono's compiler)
  asked about a file of Wine's own folder; the window's GLib lines (`G_RESOURCE_OVERLAYS`, set for the shell) were
  all the command's output showed. Wine's folder is the system's; the question window and the notification run
  without that variable, and the window's standard error is shown only when it fails.

Also since then: the nested server offers fewer extensions (`-extension RECORD`, `XTEST`, `SECURITY`,
`DOUBLE-BUFFER`, `XVideo`, `X-Resource`, `MIT-SCREEN-SAVER`: each is code that reads what the box sends).

What it tried and did not get: the marks file and the answers file (not in the box), `~/.config/autostart`,
`~/.bashrc`, `~/.local/bin`, the applications folder; the session's display, clipboard, keyboard and pointer through
its own server (grabs, pointer warp, selections, an override-redirect window, XTEST: all stay inside); the
session's sockets; `localhost`; the processes of the session (its own process namespace); typing into the terminal
(`TIOCSTI`); the question's text (a name with a line break, markup or a right-to-left mark is shown plain).

**What the sandbox does not do:**

- **The display, and through it the files** (the normal box). A program with the session's display can read the
  keyboard and the screen and send keys to other windows, e.g. type a command into an open terminal. The normal box
  keeps honest programs from reaching your files by mistake; it does not stop a hostile one. For a program you do
  not trust: isolated (above), or the Windows VM (`silik win vm`).
- Sound (the normal box, and isolated with `--sound`): a program can play and record.
- Network (the normal box, unless `--no-net`): it is this machine's network, with what listens on `localhost`.
- The kernel's keyrings: a sandbox starts with an empty session keyring, and the calls that reach the others
  (`keyctl`, `add_key`, `request_key`) are refused by the filter. Before the filter (14/11/2026) a program linked
  the user keyring by its number, read a key in it and added one; EL 9's default Kerberos cache is such a keyring.
  The list of this user's keys, `/proc/keys` and `/proc/key-users`, is covered in both boxes (it showed their names).
- The programs of one prefix are not protected from each other (they can read each other's memory through the
  wineserver). For a program that must not reach the others, or must have no network at all: a prefix of its own.
- The kernel: the filter refuses a short list of calls (above) and allows the rest: a kernel fault in a call that
  Wine does use is as reachable as for any program of the user. A program can no longer make a user
  namespace of its own and be root in it, which is where most such faults were reached from.
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
- **`--no-net` takes the network away and nothing else**: in the normal box the program still has this session's
  X11 display, and with it the keyboard and the other windows (above). The way to run a program you do not trust
  is `--isolated`.
- **A double click asks first**, once per file (above). `--yes`, and a file answered "normal box" before, run with
  the reach of the normal box.
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

Run on 13/11/2026 for `--isolated`, the question and the keyring:

- **An attack from inside the box**, in an AlmaLinux 9.8 container as an ordinary user, with the base's own
  bubblewrap 0.6.3, Xephyr 1.20.11, pasta and util-linux, a session on Xvfb with a key, a window, a clipboard, EL 9's
  `xhost +si:localuser` and stand-ins for Wine's programs (they run a Linux program in the box: the attacker).
  Isolated: the session's display does not open by its socket's file, by its abstract socket or over TCP; a picture
  of the session's screen has 0 bytes; the session's window is not among the box's windows; the clipboard and the
  primary selection have no owner; a key logger (XQueryKeymap, and XInput2 raw events) sees nothing of what is
  typed into the session; keys the box types with XTEST do not arrive in the session (its window got the 6 the
  owner typed); no socket of the runtime folder is there; a server on `127.0.0.1` refuses; with pasta an address
  outside answers, with `--no-net` only `lo` exists. The same program in the normal box: opens the session's display
  (also by the abstract socket), a 9 MB picture of the screen, both selections read, the five keys of the password
  seen, two keys typed into the session, the `localhost` server open, the sound sockets connected. The session bus,
  the keyring daemon's socket and the COMMAND bar's socket are in neither box.
- The box's server refuses a program of the same user without its key; the key file is 0600.
- The layout: a session set to es/cat, the key right of L pressed over the box's window arrives as `ntilde`
  (with Xephyr's own `-xkb-layout es` it arrived as a semicolon).
- Closing the window ends every program (one without a window too) in 2 s; killing `silik-win-box` ends the server
  and the sandbox; `silik win stop` leaves nothing; a prefix opened again after that starts clean.
- **With a real Wine** (9.0, on the build machine, with EL 9's Xephyr binary): a window program run isolated
  draws on Wine's desktop inside the box's window (picture) and is not a window of the session; a console program
  writes to `W:\`, does not see `~/.ssh`, exits 0 and its box is gone 8 s later; the question as text and through
  the window's protocol, the answers kept (0600) and used the second time; the normal box as before.
- The question's window in English, Catalan (dark) and Spanish, each answered with a key (pictures).
- The kernel's keyring: before, a key of the session's keyring was read in both boxes; after, the box's session
  keyring is empty and that key is refused; the user keyring is still linked by number and read.

Not run for these: an installed SilikOS (SELinux enforcing: pasta, Xephyr and the box together; the checks
`win.isolated.*` and `win.question.*` of the CI's installed-system test are for that), the real shell around the box's
window, a GPU, HiDPI, a Wayland session, sound in an isolated box, Firefox's attributes on a downloaded file, a
real third-party installer isolated, Wine 11 isolated.

Not run: the rail and the applications list of the real shell with a Wine window; sound, a GPU, NVIDIA devices, a
Wayland session; a real `.msi`; a 32-bit program on the installed system (one ran in the Wine workflow's container);
a real third-party installer; a real .NET application (only a program compiled for the test); the virtual machine
route, Altium.
