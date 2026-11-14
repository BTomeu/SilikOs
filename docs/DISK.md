# Data at rest and the boot chain

What a stolen or briefly unattended SilikOS laptop gives away, what stops it, and what does not. The commands are
`silik disk` (13/11/2026). Like the rest of `docs/SECURITY.md`: the base's own mechanisms (LUKS2, the TPM, Secure
Boot, the signed shim, GRUB and kernel of AlmaLinux), nothing of ours in the boot path.

**No real machine has run any of this.** A virtual machine has (GitHub's CI, 14/11/2026): what ran, and where, is
in the last section; [A] marks what is assumed from the base's documentation or source and has not been seen.

```bash
silik disk                 # what is encrypted (/, /home, swap), the LUKS volume, the TPM, Secure Boot, what opens the disk
sudo silik disk            # the same with the key slots (only root reads a LUKS header)
silik disk check           # the same, and what to do: a copy of the header, a recovery key... (commands printed, none run)
silik disk tpm enroll      # a short PIN at each start instead of the passphrase: TPM2 + PIN, bound to the Secure Boot state
silik disk tpm remove      # back to the passphrase at each start
silik disk recovery        # one more key slot: a generated recovery key, shown once (for paper)
```

`silik disk` never formats, never encrypts or re-encrypts, never removes a passphrase or recovery slot. It finds the
volume from the running system (what `/` is on), prints the device and asks before anything is written to it (`--yes`
for scripts), and prints each command it runs; `--dry-run` runs none. Without root it says `unknown` for what it
cannot read, never `ok`.

## Against whom

| Who | What stops them | What does not |
|---|---|---|
| A thief with the laptop **switched off** (or the disk taken out) | LUKS2 on `/`, `/home` and swap: without the passphrase the disk is noise. The passphrase is stretched with argon2id (up to 1 GiB of memory for each guess, cryptsetup's default) | A short or guessable passphrase: it can be guessed offline, on as many machines as the thief has. The TPM slot does not change this: the passphrase slot stays (it is the way back) |
| The same thief, **with TPM2 + PIN enrolled** | The key of the TPM slot never leaves the TPM without the PIN; the TPM counts wrong PINs and locks itself for a time (its own setting, not ours); the slot opens only with Secure Boot in the state it was enrolled in, in this machine | The passphrase slot, as above. A TPM slot **without** a PIN: the machine opens its own disk for whoever holds it (`--no-pin` has to be typed, and `silik disk` then says bad) |
| Somebody with the machine in their hands **for a few minutes, who gives it back** ("evil maid") | With Secure Boot on they cannot make the firmware start a boot loader or kernel that is not signed; with it off, or with another machine's firmware keys, the PIN no longer opens the disk: the passphrase is asked, and that is the sign that something changed | `/boot` is not encrypted and **the initramfs and the kernel's arguments are not signed or measured into PCR 7**: they can be replaced by ones that keep what is typed. The PIN or the passphrase typed after that is theirs at their next visit. Nothing in SilikOS detects it |
| Somebody at the machine **while it runs** (unlocked, or locked with the disk open) | The screen lock (`docs/SECURITY.md`) | The disk is open: encryption protects nothing then. The key is in memory, also while suspended (a cold-boot attack reads memory; only powering off ends it) |
| Somebody who can change the **firmware** | A password on the firmware's setup (the owner sets it; no command can see whether it is there) | A firmware implant, or Secure Boot turned off in the setup: outside what an operating system can check |
| A **signed but vulnerable** boot loader or kernel put in place of the current one | Revocation: the shim's SBAT level comes with the base's `shim-x64` package (`silik update`); the firmware's forbidden list (dbx) comes through `fwupd` from LVFS | AlmaLinux ships the LVFS source **disabled** (`/etc/fwupd/remotes.d/lvfs.conf`, `Enabled=false`, read in fwupd 2.0.19-2.el9_8.alma.1): no dbx update arrives until `fwupdmgr enable-remote lvfs`. `silik update` runs dnf and **does not show firmware or dbx updates** (`fwupdmgr get-updates` does) |

## Encryption is chosen at installation, and why the installer does not tick it by itself

In the installer's **Installation Destination** screen: **Encrypt my data**, then a passphrase. With "Automatic" it
makes one LUKS volume under everything (`/`, `/home`, swap); LUKS2 is the installer's default (`luks_version = luks2`
in anaconda 34.25.7.14's own configuration) and cryptsetup 2.8.1's default key derivation for LUKS2 is argon2id; the
installed result is what the CI's encrypted installation looks at [A until it has run].

The owner's rule is that the kickstart never selects or erases a disk. The only thing a kickstart can say for
encryption is `autopart --encrypted` (valid: `ksvalidator -v RHEL9`, as are `--luks-version=luks2` and
`--pbkdf=argon2id`), and it was **not** added, because of what the installer does with it (read in anaconda
34.25.7.14, not run):

- any kickstart makes the installation "automated"; a kickstart that names `autopart` makes the Storage module create
  an automatic partitioning before the person has seen a screen (`PartitioningFactory.get_method_for_kickstart`);
- the Installation Destination screen then, on its own: selects **every** disk (`select_default_disks`), asks for the
  passphrase in a dialog when `--encrypted` has none, and applies the automatic partitioning (`_initialize` →
  `execute`). Where the disks have room, the screen is already "complete" when the person arrives: the disk was
  chosen for them.

So without `--passphrase` it does ask the passphrase and it does keep "Encrypt my data" ticked; but it takes the choice
of the disk, which is the one thing the kickstart must leave alone. The installer's configuration has no setting for "ticked by
default" (its `[Storage]` section names the scheme and the LUKS version; nothing there encrypts).

What carries the weight instead:

- `silik disk` and `silik secure status` say `▼ bad` for a disk in clear;
- at the first login after an installation without encryption a notification says it once (`silik disk notice`, an
  autostart entry of `silik-tools`; again only if what is in clear changes);
- the first-hour guide tells the person to tick it.

No command of SilikOS encrypts a disk that is in use (the base's `cryptsetup reencrypt` can; it rewrites the whole
disk and a power cut in the wrong second loses it: not behind a `silik` command).

PROPOSAL, not done: the installer's process could be made to start with the box ticked by a small Python hook in the
ISO's `product.img` (the default of `AutoPartitioningModule`'s request; a kickstart that names `autopart` would still
decide for itself). It changes the installer's behaviour from outside its configuration and cannot be tried without an
installer run: the owner's call.

Also read there, and not new: with any kickstart (so with SilikOS's) the Installation Destination screen opens with
**all disks ticked**, where an installation without a kickstart ticks one only when there is only one. Nothing is
partitioned until the person leaves the screen, and nothing is erased without the installer's own "Reclaim space"
dialog; on a machine with a second disk, untick it. [A: read in `select_default_disks`, not seen on a screen]

## `silik disk`

Run for real on AlmaLinux 9.8 (cryptsetup 2.8.1, systemd 252-67.el9_8.6) on a LUKS2 volume and a software TPM, with a
stand-in for the list of block devices (the last section says exactly what was real):

```text
● ok       /                  encrypted: /dev/mapper/luks-x is on /tmp/l/a.img
● ok       /home              in the file system of /
● ok       swap               none
● ok       LUKS /tmp/l/a.img  LUKS2, aes-xts-plain64, 512-bit key; key slots: 0 passphrase (argon2id), 1 TPM2 + PIN (PCR 7), 2 recovery key
● ok       TPM                2.0; PCR 7 (the Secure Boot state) is measured
● ok       Secure Boot        on
● ok       opens with         TPM2 + PIN while the Secure Boot state is the one it was enrolled in, or the passphrase or the recovery key
7 ok, 0 warn, 0 bad, 0 unknown
```

- **bad**: `/`, `/home` or swap on a disk in clear; a TPM slot without a PIN.
- **warn**: LUKS1, or a passphrase stretched with PBKDF2 (the command that changes it is printed); Secure Boot off;
  a TPM slot that a start does not use (no `tpm2-device=` in `/etc/crypttab`, or an initramfs without TPM support)
  or that is bound to nothing useful; other file systems mounted in clear.
- `--json` for programs: the rows, and the state they were made from.

## TPM2 + PIN (`silik disk tpm enroll`)

What it runs, each line printed (as root; it also reads the header before and after; at a terminal the base's
`systemd-cryptenroll` asks for the passphrase and the new PIN itself, so neither passes through `silik`):

```bash
systemd-cryptenroll --wipe-slot=tpm2 DEVICE        # only when a TPM2 slot is already there
systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7 --tpm2-with-pin=yes DEVICE
cp -a /etc/crypttab /etc/crypttab.before-silik-disk ; tee /etc/crypttab    # tpm2-device=auto on the volume's line
dracut -f                                          # the running kernel's initramfs, with the crypttab and TPM support
```

- **It refuses** when Secure Boot is off or PCR 7 was never written by the firmware (the key would be bound to
  nothing: `--even-without-secure-boot` to do it anyway); when there is no TPM 2.0; on LUKS1.
- **Never without a PIN** unless `--no-pin` is typed, and then with the warning above.
- **The passphrase slot is never touched.** Only TPM2 slots are ever wiped, and a TPM2 slot is not replaced when it
  is the only slot.
- An earlier TPM2 slot is wiped first because, asked to enrol a slot whose PCR state is already enrolled,
  systemd-cryptenroll 252 does nothing ("This PCR set is already enrolled": seen), and the new PIN would not be the
  one that opens the disk.
- `dracut` takes TPM support into the initramfs when a line of `/etc/crypttab` has `tpm2-device=` and the program
  `tpm2` is installed (read in dracut 057-120.el9_8's `90crypt` and `91tpm2-tss`): `tpm2-tools` is installed first
  when it is missing. Only the running kernel's initramfs is made again: the other installed kernels and the rescue
  entry keep theirs and ask for the passphrase, a known way to start if the new one fails.
- From a script: the passphrase in `--unlock-key-file FILE`, the PIN as the first line of the standard input (handed
  to systemd-cryptenroll in `$NEWPIN`; never on a command line, never printed).

**PCR 7** is what the firmware measured of the Secure Boot policy: whether it is on, the firmware's key lists (PK,
KEK, db, dbx), and the certificates that verified what was started [A: systemd-cryptenroll(1) and the shim's own
notes]. Bound to PCR 7 only:

- a **kernel update does not change it** (the kernel is verified with the same certificate; the initramfs and the
  kernel's arguments are not measured there): the PIN keeps working across `silik update` [A: follows from what PCR 7
  holds; not run];
- it **changes** when Secure Boot is turned off or on, when the firmware's key lists change (a firmware update that
  brings new ones, a dbx update through fwupd), and with a shim signed by another certificate or carrying another
  revocation level [A]. Then the TPM does not give the key: the passphrase is asked; after that start,
  `silik disk tpm enroll` again;
- binding to more (`--pcrs 7+8+9`: GRUB's commands and the files it loads [A]) would catch a changed initramfs, and
  would also ask the passphrase after every kernel update. Not the default.

What somebody with the machine in their hands **can** do under this policy: read and change `/boot` (previous
table); start this same signed boot loader and kernel from another medium, which gives the same PCR 7 — which is why
the PIN is not optional; guess the PIN at the TPM's own pace until it locks; attack the passphrase slot offline.
What they **cannot**: get the TPM's key without the PIN, or with the PIN in another machine or under another
Secure Boot state; guess the PIN offline.

When the PIN does not work (forgotten, the TPM replaced with the mainboard, the firmware's keys changed, the TPM
locked): the passphrase or the recovery key still opens the disk. At a start that the PIN does not open, the PIN is
asked a second time, then "TPM2 operation failed, falling back to traditional unlocking" and the passphrase is
asked. Seen in the CI's virtual machine with Enter alone and then a wrong PIN; with the right PIN under another
Secure Boot state or in another machine the second question was seen, the passphrase after it not yet (the test
stopped there by its own fault; mended, to run again).

## The TPM's count of failed tries

The TPM counts failed tries by itself and locks when they reach its limit; systemd does not set or read it. What
counts, measured on the software TPM (swtpm 0.8.0, with an object sealed as systemd-cryptenroll seals its own: PCR 7
and the PIN) and consistent with the counter the CI's machine showed:

| What happened | Counted |
|---|---|
| The right PIN | no (and it does not take earlier failed tries back) |
| A wrong PIN | one |
| Enter alone at the PIN prompt | no [A: from the CI machine's counter, not measured alone] |
| Any PIN, right or wrong, under another Secure Boot state (PCR 7 changed) | no: the TPM refuses on the state before it looks at the PIN |
| The disk in another machine | nothing in the first machine's TPM |
| **The machine switched off by force** (no shutdown) in a session in which the PIN was used, even the right one | **one**, at the next start |

At the limit the TPM refuses the right PIN too, also after switching off and on (measured with the tools; a start in
that state is the CI test's `locked` start, not run yet). The passphrase always opens the disk: its key slot does
not go through the TPM. The ways out:

1. **The passphrase** (or the recovery key), at every start, for as long as it takes.
2. **Wait.** The TPM forgives one failed try each time its own interval passes while it is powered [A: the TPM 2.0
   rule; not measured]. The software TPM: 3 tries, 1000 s. A laptop's chip has its own numbers:
   `sudo tpm2_getcap properties-variable` (`TPM2_PT_MAX_AUTH_FAIL`, `TPM2_PT_LOCKOUT_INTERVAL` in seconds,
   `TPM2_PT_LOCKOUT_COUNTER`, `inLockout`).
3. **`sudo tpm2_dictionarylockout --clear-lockout`** puts the count back to zero at once and the PIN works again
   (measured on the software TPM, whose lockout authorisation is empty). Where the firmware or another system has
   set that authorisation it is refused [A], and a refused clear locks that command itself for the TPM's recovery
   time [A]: then wait, with the passphrase.

`silik disk` does not read the count (it would need root and the tools at every call): the passphrase being asked
after the PIN is the sign. So: do not hold the power button at or after the PIN prompt, and a PIN typed wrong twice
in a row is two tries.

`silik disk recovery` runs `systemd-cryptenroll --recovery-key DEVICE`: the key is printed by systemd-cryptenroll
itself, once, and passes through no file or variable of `silik`. `silik disk check` prints, and does not run,
`cryptsetup luksHeaderBackup` (a damaged header loses the disk whatever the passphrase; the copy opens the disk with
the passphrases of the day it was made, so it is kept as a key, and not on the same disk).

## The system on an external disk, started from the computer's boot menu

The owner's way of trying SilikOS beside what a computer already has (14/11/2026): the system on an external disk,
the computer's own disk untouched, and the firmware's boot menu to choose. **It has run in virtual machines, not on
a real disk or a real firmware**: the CI's external-disk test (workflow External disk; runs 43585862486, commit
fff4d24, and 43587008261, commit 27309ef, 46 checks ok and none failed; 14/11/2026) installs under UEFI onto a disk on a USB controller, beside a disk that stands for the
computer's own, and starts the result on that machine, on another with Secure Boot on, and on a third where the
disk is on SATA. What is said below was seen there unless it is marked [A].

**The installation.** The ISO's UEFI menu has a third entry, *Install SilikOS 9.8 on an external disk (the boot
order of this computer is kept)*. It is the same installation with two differences:

- the installer's own option `inst.leavebootorder`: without it the installer removes the firmware's entries that
  carry its name and adds its own **first** in the firmware's boot order; with it, it adds its entry without putting
  it in the order and removes none. Seen: the order before the installation and after it the same, no entry gone,
  one entry added (`SilikOS`) that is not in the order.
- **the computer's own disks are not shown** (since 14/11/2026, commit 27309ef): with that entry the kickstart tells
  the installer to ignore every disk that is not on USB, so *Installation Destination* lists the external disk
  (and the installer's own USB stick) and nothing else: a disk of the computer cannot be ticked by mistake. It only
  hides: the person still ticks the disk, and nothing is chosen or erased by the kickstart. An external disk that
  is not on USB (Thunderbolt, eSATA) is hidden too: the first entry of the menu is for it. Seen (run 43587008261,
  commit 27309ef): the kickstart told the installer `ignoredisk --drives=vda,vdb` (the two disks of the test
  machine that are not on USB), and the test, which names no disk and clears every disk the installer shows, left
  the computer's own disk byte for byte what it was.

The EFI system partition is made on the external disk, with the boot loader also at the path every firmware looks
for on a removable disk (`EFI/BOOT/BOOTX64.EFI`, with its fall-back program `fbx64.efi`: files of the base's package
shim-x64). Seen: the disk that stood for the computer's own (a partition table, an EFI system partition with a file
in it, data) was byte for byte what it had been, after the installation and after two starts from the external disk.

**Starting it.** From the firmware's boot menu (F12, F9, Esc: the maker's key), the external disk. Seen with the
virtual machine's firmware (OVMF), which found the disk by itself: the first start goes through `EFI/BOOT`, and
the base's shim then writes an entry of its own into the firmware, **named `almalinux`** (the name is in a file of
the base's shim package), **and puts it first**; the second start went through that entry, and nothing changed
again. So after the first start the computer starts the external disk by itself whenever it is plugged in, and
what it started before when it is not [A: a firmware skips an entry whose disk is absent; not seen on a real one].
On a machine with a TPM the shim also restarts the machine once (seen in the sealed test). To have the computer's
own system first again: the firmware's setup, or `sudo efibootmgr` (the list) and
`sudo efibootmgr -o NUMBER,NUMBER,...` (the order) from SilikOS.

**The passphrase at the boot splash.** Seen (workflow External disk, job `splash`, run 43602193388, commit 39311fa:
19 checks ok, none failed): an encrypted installation on the USB disk started the graphical way (`rhgb quiet`, as
an installation made on the installer's screens has it) shows SilikOS's splash (the ink background, the mark) with
the question `Please enter passphrase for disk ...` and its entry box, drawn through the kernel's graphics driver;
the passphrase typed once on the keyboard opens the disk. The theme and the pictures of its dialog are in the
initramfs. (Three runs before that one stayed black: the test's installer has a console on the serial port, the
installer wrote it into the installed system, and the splash program then asks there, in text. A computer has no
such console; with one, `plymouth.ignore-serial-consoles` on the kernel's command line is the base's way.)

**On another computer.** Seen: the disk as installed starts on another machine through USB (other firmware
variables, Secure Boot on, another USB controller): its initramfs has what a USB start needs. It has not what a
start from SATA or NVMe needs: the two commands `silik disk check` prints (`sudo dnf install dracut-config-generic`,
`sudo dracut -f --regenerate-all`) made one with every driver (289 kernel modules became 686, 45 MB became 90 MB),
and the same disk then started on SATA.

**What SilikOS does differently on such a disk** (silik-tools 0.10.2, silikos-power 0.2.2):

- `silik disk check` says it first: shut the system down before the disk is unplugged (pulled out while it runs,
  the running system is lost at once); encrypt it, with a passphrase (an external disk is lost more easily than a
  computer); and its initramfs is made for the computer it was installed on (the base's default), so for other
  computers the two commands it prints (the base's own package `dracut-config-generic`, then `dracut`) make one
  with every driver (seen: above).
- `silik disk tpm enroll` says that a TPM key slot opens the disk **on this computer only**: started on any other
  one, the passphrase or the recovery key. (Seen in the CI with a software TPM: another TPM, the PIN does not open
  it and the passphrase does.) A disk that travels between computers is better left with the passphrase alone.
- The saver profile (`silik power profiles silikos`) lets idle USB devices sleep; it never does so to a disk the
  running system uses (a mounted file system, swap, a volume made on it), and `silik power check` calls it
  `a disk in use`. With the system on the external disk, a USB bridge that wakes badly would take the system with it.
  Seen with the system on a USB disk: the profile applied, the disk's USB device stayed awake.
- USB protection: the disk is there when USBGuard starts, so it is allowed (`PresentDevicePolicy=allow`; seen with
  the system itself on the USB disk: the daemon active, the disk allowed). [A] A locked screen blocks only devices
  that arrive: a disk that stays plugged in is not asked again, also through a suspend, where the kernel keeps the
  device as it was (USB persist). A disk that really disconnects takes the running system with it, whatever
  USBGuard says: that is the cable's doing.

**What to expect** [A, none measured]: a solid-state disk in a USB 3 enclosure on a USB 3 port; a spinning disk or
a USB 2 port works and is slow. The weekly trim reaches the disk only through an enclosure that passes it on. The
computer's clock: Linux keeps the hardware clock in UTC and Windows in local time, so after a session in one the
other may show the wrong hour until it synchronises.

## What ran, and what did not

Ran, 14/11/2026, **in a virtual machine with KVM** (GitHub's CI, job `sealed-test`, run 43532259867: OVMF with
Secure Boot and Microsoft's keys, a software TPM, the ISO installed unattended with `autopart --encrypted` and
nothing else named; 63 checks ok):

- the installation makes LUKS2 with argon2id (aes-xts-plain64) under an LVM thin pool; the system starts with
  Secure Boot enabled, the kernel locked down, a TPM 2.0 with PCR 7 measured;
- `silik disk` there: `/`, `/home` and swap encrypted, the key slots, the TPM, Secure Boot (7 rows ok); as a user the
  key slots are `unknown` with `sudo silik disk`;
- `silik disk tpm enroll` with a PIN on the standard input (the PIN not shown), the crypttab option (the installer's
  own options on that line kept), `dracut -f` (the initramfs has the TPM support and the option), `silik disk
  recovery` (the key shown opens a key slot);
- **at the next start the PIN is asked and opens the disk**, with no passphrase (twice: two different starts);
- Enter alone and then a wrong PIN: the passphrase is asked and opens the disk;
- `silik disk tpm remove`, and after it the passphrase is asked, no PIN.

Not shown by that run, because the test itself was wrong (it had one PIN answer for a start that asks twice, and
stopped the machine): **that the PIN does not open the disk with Secure Boot off, or with another TPM, and that the
passphrase then does.** The PIN was asked a second time in both, which is what a refused PIN gives; nothing more is
known. The test is mended and has two more starts (the TPM locked, and cleared); they have not run.

Ran, 14/11/2026, in an `almalinux:9` container: what the software TPM counts as a failed try and what clears a
lockout (the section above), with tpm2-tools 5.2 and swtpm 0.8.0; not through systemd's own unlocking, which finds
its TPM only as a device of the kernel.

Ran, 13/11/2026, in an `almalinux:9` container (AlmaLinux 9.8; no loop device, no device-mapper, not privileged):

- `silik disk`, `disk check`, `disk tpm enroll` (PIN on the standard input), enrol again with another PIN, `disk
  recovery`, `disk tpm remove`, `--no-pin`, `--dry-run`, and the refusals, against a **real LUKS2 header in a plain
  file** (cryptsetup 2.8.1), the **real systemd-cryptenroll** 252-67.el9_8.6 and a **software TPM** (swtpm 0.8.0,
  reached through the TSS's `swtpm:` driver). Stand-ins: lsblk's tree (the file as the volume `/` is on), the TPM's
  sysfs files, the Secure Boot state, `dracut`. The recovery key that was printed opened a key slot (`cryptsetup open
  --test-passphrase`); `--dry-run` left the header byte for byte.
- The headers `cryptsetup luksDump --dump-json-metadata` gave there are the tests' data.
- The CI's kickstart for the encrypted installation: `ksvalidator -v RHEL9` (pykickstart 3.32.15).
- The CI test's own script, start to end, against stand-ins of QEMU and the TPM (a machine that asks and opens by the
  real one's rules; one that opens where it must not makes the test fail).
- The firmware part of that test, for real but emulated (no KVM: QEMU 8.2.2 in software, the runner's own firmware
  package ovmf 2024.02-2ubuntu0.10, swtpm 0.7.3), with the test's own QEMU options and the base's boot files on a
  small disk (shim-x64 16.1-7.el9.alma.1, GRUB 2.06, kernel 5.14.0-687.66.2.el9_8): with the firmware variables that
  have Microsoft's keys and Secure Boot on, the firmware started AlmaLinux's shim from the fall-back path, the shim
  wrote its boot entry and restarted the machine (a TPM is present), the entry "almalinux" started the shim again
  and it started GRUB; the same shim with one byte changed was refused ("Access Denied"), and was started with the
  variables that have Secure Boot off. The kernel handed to the firmware by QEMU, as the installation does, starts
  as an EFI system. No system was started beyond GRUB or the kernel's first seconds.

Not run: the two refusals above and the TPM's lockout at a start (the CI job `sealed-test`, at its next run); the
installer's screens with a person ("Encrypt my data" ticked by hand); the notification at the first login; a kernel
update with the TPM slot enrolled; `silik disk tpm enroll` typed at a terminal by a user. On real hardware:
nothing.
