# USB: a device plugged in while the screen is locked is refused

> **Resum (per a en Tomeu).** Com un mòbil: el que endolles amb la pantalla blocada no s'accepta (un llapis USB, un
> adaptador de xarxa, un "teclat" que també és disc). El que hi ha endollat en arrencar, a la pantalla d'inici de
> sessió o amb la sessió oberta funciona sense preguntar res. Un teclat, un ratolí o un concentrador sí que
> s'accepten amb la pantalla blocada (és la regla del GNOME, perquè ningú es quedi fora). El que s'ha refusat
> continua refusat en desblocar: torna-ho a endollar, o `silik usb allow all-present`. Per treure-ho:
> `silik usb level off`. **Provat aquí:** els paquets, la configuració amb el dimoni real, les crides D-Bus i la
> regla de polkit carregada. **No provat:** cap dispositiu real endollat; ho fa el CI amb QEMU (files `usb.*`).

## What happens

| When a device is plugged in | What happens |
|---|---|
| it is there when the machine starts | accepted |
| at the login screen (nobody has logged in) | accepted |
| the session is unlocked | accepted, without a question |
| the screen is locked | **refused**: the kernel does not use it. A keyboard, a mouse or a hub is still accepted (and the desktop says so when the session is opened), so that a keyboard that fell out can be plugged in again to type the password |
| it was refused, and the session is unlocked | it stays refused: unplug it and plug it in again, or `silik usb allow all-present` |

The parts are the base's own. **USBGuard** (`usbguard`, `usbguard-dbus`, `usbguard-selinux` 1.1.4, AppStream)
decides for each device whether the kernel may use it. **GNOME's USB protection** (`gsd-usb-protection`, of
gnome-settings-daemon 40, a program of the user's session; `org.gnome.desktop.privacy usb-protection` true and
`usb-protection-level` `lockscreen` are GNOME's own defaults) tells USBGuard "refuse new devices" when the screen
locks and "accept them" when it is unlocked. Out of the box on EL 9 the two do not work together (below), and with
USBGuard's own configuration every device that is plugged in later is refused, a keyboard included.
`silikos-security` carries what makes them work; nothing of the base is edited:

| File of silikos-security | What it does |
|---|---|
| `/etc/usbguard/silikos-daemon.conf` | the daemon's configuration: `ImplicitPolicyTarget=allow`, `PresentDevicePolicy=allow`, `InsertedDevicePolicy=apply-policy`, `RestoreControllerDeviceState=true`; the rest as the base's `usbguard-daemon.conf`, which stays as shipped |
| `/usr/lib/systemd/system/usbguard.service.d/10-silikos.conf` | the base's unit reads that file instead of its own |
| `/etc/usbguard/rules.d/90-silikos-gnome.conf` | the one rule the desktop looks for (`allow id *:* label "GNOME_SETTINGS_DAEMON_RULE"`) |
| `/usr/share/polkit-1/rules.d/70-silikos-usbguard.rules` | the session at the machine's own screen may make the two calls the desktop needs, without a password |

The daemon is turned on by the kickstart on a new installation and by `silik secure apply` on a running one, never
by a package script, and never with the base's configuration. The packages are recommended by `silikos-security`,
not required (a container, a server or a virtual machine without USB has no use for them), and named in the
kickstart.

## The commands

```
silik usb                         the daemon, the level, each device: allowed or BLOCKED
silik usb allow ID                accept a blocked device (ID: its number in `silik usb`)
silik usb allow all-present       accept everything that is blocked now (after unlocking with a dock plugged in)
silik usb block ID                refuse a device that is plugged in, until it is plugged in again
silik usb level                   lockscreen | always | off: which is on
silik usb level always            every new device is refused, locked or not, except a keyboard, a mouse or a hub
silik usb level off               the desktop switches nothing: every device is accepted
```

