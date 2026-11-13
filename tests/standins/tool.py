#!/usr/bin/env python3
# Stand-ins for the tools `silik snapshot` / `silik rollback` call, for tests/test_rollback.py: one script under the
# names snapm, boom, lvs, vgs, lvchange, dnf, rpm, grub2-reboot, grubby, kernel-install, systemctl, sudo. No LVM,
# no boot loader: they keep their "system" as files under $STANDIN (snapsets.json, lvs.json, boot/, ...), write
# every call to $STANDIN/log, and answer in the formats of the real tools:
#   snapm 0.7.0   `snapset list --json -o ...`, `snapset create --json`, errors: its own report and command code, run
#                 on EL 9.8 with made-up snapshot sets (12/11/2026); delete / revert: read in manager/_manager.py
#   boom 1.6.8    entry files and `entry delete --boot-id`: run on EL 9.8 (it wrote these files itself)
#   lvm2 2.03.33  `lvs --reportformat json`: the frame run on EL 9.8; the rows [A: the fields as strings, as snapm's
#                 lvm2 plugin reads them; no volume could exist where this was written]
#   dnf 4.14      `history list`, `check-update` exit codes: run on EL 9.8
#   grubby 8.40, grub2 2.06, systemd 252 kernel-install: their scripts read (what they write and remove)
import json
import os
import sys
import uuid as uuidlib

D = os.environ["STANDIN"]
name = os.path.basename(sys.argv[0])
args = sys.argv[1:]
MID = "0123456789abcdef0123456789abcdef"


def state(f, default=None):
    try:
        with open(os.path.join(D, f)) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save(f, v):
    with open(os.path.join(D, f), "w") as fh:
        json.dump(v, fh, indent=1)


def text(f, default=""):
    try:
        with open(os.path.join(D, f)) as fh:
            return fh.read()
    except OSError:
        return default


with open(os.path.join(D, "log"), "a") as fh:
    fh.write(json.dumps([name] + args) + "\n")
BOOT = os.path.join(D, "boot")
ENTRIES = os.path.join(BOOT, "loader/entries")
KERNEL = text("kernel").strip() or "5.14.0-611.5.1.el9_7.x86_64"

if name == "sudo":
    os.execvp(args[0], args)

PROFILES = os.path.join(BOOT, "boom/profiles")
# boom 1.6.8 wrote this file itself (`boom profile create --from-host --uname-pattern el9`, os-release NAME="SilikOS")
PROFILE = """BOOM_OS_ID="c5cca5e262791423bd215d54e560db2f1415f296"
BOOM_OS_NAME="SilikOS"
BOOM_OS_SHORT_NAME="almalinux"
BOOM_OS_VERSION="9.8 (Olive Jaguar)"
BOOM_OS_VERSION_ID="9.8"
BOOM_OS_KERNEL_PATTERN="/vmlinuz-%{version}"
BOOM_OS_INITRAMFS_PATTERN="/initramfs-%{version}.img"
BOOM_OS_ROOT_OPTS_LVM2="rd.lvm.lv=%{lvm_root_lv}"
BOOM_OS_ROOT_OPTS_BTRFS="rootflags=%{btrfs_subvolume}"
BOOM_OS_OPTIONS="root=%{root_device} ro %{root_opts}"
BOOM_OS_TITLE="%{os_name} %{os_version_id} (%{version})"
BOOM_OS_OPTIONAL_KEYS=""
BOOM_OS_UNAME_PATTERN="@PATTERN@"
"""


def profile_for(kernel):
    import re
    for f in os.listdir(PROFILES) if os.path.isdir(PROFILES) else []:
        with open(os.path.join(PROFILES, f)) as fh:
            m = re.search(r'^BOOM_OS_UNAME_PATTERN="([^"]+)"', fh.read(), re.M)
        if m and re.search(m.group(1), kernel):
            return True
    return False

