# Going back from an update: design, what is done and how it is used

A feasibility study of 12/11/2026 (made by an agent and reviewed); implemented on 13/11/2026 following it. The
packages and the tools were checked in an `almalinux:9` container (9.8). **No LVM or device-mapper operation and no
start could be run** on the machine where it was written (it has no device-mapper, KVM or systemd): everything that
depends on a real disk is "written, tried with stand-ins, not run" until the CI's job `rollback-test` runs
(section 5; `docs/STATUS.md` has what ran and what did not). The numeric values are a **PROPOSAL**.

## How it is used

"What happens when an update breaks my machine?" One command:

```bash
silik rollback               # puts / back as it was before the last update; asks first; does NOT restart
systemctl reboot             # starts, once, the entry "Revert ..." (silik has left it chosen)
                             # at this start `silik rollback finish` runs by itself and leaves /boot ready
```

If the system no longer starts: in the boot menu, the entry **"Snapshot silikos-update.N ..."** starts the system
as it was; there, `silik rollback` makes that state the system, and you restart.

```bash
silik snapshot               # (= status) can it go back? root volume, use and growth of the pool, snapshots, /boot
silik snapshot list          # the snapshots, from the newest to the oldest
silik snapshot create [NAME]  # one by hand (before installing an EDA tool, for example); without a name: manual.N
silik snapshot delete NAME
silik snapshot setup         # on a system already installed on LVM thin: snapm, boom-boot, the pool's profile, trim
silik rollback NAME          # to one given snapshot
silik rollback --packages    # without snapshots (a disk that is not thin): dnf history undo of the last update
silik update                 # makes the snapshot first (--no-snapshot: it does not); after a rollback, it ends the wait
silik doctor system          # row "rollback": ok / warn / unknown and what to do
```

All of them print each command they run (`$ sudo snapm ...`); `--dry-run` runs nothing (and asks for no password);
`--json` on `status` and `list`. **`/home` is never touched**; what is lost by going back is what was written to `/`
since the snapshot: packages, `/etc`, `/var`, `/opt` (the EDA installations in `/opt/eda` too).

## What is done (13/11/2026) and what is still a PROPOSAL

| Piece | State | Where |
|---|---|---|
| `silik snapshot list / create / delete / status / setup`, `silik rollback [NAME] / finish / --packages` | written; 100 tests with stand-ins of the tools; **not run on LVM** | `packages/silik-tools/files/silik`, `tests/test_rollback.py`, `tests/standins/tool.py` |
| Hook before an update (`/usr/libexec/silikos/pre-update-snapshot`), in the two update units and in `silik update` | written; run in an EL 9.8 container with the real dnf (nothing to update; something to update; dnf without network) | `packages/silikos-security` |
| The units do not run when started from a snapshot (`ConditionKernelCommandLine=!snapm.snapset`) or while waiting after a rollback | written; `systemd-analyze verify` (systemd 252) finds nothing in them | `silikos-update.service`, `silikos-security-update.service` |
| `silik rollback finish` by itself, at the "Revert" start (`silikos-rollback-finish.service`, `ConditionKernelCommandLine=snapm.revert`) | written; never started | `packages/silikos-security` |
| LVM profile `silikos-thin` (autoextension at 70 %, in steps of 20 %) | written; `lvmconfig --validate` (lvm2 2.03.33) finds it valid; **never applied to a pool** | `/etc/lvm/profile/silikos-thin.profile`; the kickstart's `%post` or `silik snapshot setup` applies it, never a package script |
| `snapm` and `boom-boot` in `%packages`; `Recommends` in `silikos-security` | they resolve in 9.8's AppStream (27 packages, 5.8 MB, in a clean container) | `kickstart/silikos.ks` |
| `[Storage] default_scheme = LVM_THINP` in the `product.img` | written, in a commit of its own (it can be reverted alone); the configuration code of anaconda 34.25.7.14 itself, run in a container with this file, reads `default_scheme` = LVM_THINP for the product SilikOS (LVM for AlmaLinux); **never installed** | `installer/product/etc/anaconda/product.d/silikos.conf`, `tests/test_installer_thin.py` |
| Status bar: `update no snapshot` / `update waiting since the rollback` (EN, CA, ES), in the same field as "restart to finish" | written; not seen in a session | `extension.js` |
| Row `rollback` in `silik doctor system`; entries `sys/snapshot`, `sys/snapshot-create`, `sys/rollback` in the COMMAND bar | written, with tests | |
| The CI's job `rollback-test` (steps 1-6, 8 and 10 of the plan) | written; the YAML parses; **not run** (`continue-on-error`) | `.github/workflows/ci.yml`, `tests/install/rollback*.sh`, `rollback*.ks.in` |
| A volume of its own for `/opt/eda`; `silik rescue usb` (ReaR); steps 7, 9, 11 and 12 of the plan; encryption; a disk with another system | **not done**: still a PROPOSAL | |