Each prints the commands it runs (`usbguard allow-device N`, `gsettings set ...`) and takes `--dry-run`. The daemon
answers root alone (the base's own file also lets the group `wheel` in without a password; SilikOS's does not):
`silik usb allow` and `block` go through `sudo` for everybody.
`allow` and `block` are for the device as it is plugged in now; nothing is written to the rules. A rule of your own
(a device that is never accepted) goes in `/etc/usbguard/rules.conf`, which is read before SilikOS's rule
(usbguard-rules.conf(5)), then `sudo systemctl restart usbguard`; a rule added with `usbguard block-device -p` lands
after the rule that accepts everything and is never reached.

**To turn it off:** `silik usb level off` (this user's desktop stops switching; the daemon keeps running and accepts
everything). To stop the daemon as well: `sudo systemctl disable --now usbguard-dbus.service usbguard.service`; new
devices are accepted again at once (`RestoreControllerDeviceState=true`). `silik secure apply` would turn it on
again; `silik secure status` has the row "USB devices".

## What it does not protect against

- **A device that is present at the start** is trusted, and so is one plugged in at the login screen before anybody
  has logged in: the choice that keeps a machine whose only keyboard is USB usable.
- **A keyboard plugged in while locked** is accepted (GNOME's rule): it can type at the password prompt, nothing
  more. A device that is a keyboard and something else (a disk, a network card) is refused.
- **A program running as the user** in the unlocked session can ask for the same two things the desktop does
  (accept a device, change `InsertedDevicePolicy`): this is a protection against someone at the machine's ports
  while the owner is away, not against software.
- **"Log in as another user" from a locked screen**: the login screen cannot open USB again (the polkit rule refuses
  its user), but another person who logs in with their own password has an unlocked session, and devices are
  accepted while it is at the screen.
- **A restart of the USBGuard daemon** accepts what is plugged in at that moment and starts from
  `apply-policy`, also while the screen is locked; the desktop sets `block` again at the next lock. Restarting it
  takes root.
- **A session that ends while it is locked** (it crashed) leaves USBGuard refusing new devices until somebody logs in
  or the machine restarts: what is plugged in keeps working, a keyboard plugged in at that login screen does not
  [A: from gsd's source, which sets the value back only on an unlock; not seen].
- **A laptop that resumes from sleep** with a device whose USB link was reset may see it as newly plugged in while
  locked [A: not seen here; USB's own "persist" normally keeps the device]: `silik usb allow all-present`.
- **Thunderbolt and PCIe (DMA)**: another mechanism (`boltd`, the IOMMU), another item of docs/SECURITY.md.
- **What a device does once it is accepted**: an accepted keyboard types whatever it wants.
- Other desktops than GNOME, and a text console, have nobody to switch the daemon: every device is accepted.

## What gsd-usb-protection asks USBGuard for (read, not guessed)

From the source of gnome-settings-daemon 40.0.1 (`plugins/usb-protection/gsd-usb-protection-manager.c`, the tag's
file on GitHub's mirror of GNOME's repository) and the strings of EL 9.8's own binary
(`gnome-settings-daemon-40.0.1-24.el9`: `listRules`, `appendRule`, `setParameter`, `getParameter`,
`applyDevicePolicy`, `PropertyParameterChanged`, `DevicePresenceChanged`; no `removeRule`, no `listDevices`).
All on the system bus, to `org.usbguard1`:

| Call | When | polkit action (usbguard-dbus's own default for an active session) |
|---|---|---|
| `org.usbguard1.getParameter("InsertedDevicePolicy")` | at the start of the session | `org.usbguard1.getParameter` (yes) |
| `org.usbguard1.setParameter("InsertedDevicePolicy", "block" / "apply-policy")` | the screen locks / is unlocked (`org.gnome.ScreenSaver` `ActiveChanged`); at the start when the value is not the level's; when the level changes | `org.usbguard1.setParameter` (administrator's password) → **yes by SilikOS's rule** |
| `org.usbguard.Policy1.listRules("")` | at the start, and when the level changes | `org.usbguard.Policy1.listRules` (yes) |
| `org.usbguard.Policy1.appendRule('allow id *:* label "GNOME_SETTINGS_DAEMON_RULE"', 0, temporary)` | only when that exact rule is not in the list | `org.usbguard.Policy1.appendRule` (administrator's password): **not given, and not needed**: the rule is shipped |
| `org.usbguard.Devices1.applyDevicePolicy(id, allow, not permanent)` | a device arrives (`DevicePresenceChanged`) while locked and all its interfaces are HID (03) or hub (09), or its connect type is `hardwired`; in level `always`, a HID or hub, with the screen locked at once | `org.usbguard.Devices1.applyDevicePolicy` (administrator's password) → **yes by SilikOS's rule** |

The login screen's own session (`gdm`, "Display Manager") does not start `gsd-usb-protection`
(`/usr/share/gnome-session/sessions/gnome-login.session` of gdm 40.1-44.el9_8 has no `UsbProtection`; the user's
`gnome.session` has it): at the login screen the daemon's own configuration decides, which is why it accepts.

Two facts found on the way (13/11/2026, an `almalinux:9` container, USBGuard 1.1.4-2.el9 really running):

- `appendRule(rule, 0, temporary)`, as gsd calls it, **fails on this USBGuard** ("Policy append: rule:
  Invalid parent ID"), with an empty rule set too. So GNOME's rule that accepts devices while unlocked is never added, and with
  the base's `ImplicitPolicyTarget=block` every device plugged in after the daemon starts would be refused, locked
  or not. With the rule shipped in `rules.d`, `listRules` answers exactly the text gsd compares, and gsd adds nothing.
- usbguard-dbus asks polkit with a dialog allowed: without a polkit rule, each of gsd's calls would be a password
  prompt at every login and every lock.

## Verified, and not verified

Run (the build machine, in `almalinux:9` containers, 13/11/2026; no device, no systemd, no session there):
the packages are in AppStream (`usbguard`, `usbguard-dbus`, `usbguard-selinux` 1.1.4-2.el9); installing them
enables nothing (the base has no preset for them); `silikos-security` installs beside them with `rpm -V` clean
for all three; the daemon, started with the drop-in's command line on an empty USB bus, loads the configuration
and the rule (`InsertedDevicePolicy apply-policy`, `ImplicitPolicyTarget allow`); `setParameter` is not written to
the file; a rule file that is not mode 0600 stops the daemon; over D-Bus `listRules` returns the rule as gsd wants
it; polkitd loads the rule file without an error; a user without a session is refused `setParameter` and
`listRules`, an administrator reaches the daemon's own socket; `systemd-analyze verify` accepts the unit with the
drop-in; `silik usb` against that daemon. The polkit rule's decisions were run in node with made-up subjects
(`tests/test_usb.py`). The host side of the CI's hot-plug was run against QEMU 8.2.2 with the machine stopped.

With devices (the build machine has no KVM, USB bus, GNOME session or SELinux): the
installed-system test of the CI does it (its `run.sh` and `check.sh`, rows `usb.*`): an xHCI controller
with a disk from the start, then a keyboard and a disk plugged in through QEMU's monitor with the session unlocked
(must be allowed), the session locked with `loginctl lock-session` (`InsertedDevicePolicy` must read `block`), a
disk plugged in (must be blocked), a keyboard (must be allowed), unlocked again (must read `apply-policy`, the
disk still blocked), `silik usb allow all-present` (allowed). Seen there (runs 43537343489 and 43549553439,
14/11/2026): every step up to the disk still blocked after unlocking, under SELinux enforcing with SilikOS's
configuration file. Not seen: `silik usb allow all-present` and the daemon refusing a user without sudo: their two
checks never ran (a quoting fault of the test's script, fixed 14/11/2026: the next run says them).
Also not seen: SELinux letting the daemon read
`silikos-daemon.conf` (its path carries the type `usbguard_conf_t` by the policy's own pattern
`/etc/usbguard(/.*)?`) [A]; polkit finding the session of a program that runs under `systemd --user` [A: the
base's own bolt rule relies on the same]; a real dock, a real laptop's sleep.