if name == "snapm":
    sets = state("snapsets.json", [])
    if os.environ.get("SNAPM_FAIL") or text("snapm-fail").strip():
        print("ERROR - Command failed: " + (text("snapm-fail").strip() or "Error calling dmsetup"), file=sys.stderr)
        sys.exit(1)
    if args[:2] == ["snapset", "list"]:
        fields = args[args.index("-o") + 1].split(",") if "-o" in args else ["name", "time", "nr_snapshots", "status", "sources", "mounted"]
        rows = []
        for s in sets:
            base, _, idx = s["name"].rpartition(".")
            full = {"name": s["name"], "uuid": s["uuid"], "timestamp": s["timestamp"], "status": s.get("status", "Active"),
                    "bootable": bool(s.get("bootentry")), "bootentry": s.get("bootentry", ""), "revertentry": s.get("revertentry", ""),
                    "basename": base if idx.isdigit() else s["name"], "index": idx if idx.isdigit() and base else "-", "sources": ["/"],
                    "nr_snapshots": 1, "mounted": False, "time": "2026-11-13 06:00:00"}
            rows.append({"snapset_" + f: full[f] for f in fields})
        print(json.dumps({"Snapsets": rows}, indent=4))
        sys.exit(0)

    def entry(s, kind):
        boot_id = uuidlib.uuid5(uuidlib.NAMESPACE_DNS, s["uuid"] + kind).hex + "00000000"
        title = "%s %s 2026-11-13 06:00:00 (%s)" % ("Snapshot" if kind == "snapset" else "Revert", s["name"], KERNEL)
        root = "/dev/silikos/root-snapset_%s_%d_-" % (s["name"], s["timestamp"]) if kind == "snapset" else "/dev/silikos/root"
        opts = ("root=%s rw snapm.snapset=%s fstab=no systemd.mount-extra=/dev/silikos/home:/home:xfs:defaults" % (root, s["uuid"]) if kind == "snapset"
                else "root=%s ro snapm.revert=%s" % (root, s["uuid"]))
        os.makedirs(ENTRIES, exist_ok=True)
        with open(os.path.join(ENTRIES, "%s-%s-%s.conf" % (MID, boot_id[:7], KERNEL)), "w") as f:     # (boom 1.6.8's own text)
            f.write("#OsIdentifier: c5cca5e262791423bd215d54e560db2f1415f296\ntitle %s\nmachine-id %s\nversion %s\nlinux /vmlinuz-%s.boom0\n"
                    "initrd /initramfs-%s.img.boom0\noptions %s\n" % (title, MID, KERNEL, KERNEL, KERNEL, opts))
        return boot_id

    def unentry(boot_id):
        for f in os.listdir(ENTRIES) if os.path.isdir(ENTRIES) else []:
            if boot_id and f.startswith("%s-%s-" % (MID, boot_id[:7])):
                os.unlink(os.path.join(ENTRIES, f))

    if args[:2] == ["snapset", "create"]:
        rest, i, pos, opt = args[2:], 0, [], {}
        while i < len(rest):
            if rest[i] in ("-s", "--size-policy"):
                opt["size"] = rest[i + 1]
                i += 2
                continue
            if rest[i].startswith("-"):
                opt[rest[i].lstrip("-")] = True
            else:
                pos.append(rest[i])
            i += 1
        nm = pos[0]
        if any(c == "_" or not (c.isalnum() or c in "+.-") for c in nm):
            print("ERROR - Command failed: Snapshot set name cannot include '%s'" % next(c for c in nm if c == "_" or not (c.isalnum() or c in "+.-")), file=sys.stderr)
            sys.exit(1)
        if opt.get("autoindex") or opt.get("a"):
            idx = [int(s["name"].rpartition(".")[2]) for s in sets if s["name"].rpartition(".")[0] == nm and s["name"].rpartition(".")[2].isdigit()]
            nm = "%s.%d" % (nm, max(idx) + 1 if idx else 0)
        if any(s["name"] == nm for s in sets):
            print("ERROR - Command failed: Snapshot set named '%s' already exists" % nm, file=sys.stderr)
            sys.exit(1)
        ts = int(state("now", 1763100000))
        s = {"name": nm, "timestamp": ts, "uuid": str(uuidlib.uuid5(uuidlib.UUID("952f0e38-24a1-406d-adf6-0e9fb3c707d8"), nm + str(ts))), "status": "Active"}
        if (opt.get("bootable") or opt.get("b") or opt.get("revert") or opt.get("r")) and not profile_for(KERNEL):
            # snapm 0.7.0 with boom 1.6.8 and no OS profile for the kernel, on a system boom's heuristic does not
            # know (run on EL 9.8 with NAME="SilikOS"): the volume is made, the boot entries are not
            sets.append(s)
            save("snapsets.json", sets)
            print("ERROR - Command failed: Error calling boom to create default OsProfile: Could not determine uname pattern for 'SilikOS'", file=sys.stderr)
            sys.exit(1)
        if opt.get("bootable") or opt.get("b"):
            s["bootentry"] = entry(s, "snapset")
        if opt.get("revert") or opt.get("r"):
            s["revertentry"] = entry(s, "revert")
        s["size_policy"] = opt.get("size")
        sets.append(s)
        save("snapsets.json", sets)
        out = {"SnapsetName": nm, "Sources": ["/"], "MountPoints": ["/"], "Devices": [], "NrSnapshots": 1, "Timestamp": ts, "Time": "2026-11-13 06:00:00",
               "UUID": s["uuid"], "Status": "Active", "Categories": [], "Autoactivate": True, "OriginMounted": True, "Mounted": False,
               "Bootable": bool(s.get("bootentry"))}
        if s.get("bootentry") or s.get("revertentry"):
            out["BootEntries"] = {k: v[:7] for k, v in (("SnapshotEntry", s.get("bootentry")), ("RevertEntry", s.get("revertentry"))) if v}
        print(json.dumps(out, indent=4) if opt.get("json") else "SnapsetName:      %s" % nm)
        sys.exit(0)
    if args[:2] in (["snapset", "delete"], ["snapset", "revert"]):
        s = next((x for x in sets if x["name"] == args[2]), None)
        if s is None:
            print("ERROR - Command failed: Could not find snapshot sets matching name=%s" % args[2], file=sys.stderr)
            sys.exit(1)
        if args[1] == "delete":
            if s.get("status") == "Reverting":
                print("ERROR - Cannot operate on reverting snapshot set '%s'\nERROR - Command failed: Failed to delete snapshot set %s" % (s["name"], s["name"]), file=sys.stderr)
                sys.exit(1)
            unentry(s.get("bootentry"))
            unentry(s.get("revertentry"))
            sets.remove(s)
            # (a deleted snapshot gives its own blocks back to the pool: the tests say how much, per snapshot)
            lv = state("lvs.json", {})
            for row in lv.values():
                if row.get("lv_name") == "pool00" and "freed_per_snapshot" in row:
                    row["data_percent"] = "%.2f" % (float(row["data_percent"]) - row["freed_per_snapshot"])
            save("lvs.json", lv)
        else:
            if s.get("status") == "Reverting":
                print("ERROR - Command failed: A revert has already started for snapshot set %s" % s["name"], file=sys.stderr)
                sys.exit(1)
            unentry(s.get("bootentry"))             # (the snapshot's entry becomes invalid as the revert starts; the Revert entry stays)
            s["bootentry"] = ""
            s["status"] = "Reverting"
        save("snapsets.json", sets)
        sys.exit(0)
    sys.exit(2)

