# The session's start, Start's first opening and the shell at rest: measured, and what was taken out

> **Resum (per a en Tomeu).** El mig segon que SilikOS triga més que l'AlmaLinux de sèrie a tenir l'escriptori és
> **abans** que la shell comenci: una sessió X11 engega el servidor Xorg, fa córrer els scripts d'inici (dos dels
> quals, dels paquets de Qt, criden `glxinfo` cadascun) i el `gnome-session` comprova els gràfics; a Wayland res
> d'això passa. La shell mateixa no és més lenta. Dins la shell, el que hi posàvem nosaltres eren 67 ms (al banc de
> proves, sense targeta gràfica) i ara en són 35: la fulla d'estil de SilikOS es carregava tres vegades (ara una),
> i el `silik look --qt` s'engegava abans de tenir l'escriptori (ara després). La primera obertura de l'Start
> costava 29 ms de la shell i ara 19 (les següents, 8, com abans). En repòs l'extensió no gasta res que es pugui
> mesurar. `silik` no té res a esgarrapar que passi de 10 ms. **Tot això és mesurat al banc de proves (un
> contenidor, renderitzat per programari), no en maquinari real ni a la màquina virtual del CI:** el workflow
> Compare ho ha de tornar a mesurar. Decisió teva: els dos fitxers que fan que `glxinfo` corri un cop en lloc de dos
> (secció 2) canvien com s'executen dos scripts de la base sense tocar-los.

13–14/11/2026. Everything here was measured in the test rig: a container with AlmaLinux 9.8, GNOME Shell 40.10 on
Xvfb at 1280x800, **software rendering (llvmpipe), 4 processors shared with other work, not real hardware**. A number
is a median with its smallest and largest sample in brackets; N is said each time. Where the machine was busy with
other work while a series ran, it is said. The CI's virtual machine and a real workstation have other numbers: the
Compare workflow re-measures what it can (section 9).

## 1. The half second against the stock system: it is before the shell starts