**PROPOSAL values** (`/etc/silikos/snapshot.conf`, none measured): 5 update snapshots and 14 days are kept;
no new snapshot with the pool above 70 % of data or 50 % of metadata; `size_policy = 50%FREE`.

### Where it departs from the design of section 3, and why

- **Without `snapm schedule`.** A snapm schedule carries a timer of its own and a single pruning policy (count
  *or* age). Here the snapshot is made only before an update and the pruning wants both rules: it is created with
  `snapm snapset create --bootable --revert --autoindex silikos-update /` and pruned with `snapm snapset delete`
  (only the `silikos-update.N` ones; one made by hand is never pruned; the newest is always kept).
- **An explicit `--size-policy` (`50%FREE`).** By default snapm asks the pool for free space for twice what `/`
  takes (`200%USED`, read in `snapm(8)` and in `_snapm.py`): a half-full pool never has it and the snapshot would fail.
  `100%FREE` is of no use either: snapm rounds up to a sector and refuses itself (run with the
  `SizePolicy` of snapm 0.7.0: it asks for 35944689152 bytes when 35944688675 are free). A thin snapshot takes
  nothing when it is created; what protects the pool are the two thresholds and the autoextension.
- **`silik` makes boom's profile** before the first snapshot (`boom profile create --from-host
  --uname-pattern el9`). snapm creates it by itself only for the names boom knows (Red Hat Enterprise Linux, CentOS
  Stream, Fedora); with `NAME="SilikOS"` in `/etc/os-release` it fails *after* having made the volume: `Could not
  determine uname pattern for 'SilikOS'` (run with the code of snapm 0.7.0 and boom 1.6.8 on EL 9.8). The profile
  is made only in a normal start: it takes the options of that start's kernel command line.
- **After a rollback the automatic updates wait** (`/etc/silikos/update.hold`, which `finish` writes): otherwise,
  the next day at 6 what broke the machine would be installed again. `silik update` (by hand,
  with a snapshot first) ends the wait; the status bar and `silik doctor` say so. **The owner's decision**: the
  rule was "the system updates itself".
- **`finish` also puts back** the entry of a kernel that the reverted package database knows and that
  the update had removed from `/boot` (`kernel-install add`), besides removing those of the ones it does not know
  (`kernel-install remove`, what the `%preun` of the kernel's package does), setting the default kernel
  (`grubby --set-default`) and deleting the entries of the snapshot that no longer exists (`boom entry delete`).
- **`silik rollback` from the started snapshot itself** is allowed (it is the case "the machine no longer starts");
  what is refused when started from a snapshot is making another one and updating.
- **If it cannot be known whether there are updates** (dnf without network), no snapshot is made "just in case";
  the note is left and `pre-update-snapshot settle`, afterwards, removes it if in the end no package has changed.
- **What each snapshot takes** is not shown: `lvs` does not give the exclusive space of a thin snapshot (it would
  need `thin_ls`). `status` shows the pool's use, how many there are and what the kernel copies take in `/boot`.

### What was read of the tools (and what had to be assumed)

Read or run on EL 9.8 (container, 13/11/2026):
- **snapm 0.7.0**: the options of `snapset create/delete/revert/list` (`command.py`, `snapm(8)`); the JSON of
  `snapset list --json -o ...`, generated by its own report code with made-up sets; valid names (no
  `_`); `snapm.snapset=UUID` and `snapm.revert=UUID` on the kernel command line; the revert deletes the "Snapshot"
  entry and leaves the "Revert" one; without device-mapper it ends with `ERROR - Command failed: ...` and code 1; the
  "Snapshot" entry mounts the rest of `/etc/fstab` (`/boot`, `/home`) with `systemd.mount-extra`
  (`build_snapset_mount_list`); its `SizePolicy` and the creation of boom's profile were run (above).
- **boom 1.6.8**: it wrote the entries itself (`MACHINEID-BOOTID7-VERSION.conf`, without an `id` key), the copy
  of the kernel and the initramfs (`/boot/boom/cache/SHA1.img` and `vmlinuz-VERSION.boom0`: two copies per image,
  none if it already has it), and `boom entry delete --boot-id ID` (the options go after `entry delete`).
- **lvm2 2.03.33**: `lvs --reportformat json --units b --nosuffix -o ...,lv_profile`, `lvchange --metadataprofile`,
  `--monitor y`; the profile is valid and an option that is not allowed in a profile makes it be refused.
- **dnf 4.14**: `check-update` exits with 100 / 0 / 1; `--security` works with it; the transaction of `dnf-automatic`
  appears in `dnf history list` with an empty command line and "Upgrade"; a real `dnf history undo` (done).
- **grubby 8.40, grub2 2.06, systemd 252's kernel-install, 20-grub.install, 50-dracut.install**: read (what
  they write and what they delete; installing any kernel makes it the default) and **run**: `silik rollback
  finish` in a container with a `/boot` made by hand (a kernel that the package database does not know, without
  modules, and the default): `kernel-install remove` removes its entry and its files, `grubby --set-default` leaves
  the known kernel as the default; `grub2-reboot ID` writes `next_entry=ID` in `grubenv`.
- **anaconda 34.25.7.14**: `default_scheme = LVM_THINP` in `[Storage]` (in `anaconda.conf`, `rhvh.conf`,
  `ovirt.conf`); `autopart` without `--type` takes this value (`automatic_module.py`); its configuration code,
  run with our product file, gives LVM_THINP for SilikOS.

Assumed, not seen anywhere it could be run (**[A]**):
- [A] A thin volume is recognised in sysfs as a device with a uuid `LVM-` that has the pool's `-tpool` under it
  (`/sys/dev/block/M:m/slaves/*/dm/name`). It is what `silik` uses so as not to ask for root; if it is not so, it
  will say "not available" on a disk that is.
- [A] grub2 takes the file name without `.conf` as the identifier of an entry: it is what `grubby` saves in
  `saved_entry` (seen) and what `silik` gives to `grub2-reboot`; that grub2 starts it is seen only by starting. If
  not, the next start will not be "Revert", and `silik` already says which one to choose by hand.
- [A] The rows of `lvs --reportformat json` (values as text, `lv_profile` empty if there is none): only its
  frame was seen, without any volume.
- [A] In the kickstart's `%post` (the installer's chroot), `findmnt /` and `lvs` see the root volume. If not, the
  profile is not applied: `silik snapshot status` warns of it and `silik snapshot setup` fixes it.
- [A] The merge of a thin snapshot of `/` ends when the volume is activated at the "Revert" start, before
  `finish` runs. If it has not ended yet, `finish` leaves the entries and has to be run again (the test detects it).
- [A] `snapm snapset revert` asked from the started snapshot itself (mounted as `/`): the merge is left
  for the next activation of the volume (it is what LVM's documentation says for an origin or a snapshot in use).
- [A] SELinux lets the snapshot and `finish` be done from a systemd service (they run unconfined, as
  `dnf-automatic` does); no policy of our own.
- [A] The reserve the installer leaves in the volume group (the test reports its percentage and requires only ≥ 5 %).
- [A] On a GitHub runner, the installation on an 80 GB disk (sparse) creates `/home`.

### What is left after uninstalling

`rpm -e silikos-security` removes all the new files (checked in a container). What is left, because they are not
files of the package: the snapshots there are (LVM volumes and their boot entries: `snapm snapset list`,
`snapm snapset delete`) and the profile's name on the pool (`lvchange --detachprofile VG/POOL`).

## Recommendation

**LVM thin by default + `snapm` + `boom-boot`.** Both tools are in AlmaLinux 9.8's AppStream and the base need not
be touched. Before each automatic update a thin snapshot of `/` is made, with a boot entry, and
`silik rollback` reverts it.

If the disk is not LVM thin: `dnf history undo` (with clear limits) and, optionally, a rescue USB stick with ReaR.

**Discarded:**
- Snapper: it does not exist in EL 9 or in EPEL 9.
- Btrfs: EL 9's kernel does not carry its module.
- Stratis: it is a Technology Preview and the installer cannot put it on `/`.
- The `snapshot` role of rhel-system-roles: it needs Ansible.

## 1. What EL 9.8 offers (checked in the container)

| Package | Version | Note |
|---|---|---|
| `snapm`, `python3-snapm` | 0.7.0-2.el9 (appstream) | Snapshot sets: plugins lvm2-thin, lvm2-cow and stratis. Commands `create --bootable --revert`, `revert`, `schedule` (with GC by count or age), `mount` and `diff` |
| `boom-boot` | 1.6.8-1.el9 (appstream) | Boot entries (BLS) for the snapshots |
| `lvm2` | 2.03.33-4.el9_8.1 | By default: no autoextension of the pool, discards in passdown |
| `rear` | 2.6-28.el9 | Rescue image |
| `snapper`, `leapp` | — | Not there (BaseOS, AppStream, CRB, extras, EPEL) |
| `btrfs-progs` | only in EPEL | The kernel does not carry `btrfs.ko` |

- **The boot entry copies the running kernel** (vmlinuz + initramfs) to `/boot`. That way it survives when dnf
  deletes the kernel, but it costs space in `/boot` (1 GiB).
- **The revert is an `lvconvert --merge`**, which ends when the "Revert" entry is started. When it ends, the snapshot is gone.
- **The entry carries `snapm.snapset=` or `snapm.revert=` on the kernel command line.** This makes it possible never
  to update when started from a snapshot.
- **`fstrim.timer` is not enabled by default.** Without discard, the pool does not free the deleted blocks.
- **`dnf history undo` works** (tried: downgrading glibc and tzdata and upgrading them again, scriptlets included). But it
  fails if the old versions are no longer in the repository, for example after a change of minor release, when they move to the vault.

## 2. Installer: LVM thin without the kickstart choosing the disk

- **Not `autopart --type=thinp` in the kickstart.** In an automatic installation, the installer ticks **all** the disks
  (`select_default_disks()`, anaconda 34.25). That would break the rule.
- **The right place is the `product.img`.** In `installer/product/etc/anaconda/product.d/silikos.conf`:
  ```
  [Storage]
  default_scheme = LVM_THINP
  ```
  It is what RHV Node and oVirt do. The user still chooses the disk; "Automatic" then makes LVM thin.
- **What it creates:**
  - a thin pool with `/` (max. 70 GiB) and `/home`;
  - ordinary swap;
  - 20 % of the group free (min. 1 GiB, max. 100 GiB) to let the pool grow.
- **If the user chooses a scheme by hand** (ordinary LVM or plain XFS): the alternative method.
- **[A] It has to be looked at in the VM** whether, with `inst.ks=`, the destination screen comes up with all the disks
  ticked. It affects the rule "the kickstart never chooses a disk" even if we do not use thin.

## 3. Design (that of 12/11/2026; what was done and where it departs from it is above)

**Packages:** `snapm` and `boom-boot` in `%packages`. They are packages of the base and change nothing of it.

**Before each update** (`ExecStartPre=/usr/libexec/silikos/pre-update-snapshot`, and also in `silik update`):
1. `dnf check-update`: if there is nothing to update, it does nothing.
2. If there is, it makes the snapshot (`snapm snapset create-scheduled -c silikos-update`), bootable and revertible, of `/`.
3. Then it prunes (`snapm schedule gc`), keeping the last 5 and 14 days (PROPOSAL).
4. If the snapshot fails, the update is made all the same, because security comes first. The status bar says
   "update: no snapshot" (the owner's decision).

**Barriers:**
- No snapshot with the pool above 70 % of data or 50 % of metadata: first it prunes, then it warns.
- An LVM profile of our own (`/etc/lvm/profile/silikos-thin.profile`) applied to the pool: autoextension at 70 %, in
  steps of 20 %, drawing on the reserve. It does not touch `/etc/lvm/lvm.conf`.
- `fstrim.timer` enabled.
- If started from a snapshot, the update services do not run
  (`ConditionKernelCommandLine=!snapm.snapset`).

**Commands:**
- `silik snapshot list | create | delete | status`. The status shows the pool's use, what each snapshot takes and the
  use of `/boot`.
- `silik rollback [NAME]`: it reverts and sets the "Revert" entry as the next start (`grub2-reboot`). **It does not
  restart**: it only says so.
- `silik rollback finish`: it runs by itself at the first start after the revert.
  - It deletes the boot entries of the kernels that the reverted package database no longer knows.
  - It sets the default kernel again.
  - **Without this step, the default entry would point to a kernel without modules and would not start.**

**What is not touched or not reverted:**
- **`/home`:** it is a separate volume and is never touched. But it shares the pool: if the pool fills up, `/home` suffers too.
- **`/opt/eda` and `/var`:** they are on `/`. A rollback undoes the EDA installations and root's containers, and a
  large EDA installation swells the snapshots. PROPOSAL: a volume of its own for `/opt/eda` (it has to be seen whether
  the default partitioning allows it).
- **`/boot/efi`:** it is not reverted. If grub2 or shim were updated, they stay new. It is harmless, but it has to be
  documented.

**Alternative method** (a disk that is not thin):
- `silik rollback --packages` = `dnf history undo` of the last automatic update. Limits:
  - there are no old versions after a change of minor release;
  - it does not undo the configuration or the effects of the scriptlets;
  - the kernel is only removed, the old one is not put back;
  - downgrading glibc or systemd needs a restart.
- `silik rescue usb`: ReaR on a USB stick that the user formats. `rear recover` creates the disk again and erases it: only
  in recovery and with confirmation.

## 4. Effort and risk

**Effort: about 2 weeks** [A].

| Piece | Days |
|---|---|
| `product.img`, `%packages`, LVM profile, fstrim, conditions | 0.5 |
| `silik snapshot` / `rollback` / `finish`, update hook, status bar, EN/CA/ES texts, tests | 4–5 |
| ReaR and `dnf history undo` | 1–2 |
| Tests in a VM | 3–4 |

**Risks:**
- snapm is still 0.x and has had recent bugs (RHEL-127542: a rename left orphan entries).
- `/boot` and `/` can end up out of step.
- **A full pool:** XFS stops and `/home` goes down with it.
- A 1 GiB `/boot`, with the kernel copies.
- A duplicate XFS UUID if the origin and the snapshot are mounted at the same time.

## 5. Test plan in a real VM (a Ryzen with KVM, or a CI runner with KVM)

**The job `rollback-test`** (`.github/workflows/ci.yml`, `tests/install/rollback.sh`) does steps 1-6, 8 and 10 in
virtual machines with the ISO, and each step is an annotation of the run (`::notice` if it passes, `::error` with the
first check that fails):
- It installs with the ISO's kickstart and an `autopart` **without a scheme** (what comes out is the default value of
  the `product.img`), on an 80 GB disk, and starts the system four times (`rollback-check.sh`, one stage each
  time; the stage is kept in `/boot`, which is not inside the snapshot):
  1. a normal start: thin layout, `silik snapshot create`, pruning (7 more snapshots, 5 are left), `tzdata`,
     `expat`, `libxml2` and `sqlite-libs` are downgraded on purpose and `silikos-update.service` is run (the snapshot
     must appear in the journal before the update); another kernel is installed *after* the snapshot;
  2. a start of the "Snapshot" entry: `/` is the snapshot, `/home` the original, nothing is updated, `silik
     rollback` from there;
  3. the "Revert" start: old versions, the merge ended, `finish` has run by itself, the kernel installed afterwards
     is no longer in `/boot`, **the default kernel has its modules**, the updates wait;
  4. a normal start: the default kernel runs with modules, `silik update` ends the wait with a snapshot first.
- A second, small installation on ordinary partitions: `silik snapshot` says "not available", the update is
  made all the same and `silik rollback --packages` goes back to the old versions.
- It does not do: encryption, a disk with another system, which disks come up ticked with `inst.ks` (step 1), a full
  pool (7), measurements (9), ReaR (10), a change of minor release (11), a power cut (12).
- It is `continue-on-error` until it has passed: it cannot stop the ISO or a release.

1. **Installation:**
   - The ISO with `LVM_THINP`, the disk chosen by hand, Automatic; `lvs -a` must show the pool, `/` and `/home` thin,
     ordinary swap and ~20 % free in the group.
   - Repeat with encryption, and on a disk with another system.
   - Which disks come up ticked with `inst.ks`.
2. **Snapshot:** `silik snapshot create`, and look at `lvs`, `boom list`, `snapm snapset list` and `df /boot`.
3. **Update:** downgrade kernel, glibc, systemd and gnome-shell on purpose, and run `silikos-update.service`. The
   snapshot must be made first (journal).
4. **Start the snapshot:** `/` is the snapshot, `/home` is the original, nothing is updated, and the desktop works.
5. **Rollback:**
   - `silik rollback`, and restart into "Revert".
   - `rpm -q` with the old versions, the merge ended and `finish` has cleaned the entries.
   - The default kernel has its modules.
6. **Rollback after starting a new kernel:** the old one starts, without orphan entries.
7. **A full pool:**
   - Fill `/` up to the threshold: the autoextension, the pruning and the warning must work.
   - Go over it on purpose: see what XFS does and how it recovers.
8. **Pruning:** 10 sets with a limit of 5. The entries and the copies in `/boot` must be deleted.
9. **Cost to measure:**
   - the time to create a snapshot;
   - the % of the pool per daily update during a week, with fstrim and without;
   - fio 4k random with 0, 1 and 5 snapshots;
   - `systemd-analyze`.
10. **A disk that is not thin:**
    - `silik snapshot` says "not available";
    - `dnf history undo`;
    - ReaR to a virtual USB stick and `recover` to a second, empty disk.
11. **Change of minor release:** from 9.8 to 9.9, with snapshot and rollback.
12. **Cut the power in the middle of a merge:** at the next start the merge must go on.

Sources:
- https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/configuring_and_managing_logical_volumes/managing-system-upgrades-with-snapshots_configuring-and-managing-logical-volumes
- https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/9/html/managing_storage_devices/managing-system-upgrades-with-snapshots_managing-storage-devices
- https://issues.redhat.com/browse/RHEL-36667
- https://issues.redhat.com/browse/RHEL-127542
- https://github.com/snapshotmanager/snapm
- https://boom.readthedocs.io/en/latest/user_guide.html
- https://fedoraproject.org/wiki/Changes/StratisAnacondaSupport
- https://bugzilla.redhat.com/show_bug.cgi?id=2135427
- https://repo.almalinux.org/almalinux/9/