if name in ("lvs", "vgs"):
    table = state(name + ".json")
    if table is None:
        print("  Failure to communicate with kernel device-mapper driver.", file=sys.stderr)
        sys.exit(5)
    target = next((a for a in args if a.startswith("/dev/") or ("/" in a and not a.startswith("-"))), None) or next((a for a in reversed(args) if not a.startswith("-")), "")
    row = table.get(target)
    if row is None:
        print('  Volume group "%s" not found' % target, file=sys.stderr)
        sys.exit(5)
    row = {k: v for k, v in row.items() if k != "freed_per_snapshot"}
    print(json.dumps({"report": [{"lv" if name == "lvs" else "vg": [row]}]}, indent=4))
    sys.exit(0)

if name == "dnf":
    if "check-update" in args:
        sys.exit(int(text("dnf-check").strip() or 0))
    if args[:2] == ["history", "list"]:
        print(text("dnf-history"), end="")
        sys.exit(0)
    sys.exit(0)

if name == "rpm":
    if "-qa" in args:
        print(text("rpm-qa"), end="")
        sys.exit(0)
    if "kernel-core" in args:
        ks = state("kernels.json", [])
        if not ks:
            print("package kernel-core is not installed")
            sys.exit(1)
        print("\n".join(ks))
        sys.exit(0)
    sys.exit(1)