`docs/NUMBERS.md` §9: SilikOS reaches `graphical-session.target` 3.65–3.72 s after the user's manager starts, the
stock AlmaLinux 3.13–3.15 s, and GNOME Shell's own unit is not slower (1.74 s against 1.78–1.81 s). The journals of
two runs say where the rest is. The Compare run (43461175134) printed the stock system's lines; the SilikOS lines of
that run were cut off (the X server's own log filled the 90 lines kept; the filter is fixed since), so SilikOS's are
those of the CI run of the same day (43509961201), **another runner, a faster one** (its shell unit takes 1.33–1.39 s
where the Compare run's took 1.74 s). Seconds, from the start of the user's manager:

| | SilikOS, X11 (CI run, two starts) | AlmaLinux, Wayland (Compare run, two starts) |
|---|---|---|
| until the session's target is reached (`GNOME X11 Session` / `GNOME Wayland Session`) | 0.884, 0.842 | 0.453, 0.433 |
| from there until the shell's unit begins | 0.104, 0.079 | 0.109, 0.112 |
| the shell's unit (`org.gnome.Shell@x11` / `@wayland`) | 1.392, 1.328 | 1.808, 1.784 |
| from the shell started to `graphical-session.target` | 0.660, 0.626 | 0.778, 0.802 |
| `graphical-session.target` | 3.039, 2.876 | 3.148, 3.130 |

- **The first row is the difference: 0.84–0.88 s on X11, 0.43–0.45 s on Wayland.** On X11 the journal shows the X
  server starting 0.19–0.20 s after the user's manager, its last line at 0.25–0.27 s, and nothing more until the
  target at 0.84–0.88 s: the X server coming up, the session's shell script and gnome-session's check of the
  graphics (section 2). None of it is a SilikOS program.
- The last row's two columns cannot be subtracted (two runners). In the Compare run itself SilikOS's total is
  3.653 / 3.723 s; its split is not known until the next Compare run [A: the proportions of the CI run].
- After the shell, X11 waits for `org.gnome.SettingsDaemon.XSettings` (0.46–0.47 s in the CI run, 0.66–0.67 s in the
  Compare run; it exists only on X11 and starts only once the shell is up). Wayland waits as long for others: its
  Keyboard, Power, Color, MediaKeys and Wacom daemons take 0.59–0.76 s each where X11's take 0.13–0.26 s.
- Units only on one side, in the twenty slowest of `systemd-analyze --user blame`: on SilikOS `XSettings`; on the
  stock system `xdg-desktop-portal` (0.51–0.86 s) and `xdg-desktop-portal-gnome` (0.20–0.36 s). **No unit of
  SilikOS's is in the user's session at all**: the packages ship no user unit and no autostart entry (the speed
  profile adds one that turns GNOME Software's off); the dconf database is compiled when a package is installed, not
  at login.

## 2. What an X11 login runs before the desktop

Read on the rig (`/etc/gdm/Xsession`, `/etc/X11/xinit/xinitrc-common`, the files of `/etc/X11/xinit/xinitrc.d`,
gnome-session 40.1.1's `gnome-session-check-accelerated`) and timed there, each N=10, the machine busy:

| Step of an X11 login | Whose | Time in the rig (software rendering) |
|---|---|---|
| `10-qt5-check-opengl2.sh`: runs `glxinfo` to read the OpenGL version | qt5-qtbase-gui (it comes with qt5ct and any Qt 5 program) | `glxinfo` 68 ms (52–79) |
| `10-qt6-check-opengl2.sh`: the same, again | qt6-qtbase-gui (it comes with a Qt 6 program: Qucs-S) | `glxinfo` 68 ms (52–79) |
| the other files of `xinitrc.d` (the session bus, the user's manager's environment, `xhost`) | dbus-x11, systemd, xorg-x11-xinit | a few ms each |
| `exec -l $SHELL -c gnome-session`: a login shell (`/etc/profile`, `profile.d`) | xorg-x11-xinit, setup | `bash -lc true` 39 ms (33–47); without `-l`, 2 ms |
| `gnome-session-check-accelerated` (only where `DISPLAY` is set: not in a Wayland session [A: its code as remembered; the stock system's journal shows no such wait]) | gnome-session | 97 ms (86–126); its GL helper alone 34 ms (30–39), its GLES helper alone 73 ms (64–94) |

- The loop over `xinitrc.d` as the base has it: **173–198 ms** (medians of four series of 11; 148–235).
- These are the pieces that could be timed alone: about 0.3 s, where the CI's journal has 0.66–0.69 s between the X
  server's start and the session's target. The X server's own start was not timed (the rig's is Xvfb).
- **On real hardware these times are not known**: creating an OpenGL context on a graphics card is not what it is on
  llvmpipe, and gnome-session's check then needs one helper, not two [A: from the two times above adding up to the
  whole].

**What was done: `glxinfo` once instead of twice.** The two Qt files ask the same program the same question. Two
files of silikos-desktop, `05-silikos-glxinfo.sh` and `11-silikos-glxinfo.sh`, stand around them in the folder's
order: where both Qt files are installed (and `glxinfo`, and no answer is given already), the first runs `glxinfo`
once and makes that answer what the word `glxinfo` gives; the second takes that away again. Both Qt files then read
the same line they would have read. With one Qt file, or none, nothing is done. Nothing of the base is changed or
replaced. The loop with them: **101–115 ms** (four series of 11; 80–142); from the installed package, 87 and 98 ms
(two series of 11; 74–115). The largest sample with is below the smallest without.

Not done, and why: gnome-session's check (`gnome-session --disable-acceleration-check` exists) is what falls back to
software rendering when the graphics do not work, and what GNOME Settings shows as "Graphics" [A: its code as
remembered]; the login shell is the base's. Whether Qt 5 and Qt 6 are both on a kickstart installation is not known here [A]: the bench now lists
the folder and times these steps on both systems (section 9).

## 3. The shell's unit: what SilikOS puts into it

The shell tells systemd it has started (`READY=1`) at its first idle moment after `start()`, so everything an
extension does in `enable()` is in the unit's time. Timed from inside the shell (rig only: a copy of the shell's
`extensionSystem.js` and `main.js` with a clock around each extension and each `loadTheme`, read through
`G_RESOURCE_OVERLAYS`; never shipped), in fresh sessions that have the environment an installed system's session
has (`60-silikos-shell.conf`). Old and new in turn, nine sessions each, the machine quiet:

| In the shell's start (ms) | silikos-desktop 0.17.0 | now |
|---|---|---|
| every extension, from finding them to enabled | 66.9 (57.6–83.8) | **34.6 (28.5–35.5)** |
| silik-shell: loading its two files, its stylesheet, `enable()` | 45.9 (38.2–56.4) | 30.9 (25.6–31.8) |
| user-theme: loading it, `enable()` | 18.2 (15.8–22.5) | not turned on |
| the shell's theme made (`loadTheme`): times, total | 2, 25.6 (22.5–28.8) | 1, 8.2 (7.1–9.5) |
| the shell's `start()` | 462 (396–498) | 433 (376–479) |
| `READY=1` after the shell's exec | 859 (743–893) | 794 (748–839) |

The first four rows moved beyond their spread. The last two moved the same way but **inside their spread**: the
shell's start in the rig varies by 100 ms from one session to the next. The same with the machine busy (N=7 each):
island 99.9 (73.7–135.8) → 36.5 (30.7–39.6), the Silik look 83.6 (72.9–187.1) → 35.0 (28.4–73.3), the bar 81.3
(64.9–121.0) → 40.3 (29.2–45.6). With an accent (cobalt) 74.2 (65.1–120.7) → 64.0 (58.7–98.2): **not beyond the
spread**; an accent's stylesheet has to be loaded, by whoever does it.

What was taken out:

1. **The stylesheet was loaded three times.** The session's environment already makes the SilikOS stylesheet the
   shell's own (`G_RESOURCE_OVERLAYS`, so that the lock and login screens have it). The user-theme extension then
   loaded the same 77 kB file over it: the shell read and parsed its own again and that one on top. One copy parsed:
   9.3 ms (8.8–12.0); the pair: 18.2 ms (17.4–20.0) (N=9, in a running shell). Every widget was also matched against
   the rules twice. Now the desktop's defaults turn on `silik-shell` alone; in ink nothing is loaded; with an accent
   `silik-shell` loads `SilikOS-<accent>` itself, and in a session without that environment `SilikOS`. **The
   picture is the same**: in one session, with and without the second copy, 0 pixels differ (desktop, Start open);
   between sessions of the old and the new extension, in the three looks, with Start open, with the accent cobalt set
   through `silik look`, with the calendar open, and back in ink, the only pixels that differ are the clock's last
   digit (11 pairs, 40–49 pixels in a box of 7x8). Where a user has user-theme on, it does the work as before
   (`silik look --accent` still writes its key).
2. **`silik look --qt -q` was started inside `enable()`.** Starting a program costs the shell 10.0 ms (9.3–11.6,
   N=7): a large process is copied to start one [A: GLib's fork; the time is measured, the reason is not]. It now waits for `startup-complete` and an idle moment, and is
   not started at all without qt5ct.
3. With one stylesheet instead of two, building the pieces costs less: `enable()` as a whole 41.3 (35.7–54.1) →
   25.3 (21.2–33.9) ms in the island look, 37.8 (36.3–45.4) → 21.8 (19.0–31.2) in the Silik look (N=7 each).

What `enable()` is made of now (island, N=7, ms): the keys of the rail's applications 8.4 (6.6–11.4), of which
finding which have a line icon 5.5 (4.7–8.1: the first question loads GTK's icon theme); the piece itself 7.6
(6.1–10.2); the glass 2.9 (2.5–3.4); placing 2.6 (2.4–4.3); Start's pane, hidden, 1.3 (1.1–1.6); the watches of
files under 1. All of it is needed for the first picture. Compiling the extension's two files, as the shell does
when it loads them, was measured apart (gjs 1.68.6, 13/11/2026): 1.2–2.3 ms for `extension.js`, 0.5–1.0 ms for
`flow.js`.

## 4. Start: the first opening

Start opened and closed ten times in a session 50 s old; the time of the call (the extension's own work) and until
the shell had drawn the next picture (software rendering: that part is the rig's). Five fresh sessions of each, in
turn, the machine busy; the island look; 17 applications in the list (the rig's: an installed system has more rows,
which were already made before the first opening):

| ms | 0.17.0 | now |
|---|---|---|
| first opening of a session: the call | 29.1 (25.4–40.2) | **18.6 (12.2–19.4)** |
| first opening: until the next picture | 68.9 (59.7–91.3) | 61.5 (48.4–69.1) |
| tenth opening: the call | 8.1 (6.7–10.3) | 8.3 (5.9–9.8) |
| tenth opening: until the next picture | 25.0 (19.9–39.7) | 23.2 (19.4–31.2) |
| a closing (N=50): the call, until the next picture | 1.9 (1.2–3.4), 11.1 (8.0–26.5) | 2.1 (1.6–3.6), 10.1 (7.9–26.1) |

The rows of the list were already made before the first opening; the pane itself was not. Of the first opening's
call, 10–12 ms were the pane measured for the first time and 4–6 ms its first showing. The last idle slice after the
rows now fills the pane as an opening does, puts it among the things on the screen at opacity 0 (which the shell does
not draw), measures it and hides it again, before the shell draws its next picture. The call is beyond the spread;
**the time until the picture is not** (the first picture still makes the pane's glass and draws its text for the
first time). What is left in the first call: taking the keyboard for the first time, 3.6–4.8 ms against 0.7–1.5.

## 5. At rest

- The extension has no repeating timer and no poll (read again, 14/11/2026): the power word, the restart notice and
  the last command are file monitors; the glass's 200 ms timer runs only while a window draws behind an open pane in
  a crystal mode. Its two idle moments (the Qt palette, Start's rows and pane) each run once and end.
- CPU time of the shell in 10 s, 5 s after the desktop is up, fresh sessions without windows, N=7: with silik-shell
  and user-theme 20 ms (20–30), with user-theme alone 20 (10–40), with no extension 20 (20–30), the base's shell
  with its own stylesheet 20 (20–30). Wake-ups of its main thread: 0.8–1.5 a second in all four (0.5–2.9). **The
  extension adds nothing that can be measured.** In sessions with Files and a terminal open, 20 s: 0.17.0 20–30 ms,
  now 20–40 ms (N=5 each): 0.10–0.20 % of one processor, 1–2 wake-ups a second, the same.
- Memory of the shell 15 s after its start (`smaps_rollup`, N=7; software rendering keeps the pictures in the
  process, so the totals are the rig's): resident 324.5 MB (323.6–325.1) with both extensions, 321.7 with user-theme
  alone, 319.5 (318.2–319.9) with none, 319.9 (317.9–321.4) for the base's shell. Private memory 200.7, 199.0, 196.5,
  196.2 MB. Old against new (N=7 each): private 199.2 (196.6–199.9) → 197.4 MB (194.6–197.5), resident 322.4
  (320.0–324.1) → 321.5 (318.4–322.2): about 2 MB less, at the edge of the spread.

## 6. `silik` itself

In the rig, ten runs of each after one that is not counted, wall time, the machine quiet (silik-tools 0.9.1):

| Command | ms |
|---|---|
| `python3 -IS -c pass` (what Python itself costs) | 7.5 (6.2–10.9) |
| `silik --version` | 33.0 (26.7–36.1) |
| `silik --help` | 33.5 (29.3–44.8) |
| `silik look` | 63.7 (53.2–85.5) |
| `silik look --qt -q` (what the shell starts at login) | 38.7 (32.0–44.9) |
| `silik status` | 63.3 (54.6–89.0) |
| `silik speed` | 48.7 (40.9–59.3) |
| `silik doctor` | 665 (592–702) |
| `silik secure status --offline` | 1506 (1396–1623) |

- Of the 25 ms over Python's own start: importing the command 20 ms (`-X importtime`, one run: argparse and what it
  imports 8.6, subprocess 2.8, shutil 2.7, json 1.3, the module's own body 4.4).
- **Finding the plugins: 0.11 ms** (0.11–0.34, N=30) for the eight heads read. **The parser: 0.50 ms** (0.38–1.45)
  without a group, 0.20 ms for `secure`. One index file made at build time would save a tenth of a millisecond.
- **Nothing here yields 10 ms: nothing was changed.**
- `silik doctor` and `silik secure status --offline` are the programs they ask (35 and 23 of them; the doctor asks
  side by side, 1.0 s of processor time in 0.67 s). `firewall-cmd` is asked four times (`--get-default-zone`,
  `--get-active-zones`, `--get-zones`, `--list-all`), 0.15–0.6 s each (one run, the machine busy); `dnf updateinfo`
  0.84 s. That is `silik secure`'s part: left to it, and said to it.

## 7. At boot

`silikos-themes.service` is the one unit of SilikOS's ordered before the login screen. It has
`ConditionPathExists=|!` on the two ink themes: with both made it does not run. Run in the rig: `systemctl start`
returned in 7 ms and the journal says "was skipped because no trigger condition checks were met". (The 5.8 s it
shows in the rig's `systemd-analyze blame` is a run made by hand with a theme taken away.) Nothing to change.

## 8. How it was measured

Scripts in the build machine's scratch folder, not in the repository (the rig is not shippable): a fresh session
for every sample (Xvfb, a session bus, `gsd-xsettings` given three seconds, then `gnome-shell --x11` started as
systemd starts it, with a `NOTIFY_SOCKET`); the old and the new extension put in place in turn, so that a busy
moment falls on both; the same script and the same waits for both. The clocks inside the shell are
`GLib.get_monotonic_time()` around each call, in copies that exist only in the rig. Pictures are the X server's
frame buffer; "0 pixels differ" is ImageMagick's `compare -metric AE`. A change that did not move its number beyond
the spread was not made: moving the glass's stylesheet before the pieces (about 1 ms), not making Start's hidden
pane at `enable()` (1.3–1.6 ms), keeping the first page's keys from one opening to the next (about 3 of 8 ms, inside
the spread of the openings).

## 9. Not run here, and what will run it

| What | Who |
|---|---|
| Any of this on the CI's virtual machine or on real hardware; the session's start with these changes (`graphical-session.target`, the shell's unit) | the Compare workflow (`systemd-analyze --user`, the journal's lines) |
| The split of SilikOS's 3.65 s in the same run as the stock system's | the next Compare run: the journal's filter no longer lets the X server's log fill it |
| Which files are in `xinitrc.d` on an installed system, and what `glxinfo`, gnome-session's two helpers and a login shell take there | `tests/install/bench-guest.sh` now lists the folder and times each three times, on both systems |
| That an installed session has `silik-shell` alone enabled and the SilikOS stylesheet as the shell's own | `tests/install/check.sh`: `desktop.user-theme-off`, `desktop.shell-stylesheet`; the accent checks (`accent.volt-vivid`, `accent.ink-again`) count the extension's errors |
| An X11 login through gdm with the two files of section 2 (here: the loop of `xinitrc-common` run by bash, and bash against stand-ins in the tests) | the CI's installation: its session is an X11 login |
| The lock screen and the login screen after these changes (they have the shell's own stylesheet, as before; the rig has no gdm session) | the CI's installation; a person |