if name == "kernel-install":
    v = args[1]
    if args[0] == "remove":             # (20-grub.install and 50-dracut.install of EL 9.8: the entry and the kernel's files)
        for f in (os.path.join(ENTRIES, "%s-%s.conf" % (MID, v)), os.path.join(BOOT, "vmlinuz-" + v), os.path.join(BOOT, "initramfs-%s.img" % v),
                  os.path.join(BOOT, "System.map-" + v), os.path.join(BOOT, "config-" + v)):
            if os.path.exists(f):
                os.unlink(f)
    elif args[0] == "add":
        with open(os.path.join(ENTRIES, "%s-%s.conf" % (MID, v)), "w") as f:
            f.write("title SilikOS (%s) 9.8\nversion %s\nlinux /vmlinuz-%s\ninitrd /initramfs-%s.img\noptions root=/dev/mapper/silikos-root ro\n" % (v, v, v, v))
        open(os.path.join(BOOT, "vmlinuz-" + v), "w").close()
    sys.exit(0)

if name == "grubby":
    a = next((x for x in args if x.startswith("--set-default=")), "")
    kernel = "/" + os.path.basename(a.split("=", 1)[1])
    for f in sorted(os.listdir(ENTRIES)):
        if any(l.split() == ["linux", kernel] for l in open(os.path.join(ENTRIES, f)).read().splitlines()):
            with open(os.path.join(BOOT, "grubenv"), "a") as g:
                g.write("saved_entry=%s\n" % f[:-5])
            sys.exit(0)
    print("The param %s is incorrect" % a.split("=", 1)[1], file=sys.stderr)
    sys.exit(1)

if name == "grub2-reboot":
    with open(os.path.join(BOOT, "grubenv"), "a") as g:
        g.write("next_entry=%s\n" % args[0])
    sys.exit(0)

if name == "boom":
    if args[:2] == ["profile", "create"]:
        os.makedirs(PROFILES, exist_ok=True)
        with open(os.path.join(PROFILES, "c5cca5e262791423bd215d54e560db2f1415f296-almalinux9.8.profile"), "w") as f:
            f.write(PROFILE.replace("@PATTERN@", args[args.index("--uname-pattern") + 1]))
        print("Created profile with os_id c5cca5e:")
        sys.exit(0)
    if args[:2] == ["entry", "delete"]:
        b = args[args.index("--boot-id") + 1]
        hit = [f for f in os.listdir(ENTRIES) if f.startswith("%s-%s" % (MID, b))]
        if not hit:
            print("No matching entry found.", file=sys.stderr)
            sys.exit(1)
        for f in hit:
            os.unlink(os.path.join(ENTRIES, f))
        print("Deleted %d entr%s" % (len(hit), "ies" if len(hit) > 1 else "y"))
        sys.exit(0)
    sys.exit(2)

if name == "systemctl":
    if args[:1] == ["is-enabled"]:
        print(text("fstrim").strip() or "enabled")
    sys.exit(0)

sys.exit(0)     # (lvchange and the rest: the call is in the log)
