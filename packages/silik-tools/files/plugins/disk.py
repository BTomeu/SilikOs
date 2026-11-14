# silik-plugin: disk
# help: data at rest: what is encrypted (LUKS), TPM and Secure Boot, unlock with TPM2 + PIN, a recovery key. Never formats
# words: check tpm recovery grow --json
# words tpm: enroll remove
# state: experimental: run in virtual machines (an encrypted installation started with Secure Boot and a software TPM; a system on a USB disk); no real machine yet
"""silik disk [--json]                    what is encrypted: /, /home, swap; the LUKS volume (version, cipher, key slots,
                                       tokens), the TPM, Secure Boot, what opens the disk at a start
silik disk check [--json]              the same, and what to do so that the disk is neither opened nor lost: each
                                       command printed, none run (a copy of the header, a recovery key...)
silik disk tpm enroll [DEVICE]         a TPM2 key slot with a PIN, bound to the Secure Boot state (PCR 7); the option
        [--yes] [--no-pin] [--even-without-secure-boot] [--pcrs 7] [--unlock-key-file FILE]
                                       in /etc/crypttab; the initramfs made again. The passphrase slot stays
silik disk tpm remove [DEVICE] [--yes] the TPM2 slot wiped, the option out of /etc/crypttab, the initramfs made again
silik disk recovery [DEVICE] [--yes] [--unlock-key-file FILE]
                                       one more key slot with a generated recovery key, shown once
silik disk grow [--yes]                the system on the whole disk it is on: the last partition up to the end of
                                       the disk, the LVM volume (its thin pool first) and the file system of / with
                                       it. For a system written from a disk image onto a larger disk. Nothing is
                                       moved or formatted
silik disk notice [--again]            at a login (silik-tools' autostart entry): a disk that is not encrypted is said
                                       once, as a notification; nothing when it is encrypted

Never formats, never encrypts or re-encrypts, never removes a passphrase or recovery slot. `grow` only ever makes
the last partition of the disk / is on larger, into space nothing uses. The volume is found from
the running system (what / is on); a DEVICE typed must be a LUKS volume of this machine; the device is printed and
asked about before anything is written (--yes for scripts).

At a terminal the base's systemd-cryptenroll asks for the passphrase and the new PIN itself. From a script: the
passphrase in --unlock-key-file (or $PASSWORD, which systemd-cryptenroll reads), the PIN as the first line of the
standard input (handed on in $NEWPIN, never on a command line).

What it protects against and what it does not: docs/DISK.md."""
import json
import os
import re
import sys

SILIK = None
CRYPTTAB = "/etc/crypttab"
SYS_TPM = "/sys/class/tpm"
TPM2_DEVICE = "auto"          # what systemd-cryptenroll's --tpm2-device= gets
PCRS = "7"                    # the Secure Boot state: on or off, and the keys of the firmware (PK, KEK, db, dbx)
LSBLK = ["lsblk", "-J", "-o", "NAME,KNAME,PATH,TYPE,FSTYPE,FSVER,UUID,MOUNTPOINTS,TRAN"]
TOKENS = {"systemd-tpm2": "tpm2", "systemd-recovery": "recovery", "systemd-fido2": "fido2", "systemd-pkcs11": "pkcs11"}
KIND = {"passphrase": "passphrase", "recovery": "recovery key", "tpm2": "TPM2", "fido2": "FIDO2 token", "pkcs11": "smart card"}
NO_COMMAND = ("no command of SilikOS encrypts a disk that is in use: it is chosen at installation "
              "(Installation Destination > Encrypt my data); docs/DISK.md")
NO_PIN = ("without a PIN the TPM gives the key to this machine whenever it starts with the same Secure Boot state: "
          "the disk opens by itself for whoever holds the machine, and only the login screen stands between them and "
          "the data. A thief has as long as they want with it. docs/DISK.md")
PLACES = ("/boot", "/run/media", "/media", "/mnt")          # not judged: the boot files, and what a person plugs in
NOTICE = {
    "en": "Not encrypted: %s. Whoever holds this computer reads everything on it. Encryption is chosen at installation "
          "(Installation Destination > Encrypt my data). In a terminal: silik disk",
    "ca": "Sense xifrar: %s. Qui tingui aquest ordinador a les mans en llegeix tot el contingut. El xifratge es tria en "
          "instal·lar (Installation Destination > Encrypt my data). En un terminal: silik disk",
    "es": "Sin cifrar: %s. Quien tenga este ordenador en las manos lee todo su contenido. El cifrado se elige al "
          "instalar (Installation Destination > Encrypt my data). En un terminal: silik disk",
}


# ------------------------------------------------------------------------------------------- what the system has

def lsblk(silik):
    """lsblk's tree of block devices, None when it cannot be read"""
    rc, out = silik.sec_cmd(LSBLK)
    if rc != 0:
        return None
    try:
        return json.loads(out).get("blockdevices") or []
    except ValueError:
        return None


def walk(nodes, above=()):
    """every (device, the devices it is made on: outermost first) of lsblk's tree; a device made on two (a mirror, a
    thin pool's data and metadata) comes once under each"""
    for n in nodes or []:
        yield n, above
        for x in walk(n.get("children"), above + (n,)):
            yield x


def mounted(n):
    return [m for m in (n.get("mountpoints") or [n.get("mountpoint")]) if m]


def luks_version(fsver):
    return int(fsver) if str(fsver or "").isdigit() else None


def layout(tree, proc_swaps=""):
    """{"mounts": {mount point: {device, encrypted, luks: [devices], tran: [how its disks are attached: "usb", "nvme",
    "sata"..., as lsblk says of the outermost device]}}, "swap": [{device, kind, encrypted}],
    "luks": {device: {device, kname, uuid, version, name}}} from lsblk's tree and /proc/swaps. encrypted: a dm-crypt
    layer is under every device the file system is made on (None for zram: memory, nothing at rest)"""
    mounts, swap, luks = {}, {}, {}
    for n, above in walk(tree):
        chain = above + (n,)
        if n.get("fstype") == "crypto_LUKS" and n.get("path"):
            d = luks.setdefault(n["path"], {"device": n["path"], "kname": "/dev/" + n["kname"] if n.get("kname") else "", "uuid": n.get("uuid") or "",
                                            "version": luks_version(n.get("fsver")), "name": ""})
            for c in n.get("children") or []:
                if c.get("type") == "crypt":
                    d["name"] = c.get("name") or ""
        ms = mounted(n)
        if not ms:
            continue
        enc = any(x.get("type") == "crypt" for x in chain)
        under = [x["path"] for x in chain if x.get("fstype") == "crypto_LUKS" and x.get("path")]
        for m in ms:
            if m == "[SWAP]":
                zram = (n.get("name") or "").startswith("zram")
                e = swap.setdefault(n.get("path") or "", {"device": n.get("path") or "", "kind": "zram" if zram else "device", "encrypted": True})
            else:
                e = mounts.setdefault(m, {"device": n.get("path") or "", "encrypted": True, "luks": [], "tran": []})
                if chain[0].get("tran") and chain[0]["tran"] not in e["tran"]:
                    e["tran"].append(chain[0]["tran"])
                for u in under:
                    if u not in e["luks"]:
                        e["luks"].append(u)
            e["encrypted"] = e["encrypted"] and enc
    for s in swap.values():
        if s["kind"] == "zram":
            s["encrypted"] = None
    for l in proc_swaps.splitlines()[1:]:          # a swap file is as its file system is
        f = l.split()
        if len(f) >= 2 and f[1] == "file":
            on = max((m for m in mounts if m == "/" or f[0].startswith(m.rstrip("/") + "/")), key=len, default="")
            swap[f[0]] = {"device": f[0], "kind": "file", "encrypted": mounts[on]["encrypted"] if on else None}
    return {"mounts": mounts, "swap": sorted(swap.values(), key=lambda s: s["device"]), "luks": luks}


def parse_dump(d):
    """what `cryptsetup luksDump --dump-json-metadata` says of a LUKS2 volume: {cipher, key_bits, sector, slots:
    [{slot, kind, kdf} + for a TPM2 slot {pin, pcrs, bank}]}. A slot no token points at is a passphrase's (or a key
    file's: the header does not tell them apart)"""
    by_slot = {}
    for _, t in sorted((d.get("tokens") or {}).items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        for s in t.get("keyslots") or []:
            by_slot[str(s)] = t
    slots = []
    for sid in sorted(d.get("keyslots") or {}, key=lambda s: int(s) if s.isdigit() else 0):
        k, t = d["keyslots"][sid], by_slot.get(sid)
        ty = (t or {}).get("type", "")
        row = {"slot": int(sid) if sid.isdigit() else sid, "kind": (TOKENS.get(ty) or ty or "token") if t else "passphrase",
               "kdf": (k.get("kdf") or {}).get("type", "")}
        if row["kind"] == "tpm2":
            row.update(pin=bool(t.get("tpm2-pin")), pcrs=[int(p) for p in t.get("tpm2-pcrs") or [] if str(p).isdigit()],
                       bank=t.get("tpm2-pcr-bank", ""))
        slots.append(row)
    seg = next(iter(sorted((d.get("segments") or {}).items())), ("", {}))[1]
    bits = [8 * k.get("key_size", 0) for k in (d.get("keyslots") or {}).values() if k.get("key_size")]
    return {"cipher": seg.get("encryption", ""), "key_bits": bits[0] if bits else None, "sector": seg.get("sector_size"), "slots": slots}


def luks_read(silik, dev):
    """parse_dump of DEV, None when it may not be read (root only) or is not LUKS2"""
    rc, out = silik.sec_cmd(["cryptsetup", "luksDump", "--dump-json-metadata", dev])
    if rc != 0:
        return None
    try:
        return parse_dump(json.loads(out))
    except (ValueError, AttributeError, TypeError):
        return None


def tpm(root=None):
    """{present, version, pcr7: measured | empty | unknown}. PCR 7 is what the firmware measured of the Secure Boot
    state; one the firmware never wrote to is all zeros (or all ones), and a key bound to it is bound to nothing"""
    d = os.path.join(root or SYS_TPM, "tpm0")
    v = SILIK.read(os.path.join(d, "tpm_version_major")).strip()
    p = SILIK.read(os.path.join(d, "pcr-sha256", "7")).strip().lower()
    state = "unknown" if not p else "empty" if set(p) <= {"0"} or set(p) <= {"f"} else "measured"
    return {"present": os.path.isdir(d), "version": v, "pcr7": state}


def crypttab_find(text, vol):
    """(line number, its fields) of the volume in a crypttab's text: by its UUID, its device or its name"""
    uuid, names = (vol.get("uuid") or "").lower(), [x for x in (vol.get("device"), ) if x]
    for i, l in enumerate(text.splitlines()):
        f = l.split()
        if len(f) < 2 or f[0].startswith("#"):
            continue
        d = f[1].lower()
        if (uuid and d in ("uuid=" + uuid, 'uuid="%s"' % uuid, "/dev/disk/by-uuid/" + uuid)) or f[1] in names or (vol.get("name") and f[0] == vol["name"]):
            return i, f
    return None, None


def crypttab_set(text, vol, on):
    """the crypttab's text with tpm2-device=auto among the volume's options (ON) or without it; None when the volume
    has no line there. The other lines are not touched"""
    i, f = crypttab_find(text, vol)
    if i is None:
        return None
    opts = [o for o in (f[3].split(",") if len(f) > 3 else []) if o and not o.startswith("tpm2-device=")]
    if on:
        opts.append("tpm2-device=" + TPM2_DEVICE)
    f = f[:2] + [f[2] if len(f) > 2 else "none"] + ([",".join(opts)] if opts else [])
    lines = text.splitlines()
    lines[i] = " ".join(f)
    return "\n".join(lines) + "\n"


def crypttab_tpm2(text, vol):
    """True / False: the volume's line has tpm2-device=; None: no line, or the file is not readable"""
    _, f = crypttab_find(text or "", vol)
    if f is None:
        return None
    return any(o.startswith("tpm2-device=") for o in (f[3].split(",") if len(f) > 3 else []))


def initramfs_tpm2(silik):
    """True / False: the running kernel's initramfs has dracut's tpm2-tss module; None: not readable (root only)"""
    rc, out = silik.sec_cmd(["lsinitrd", "-m"], timeout=90)
    if rc != 0 or not out:
        return None
    return "tpm2-tss" in out.split()


def probe(silik, deep=None):
    """the state every command starts from. DEEP: also what only root may read (the LUKS headers, the initramfs);
    default: when this runs as root"""
    deep = os.geteuid() == 0 if deep is None else deep
    tree = lsblk(silik)
    lay = layout(tree or [], silik.read("/proc/swaps"))
    tab = silik.read(CRYPTTAB, None)
    vols = []
    for dev in sorted(lay["luks"]):
        v = dict(lay["luks"][dev], read=False, cipher="", key_bits=None, sector=None, slots=[], crypttab_tpm2=crypttab_tpm2(tab, lay["luks"][dev]) if tab is not None else None)
        got = luks_read(silik, dev) if deep and v["version"] != 1 else None
        if got:
            v.update(got, read=True)
        vols.append(v)
    return {"root": os.geteuid() == 0, "seen": tree is not None, "container": silik.sec_container(), "mounts": lay["mounts"],
            "swap": lay["swap"], "luks": vols, "tpm": tpm(), "secure_boot": silik.sec_secureboot(silik.sec_container()),
            "initramfs_tpm2": initramfs_tpm2(silik) if deep and vols else None}


# ------------------------------------------------------------------------------------------- what it means

def slot_text(s):
    t = KIND.get(s["kind"], s["kind"])
    if s["kind"] == "tpm2":
        t += " + PIN" if s.get("pin") else " without a PIN"
        t += " (PCR %s)" % "+".join(str(p) for p in s["pcrs"]) if s.get("pcrs") else " (no PCR: bound to no state of the machine)"
    elif s["kind"] == "passphrase" and s.get("kdf"):
        t += " (%s)" % s["kdf"]
    return "%s %s" % (s["slot"], t)


def volume_of(st, mp):
    """the mount point's entry, /home's being /'s when it has no file system of its own"""
    return st["mounts"].get(mp) or (st["mounts"].get("/") if mp == "/home" else None)


def rows(st):
    """the audit: [{id, name, state, value, fix}] as `silik secure status` has them"""
    out = []

    def row(i, name, state, value, fix=()):
        out.append({"id": i, "name": name, "state": state, "value": value, "fix": list(fix) if state != "ok" else []})

    here = " (inside a container)" if st["container"] else ""
    sudo = [] if st["root"] else ["sudo silik disk"]
    for mp in ("/", "/home"):
        m = volume_of(st, mp)
        if m is None or not m["device"].startswith("/dev/"):
            row(mp, mp, "unknown", "not on a block device seen from here" + here)
        elif mp == "/home" and "/home" not in st["mounts"]:
            row(mp, mp, "ok" if m["encrypted"] else "bad", "in the file system of /")
        elif m["encrypted"]:
            row(mp, mp, "ok", "encrypted: %s is on %s" % (m["device"], ", ".join(m["luks"]) or "a dm-crypt volume that is not LUKS"))
        else:
            row(mp, mp, "bad", "%s is not encrypted: whoever holds the machine reads it" % m["device"], [NO_COMMAND])
    sw = st["swap"]
    plain = [s["device"] for s in sw if s["encrypted"] is False]
    if plain:
        row("swap", "swap", "bad", "%s: not encrypted, and what was in memory (keys, open documents) is written there" % ", ".join(plain), [NO_COMMAND])
    elif not sw:
        row("swap", "swap", "ok", "none")
    elif any(s["encrypted"] is None and s["kind"] != "zram" for s in sw):
        row("swap", "swap", "unknown", ", ".join(s["device"] for s in sw))
    else:
        row("swap", "swap", "ok", ", ".join("%s (%s)" % (s["device"], "in memory: nothing at rest" if s["kind"] == "zram" else "encrypted") for s in sw))
    other = sorted((mp, m["device"]) for mp, m in st["mounts"].items()
                   if not m["encrypted"] and m["device"].startswith("/dev/") and mp not in ("/", "/home") and not mp.startswith(PLACES))
    if other and "/" in st["mounts"]:
        row("other", "other", "warn", "also mounted and not encrypted: " + ", ".join("%s (%s)" % o for o in other), [NO_COMMAND])
    for v in st["luks"]:
        name = "LUKS " + v["device"]
        if v["version"] == 1:
            row("luks", name, "warn", "LUKS1: its passphrase is stretched with PBKDF2 (cheap to guess on graphics cards) and it takes no TPM slot",
                ["cryptsetup convert %s --type luks2    (with the volume closed: from another system; not done here)" % v["device"]])
        elif not v["read"]:
            row("luks", name, "unknown", "LUKS%s; its key slots are read as root" % (v["version"] or ""), sudo)
        else:
            weak = [s for s in v["slots"] if s["kind"] == "passphrase" and s["kdf"] not in ("argon2id", "argon2i")]
            val = "LUKS2, %s%s; key slots: %s" % (v["cipher"], ", %d-bit key" % v["key_bits"] if v["key_bits"] else "", ", ".join(slot_text(s) for s in v["slots"]))
            if weak:
                row("luks", name, "warn", val, ["sudo cryptsetup luksConvertKey --pbkdf argon2id %s    (asks the passphrase; PBKDF2 is cheap to guess on graphics cards)" % v["device"]])
            else:
                row("luks", name, "ok", val)
    t = st["tpm"]
    if not t["present"]:
        row("tpm", "TPM", "unknown" if st["container"] else "ok", "none seen" + (here or ": the disk opens with its passphrase"))
    elif t["version"] != "2":
        row("tpm", "TPM", "ok", "version %s: not usable for the disk (TPM 2.0 is)" % (t["version"] or "unknown"))
    else:
        row("tpm", "TPM", "ok", "2.0; PCR 7 (the Secure Boot state) %s" % {"measured": "is measured", "empty": "was never written by the firmware", "unknown": "not readable"}[t["pcr7"]])
    sb = st["secure_boot"]
    if sb == "enabled":
        row("secureboot", "Secure Boot", "ok", "on")
    elif sb is None:
        row("secureboot", "Secure Boot", "unknown", "not visible" + here)
    else:
        row("secureboot", "Secure Boot", "warn", ("off" if sb == "disabled" else "not started through UEFI") + ": a changed boot loader or kernel starts unnoticed",
            ["turn it on in the firmware's setup, and set a password on that setup"])
    for v in st["luks"]:
        tp = [s for s in v["slots"] if s["kind"] == "tpm2"]
        if not v["read"]:
            if v["version"] != 1:
                row("unlock", "opens with", "unknown", "the key slots of %s are read as root" % v["device"], sudo)
            continue
        ways = " or ".join("the " + k for k in sorted({KIND.get(s["kind"], s["kind"]) for s in v["slots"] if s["kind"] != "tpm2"})) or "nothing else"
        if not tp:
            row("unlock", "opens with", "ok", "%s, typed at every start" % ways)
        elif any(not s.get("pin") for s in tp):
            row("unlock", "opens with", "bad", "the TPM alone, without a PIN: the disk opens by itself for whoever holds the machine",
                ["silik disk tpm enroll    (the same slot again, with a PIN)", "silik disk tpm remove"])
        elif v["crypttab_tpm2"] is False or st["initramfs_tpm2"] is False:
            row("unlock", "opens with", "warn", "%s; the TPM2 slot is enrolled but not used at a start (%s)" % (
                ways, "no tpm2-device= in /etc/crypttab" if v["crypttab_tpm2"] is False else "the initramfs has no TPM2 support"),
                ["silik disk tpm enroll", "silik disk tpm remove"])
        elif sb != "enabled" or any(7 not in s.get("pcrs", []) for s in tp) or t["pcr7"] == "empty":
            row("unlock", "opens with", "warn", "TPM2 + PIN, or %s; but %s" % (ways, "Secure Boot is not on: a slot enrolled with it on does not open now, one enrolled with it off is bound to nothing useful"
                if sb != "enabled" else "the slot is not bound to a Secure Boot state the firmware measures"), ["silik disk tpm enroll    (with Secure Boot on)"])
        else:
            row("unlock", "opens with", "ok", "TPM2 + PIN while the Secure Boot state is the one it was enrolled in, or %s" % ways)
    return out


def external(st):
    """True when the system's own disk hangs on USB (an external disk, started from the computer's boot menu)"""
    return "usb" in ((st["mounts"].get("/") or {}).get("tran") or [])


EXTERNAL_TPM = ("/ is on an external disk (USB): a TPM key slot opens it on this computer only. Started on any other one, "
                "the passphrase or the recovery key opens it")


def advice(st):
    """what `silik disk check` adds: [{id, text, commands}], commands a person runs (none is run here)"""
    out = []
    t, sb = st["tpm"], st["secure_boot"]
    if external(st):
        out.append({"id": "external", "text": "The system is on an external disk (USB). Shut the system down before the disk is unplugged: "
                    "pulled out while it runs, the running system is lost at once, and what was not yet written with it. "
                    "An external disk is lost or taken more easily than a computer: encrypt it (the installer's tick), with a passphrase. "
                    "Its initramfs is made for the computer it was installed on (the base's default): to start the same disk on other "
                    "computers, the base's package dracut-config-generic makes it with every driver, now and at each new kernel "
                    "[A: not run] (docs/DISK.md)",
                    "commands": ["sudo dnf install dracut-config-generic", "sudo dracut -f --regenerate-all"]})
    for v in st["luks"]:
        dev = v["device"]
        out.append({"id": "header", "text": "A damaged LUKS header loses the whole disk, whatever the passphrase. Keep a copy that is not on this disk "
                    "(it opens the disk with the passphrases of the day it was made: keep it as a key; make it again after a key slot changes)",
                    "commands": ["sudo cryptsetup luksHeaderBackup %s --header-backup-file luks-header-%s.img" % (dev, (v["uuid"] or "copy")[:8])]})
        if v["version"] == 1 or not v["read"]:
            continue
        kinds = [s["kind"] for s in v["slots"]]
        if "recovery" not in kinds and kinds.count("passphrase") < 2:
            out.append({"id": "recovery", "text": "One passphrase is the only way in when it is forgotten" + (" or the TPM stops answering" if "tpm2" in kinds else "") +
                        ": a recovery key is a second one, generated, to keep on paper away from the machine", "commands": ["silik disk recovery"]})
        if "tpm2" not in kinds and t["present"] and t["version"] == "2" and sb == "enabled":
            out.append({"id": "tpm", "text": "This machine can open the disk with its TPM and a PIN, bound to the Secure Boot state: a short PIN at each "
                        "start, the long passphrase kept for recovery. A change of firmware keys asks the passphrase once (docs/DISK.md)" +
                        (". " + EXTERNAL_TPM if external(st) else ""),
                        "commands": ["silik disk tpm enroll"]})
    if st["luks"]:
        out.append({"id": "firmware", "text": "No command can see whether the firmware's setup has a password: without one Secure Boot is turned off, "
                    "or another disk started, by whoever holds the machine", "commands": []})
        out.append({"id": "boot", "text": "/boot is not encrypted on this base: Secure Boot checks the boot loader and the kernel, nothing checks the "
                    "initramfs or the kernel's arguments. Somebody who had the machine in their hands could have changed them: a PIN or passphrase "
                    "typed after that is theirs (docs/DISK.md)", "commands": []})
    return out


def show(st, with_advice):
    rs = rows(st)
    count = {k: sum(1 for r in rs if r["state"] == k) for k in ("ok", "warn", "bad", "unknown")}
    mark = SILIK.SEC_MARK
    lines = []
    for r in rs:
        lines.append("%s %-8s %-18s %s" % (mark[r["state"]], r["state"], r["name"], r["value"]))
        lines += ["%-29s %s: %s" % ("", "see" if r["state"] == "unknown" else "fix", f) for f in r["fix"]]
    lines.append("%d ok, %d warn, %d bad, %d unknown" % (count["ok"], count["warn"], count["bad"], count["unknown"]))
    if with_advice:
        for ad in advice(st):
            lines.append("")
            lines.append(ad["text"])
            lines += ["    " + c for c in ad["commands"]]
    return rs, count, "\n".join(lines)


def status(ctx, a):
    st = probe(SILIK)
    with_advice = getattr(a, "cmd", None) == "check"
    rs, count, text = show(st, with_advice)
    if a.json:
        out = {"checks": rs, "summary": count, "state": st}
        if with_advice:
            out["advice"] = advice(st)
        print(json.dumps(out, indent=1))
    else:
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode("ascii", "replace").decode("ascii"))
    return 1 if count["bad"] else 0


# ------------------------------------------------------------------------------------------- what it changes

def pick(st, typed):
    """the LUKS volume a command works on: the one / is on, or the one typed if it is a LUKS volume of this machine"""
    silik = SILIK
    vols = {v["device"]: v for v in st["luks"]}
    if typed:
        dev = os.path.realpath(typed) if os.path.exists(typed) else typed
        v = vols.get(dev) or vols.get(typed) or next((x for x in st["luks"] if x.get("kname") == dev), None)
        if not v:
            silik.die("%s is not a LUKS volume of this machine (those are: %s)" % (typed, ", ".join(sorted(vols)) or "none"), 2)
        return v
    m = st["mounts"].get("/")
    if not st["seen"] or m is None:
        silik.die("the device / is on is not seen from here%s: nothing to work on" % (" (inside a container)" if st["container"] else ""), 3)
    if not m["luks"]:
        silik.die("/ (%s) is not on a LUKS volume: there is no key slot to add. %s" % (m["device"], NO_COMMAND), 1)
    if len(m["luks"]) > 1:
        silik.die("/ is on %d LUKS volumes (%s): name one" % (len(m["luks"]), ", ".join(m["luks"])), 2)
    return vols[m["luks"][0]]


def agree(ctx, a, vol, what):
    """the device said, and asked about: nothing is written to a volume the person did not confirm"""
    print("silik: %s: %s%s" % (what, vol["device"], " (LUKS%s%s)" % (vol["version"] or "", ", open as " + vol["name"] if vol["name"] else "")))
    if ctx.dry or a.yes:
        return
    if not sys.stdin.isatty():
        SILIK.die("not asked at a terminal: add --yes when that is the volume", 2)
    try:
        ok = input("silik: go on with %s? [y/N] " % vol["device"]).strip().lower() in ("y", "yes", "s", "si", "sí")
    except EOFError:
        ok = False
    if not ok:
        SILIK.die("nothing changed", 1)


def secrets(ctx, a, pin):
    """(environment, sudo's switches) for systemd-cryptenroll away from a terminal: the PIN from the first line of
    the standard input, in $NEWPIN; the passphrase from --unlock-key-file or an existing $PASSWORD. At a terminal
    systemd-cryptenroll asks by itself and nothing passes through here"""
    silik = SILIK
    env, keep = dict(os.environ), []
    if ctx.dry or sys.stdin.isatty():
        return None, keep
    if not a.unlock_key_file and not env.get("PASSWORD"):
        silik.die("not at a terminal: the passphrase is given with --unlock-key-file FILE (or in $PASSWORD)", 2)
    if env.get("PASSWORD"):
        keep.append("PASSWORD")
    if pin:
        line = sys.stdin.readline().rstrip("\n")
        if not line:
            silik.die("not at a terminal: the new PIN is the first line of the standard input", 2)
        env["NEWPIN"] = line
        keep.append("NEWPIN")
    return env, keep


def enroll_argv(a, vol, what, keep=()):
    """systemd-cryptenroll's command line, as root. WHAT: its switches"""
    argv = ["systemd-cryptenroll"] + (["--unlock-key-file=" + a.unlock_key_file] if getattr(a, "unlock_key_file", None) else []) + list(what) + [vol["device"]]
    if os.geteuid() == 0:
        return argv
    return ["sudo"] + (["--preserve-env=" + ",".join(keep)] if keep else []) + argv


def after(ctx, vol):
    """the volume's key slots, read again as root: [{slot, kind...}], None when not readable"""
    rc, out = ctx.run(SILIK.as_root(["cryptsetup", "luksDump", "--dump-json-metadata", vol["device"]]), check=False, capture=True)
    if ctx.dry or rc != 0:
        return None
    try:
        return parse_dump(json.loads(out))["slots"]
    except (ValueError, AttributeError, TypeError):
        return None


def write_crypttab(ctx, vol, on):
    """/etc/crypttab with or without tpm2-device= on the volume's line: a copy of the file first, then the file written
    in place (its owner, mode and label stay). False when the volume has no line"""
    silik = SILIK
    rc, text = ctx.run(silik.as_root(["cat", CRYPTTAB]), check=False, capture=True)
    if ctx.dry:
        print("    | the line of %s in %s %s" % (vol["device"], CRYPTTAB, "gets tpm2-device=%s among its options" % TPM2_DEVICE if on else "loses tpm2-device="))
        ctx.run(silik.as_root(["cp", "-a", CRYPTTAB, CRYPTTAB + ".before-silik-disk"]))
        ctx.run(silik.as_root(["tee", CRYPTTAB]))
        return True
    new = crypttab_set(text, vol, on) if rc == 0 else None
    if new is None:
        return False
    if new == text:
        return True
    ctx.run(silik.as_root(["cp", "-a", CRYPTTAB, CRYPTTAB + ".before-silik-disk"]))
    argv = silik.as_root(["tee", CRYPTTAB])
    ctx.echo(argv)
    i, _ = crypttab_find(new, vol)
    if not ctx.quiet:
        print("    | " + new.splitlines()[i], flush=True)
    ctx.note(argv)
    import subprocess
    p = subprocess.run(argv, input=new, universal_newlines=True, stdout=subprocess.DEVNULL)
    if p.returncode != 0:
        silik.die("%s was not written (tee exited %d); the copy is %s.before-silik-disk" % (CRYPTTAB, p.returncode, CRYPTTAB), 1)
    return True


def remake(ctx, otherwise):
    """the running kernel's initramfs made again (dracut takes /etc/crypttab into it, and its tpm2-tss module when a
    line there has tpm2-device=). The other installed kernels keep theirs: a known way to start"""
    rc, _ = ctx.run(SILIK.as_root(["dracut", "-f"]), check=False)
    if rc != 0:
        SILIK.die("dracut exited %d: %s. Run it again: sudo dracut -f" % (rc, otherwise), rc)


def tpm_enroll(ctx, a):
    silik = SILIK
    import shutil
    st = probe(silik)
    vol = pick(st, a.device)
    t, sb = st["tpm"], st["secure_boot"]
    if vol["version"] == 1:
        silik.die("%s is LUKS1: a TPM slot needs LUKS2 (cryptsetup convert, with the volume closed; not done here)" % vol["device"], 1)
    if not re.match(r"^\d+(\+\d+)*$", a.pcrs) or any(int(p) > 23 for p in a.pcrs.split("+")):
        silik.die("--pcrs takes numbers 0-23 joined with + (default %s: the Secure Boot state)" % PCRS, 2)
    if not ctx.dry:
        if not shutil.which("systemd-cryptenroll"):
            silik.die("systemd-cryptenroll is not installed (the base's package systemd-udev has it)", 3)
        if not t["present"] or t["version"] != "2":
            silik.die("no TPM 2.0 is seen (%s): nothing to enroll in" % ("none in %s" % SYS_TPM if not t["present"] else "version " + (t["version"] or "unknown")), 1)
    if (sb != "enabled" or t["pcr7"] == "empty") and not a.even_without_secure_boot:
        why = "PCR 7 was never written by this firmware" if sb == "enabled" else "Secure Boot is %s" % {"disabled": "off", "bios": "not there (not started through UEFI)"}.get(sb, "not visible")
        silik.die("%s: PCR 7 would bind the key to nothing useful, and any system started on this machine could ask the TPM for it with the PIN.\n"
                  "  Turn Secure Boot on in the firmware's setup first (then the key is bound to that state), or add --even-without-secure-boot" % why, 1)
    if a.no_pin:
        print("silik: --no-pin: " + NO_PIN, file=sys.stderr)
    if external(st):
        print("silik: " + EXTERNAL_TPM, file=sys.stderr)
    need_tools = not shutil.which("tpm2")          # (dracut's tpm2-tss module is left out without the tpm2 program)
    pin = not a.no_pin
    agree(ctx, a, vol, "a TPM2 key slot %s, bound to PCR %s, is added to" % ("with a PIN" if pin else "WITHOUT a PIN", a.pcrs))
    env, keep = secrets(ctx, a, pin)
    if need_tools:
        ctx.run(silik.as_root(["dnf", "-y", "install", "tpm2-tools"]))
    # An earlier TPM2 slot goes first, in a step of its own: asked to enroll a slot whose PCR state is already
    # enrolled, systemd-cryptenroll does nothing ("This PCR set is already enrolled": seen with systemd 252 of EL 9.8),
    # and the PIN typed now would not be the one that opens the disk. Only TPM2 slots are named: the passphrase and
    # recovery slots stay, and one of them must be there
    before = after(ctx, vol)
    if before is None and not ctx.dry:
        silik.die("the header of %s could not be read as root: nothing was changed" % vol["device"], 1)
    if ctx.dry:
        print("    | a TPM2 slot that is already there is wiped first: %s" % " ".join(enroll_argv(None, vol, ["--wipe-slot=tpm2"])))
    elif any(s["kind"] == "tpm2" for s in before):
        if not any(s["kind"] in ("passphrase", "recovery") for s in before):
            silik.die("%s has no passphrase or recovery slot: the TPM2 slot is not replaced before it has one:\n"
                      "  sudo systemd-cryptenroll --password %s" % (vol["device"], vol["device"]), 1)
        rc, _ = ctx.run(enroll_argv(None, vol, ["--wipe-slot=tpm2"]), check=False)
        if rc != 0:
            silik.die("systemd-cryptenroll exited %d: nothing else was changed" % rc, rc)
    rc, _ = ctx.run(enroll_argv(a, vol, ["--tpm2-device=" + TPM2_DEVICE, "--tpm2-pcrs=" + a.pcrs, "--tpm2-with-pin=" + ("yes" if pin else "no")], keep),
                    check=False, env=env)
    if rc != 0:
        silik.die("systemd-cryptenroll exited %d: no TPM2 slot was added, nothing else was changed (the passphrase opens the disk%s)"
                  % (rc, "; the earlier TPM2 slot is wiped" if before and any(s["kind"] == "tpm2" for s in before) else " as before"), rc)
    slots = after(ctx, vol)
    if slots is not None:
        if not any(s["kind"] == "tpm2" for s in slots):
            silik.die("no TPM2 slot is in the header after that: nothing else was changed", 1)
        if not any(s["kind"] in ("passphrase", "recovery") for s in slots):
            silik.die("no passphrase or recovery slot is left in the header: this must not happen. Add one NOW, before a restart:\n"
                      "  sudo systemd-cryptenroll --password %s" % vol["device"], 1)
    if not write_crypttab(ctx, vol, True):
        silik.die("%s has no line for %s: the slot is enrolled but nothing will use it at a start. The line would be:\n"
                  "  %s UUID=%s none tpm2-device=%s\n  then: sudo dracut -f" % (CRYPTTAB, vol["device"], vol["name"] or "luks-" + vol["uuid"], vol["uuid"], TPM2_DEVICE), 1)
    remake(ctx, "the slot is enrolled and %s names it, but the initramfs is the old one: the passphrase is asked as before" % CRYPTTAB)
    print("silik: at the next start this kernel %s.\n"
          "  The passphrase still opens the disk: it is asked when the TPM does not give the key (a wrong PIN, another Secure Boot\n"
          "  state, another machine). The other installed kernels ask for it as before. After a change of the firmware's keys\n"
          "  (a dbx update, a MOK) the TPM stops giving the key: the passphrase once, then `silik disk tpm enroll` again."
          % ("asks for the TPM2 PIN" if pin else "opens the disk by itself, with no question"))
    return 0


def tpm_remove(ctx, a):
    silik = SILIK
    st = probe(silik)
    vol = pick(st, a.device)
    if vol["read"] and not any(s["kind"] == "tpm2" for s in vol["slots"]) and vol["crypttab_tpm2"] is not True:
        print("silik: %s has no TPM2 slot and %s no tpm2-device= for it: nothing to remove" % (vol["device"], CRYPTTAB))
        return 0
    if vol["read"] and not any(s["kind"] in ("passphrase", "recovery") for s in vol["slots"]):
        silik.die("%s has no passphrase or recovery slot: without the TPM2 slot nothing would open it. Add one first:\n"
                  "  sudo systemd-cryptenroll --password %s" % (vol["device"], vol["device"]), 1)
    agree(ctx, a, vol, "the TPM2 key slot is wiped from")
    rc, _ = ctx.run(enroll_argv(None, vol, ["--wipe-slot=tpm2"]), check=False)
    if rc != 0:
        silik.die("systemd-cryptenroll exited %d: nothing else was changed" % rc, rc)
    if not write_crypttab(ctx, vol, False):
        print("silik: %s has no line for %s: nothing to take out of it" % (CRYPTTAB, vol["device"]))
    remake(ctx, "the slot is wiped; the old initramfs looks for the TPM first, then asks the passphrase")
    print("silik: at the next start the passphrase (or the recovery key) is asked, as before the enrolment.")
    return 0


def recovery(ctx, a):
    silik = SILIK
    st = probe(silik)
    vol = pick(st, a.device)
    if vol["version"] == 1:
        silik.die("%s is LUKS1: a recovery key of systemd-cryptenroll needs LUKS2. A second passphrase does the same:\n"
                  "  sudo cryptsetup luksAddKey %s" % (vol["device"], vol["device"]), 1)
    agree(ctx, a, vol, "one more key slot, with a generated recovery key, is added to")
    env, keep = secrets(ctx, a, False)
    # (the key is printed by systemd-cryptenroll itself, once, to this terminal: it passes through no file and no
    # variable of silik's)
    rc, _ = ctx.run(enroll_argv(a, vol, ["--recovery-key"], keep), check=False, env=env)
    if rc != 0:
        silik.die("systemd-cryptenroll exited %d: no slot was added" % rc, rc)
    print("silik: that key is shown this once. On paper, away from the machine; not in a file on this disk. It is typed where\n"
          "  the passphrase is asked. To take it out again: sudo systemd-cryptenroll --wipe-slot=recovery %s" % vol["device"])
    return 0


# ------------------------------------------------------------------------------------------- the whole disk

GROW_LEAST = 64 << 20          # bytes free after the last partition below which the partition table is left alone
SYS_BLOCK = "/sys/class/block"
NO_GROW = "Nothing was changed"
# what the installer leaves free in the volume group beside a thin pool: a fifth of the group (seen in the installed
# image: 7.7 of 38.4 GB), at least 1 GiB and at most 100 GiB [A: the two bounds are blivet's, from its code as
# remembered, not seen here]. `grow` keeps the same share
RESERVE_PART, RESERVE_LEAST, RESERVE_MOST = 5, 1 << 30, 100 << 30
LVS = ["lvs", "--noheadings", "--nosuffix", "--units", "b", "--separator", "|", "-o",
       "lv_dm_path,vg_name,lv_name,pool_lv,lv_size,vg_size,vg_free,vg_extent_size"]


def grow_read(silik, sys_block=None):
    """what / is on, as far as `grow` needs it: {source, fstype, kinds (the types of every device under /), thin,
    parts and disks (each once: {path, kname, pttype}), partn, start, sectors, disk_sectors, later (partitions that
    start after it)}, sizes in 512-byte sectors as the kernel gives them. None when it cannot be seen (a container)"""
    sys_block = sys_block or SYS_BLOCK
    rc, src = silik.sec_cmd(["findmnt", "-n", "-o", "SOURCE", "/"])
    src = src.strip().split("[")[0]
    if rc != 0 or not src.startswith("/dev/"):
        return None
    rc, out = silik.sec_cmd(["lsblk", "-J", "-s", "-o", "PATH,KNAME,TYPE,FSTYPE,PTTYPE", src])
    try:
        top = (json.loads(out).get("blockdevices") or [None])[0] if rc == 0 else None
    except ValueError:
        top = None
    if not top:
        return None
    st = {"source": src, "fstype": top.get("fstype"), "top": top.get("type"), "kinds": [], "thin": False, "parts": [], "disks": []}
    todo = [top]
    while todo:
        n = todo.pop()
        todo.extend(n.get("children") or [])
        kind = n.get("type")
        if kind not in st["kinds"]:
            st["kinds"].append(kind)
        if kind == "lvm" and str(n.get("path") or "").endswith("-tpool"):
            st["thin"] = True
        for key, want in (("parts", "part"), ("disks", "disk")):
            if kind == want and n.get("path") not in [x["path"] for x in st[key]]:
                st[key].append({k: n.get(k) for k in ("path", "kname", "pttype")})
    st["kinds"].sort(key=str)

    def num(*path):
        try:
            with open(os.path.join(sys_block, *path)) as f:
                return int(f.read().split()[0])
        except (OSError, ValueError, IndexError):
            return None

    if len(st["parts"]) == 1 and len(st["disks"]) == 1:
        part, disk = st["parts"][0]["kname"], st["disks"][0]["kname"]
        st.update(partn=num(part, "partition"), start=num(part, "start"), sectors=num(part, "size"), disk_sectors=num(disk, "size"), later=[])
        try:
            names = sorted(os.listdir(os.path.join(sys_block, disk)))
        except OSError:
            names = []
        for n in names:
            if num(disk, n, "partition") is not None and st["start"] is not None and (num(disk, n, "start") or 0) > st["start"]:
                st["later"].append(n)
    return st


def grow_plan(st):
    """(what, text, plan): what is "refuse" (this layout is not one `grow` knows: nothing is tried), "full" (the
    partition already ends where the disk does) or "grow"; plan: {disk, part, partn, lv, thin, free (bytes)}"""
    if not st:
        return "refuse", "the device / is on is not seen from here", None
    if "crypt" in st["kinds"]:
        return "refuse", "/ is on an encrypted volume: `silik disk grow` does not grow an encrypted system (not written yet)", None
    if st.get("top") != "lvm" or set(st["kinds"]) - {"lvm", "part", "disk"} or len(st["parts"]) != 1 or len(st["disks"]) != 1:
        return "refuse", "/ (%s) is on %s, %d partition(s) of %d disk(s): `silik disk grow` knows an LVM volume on one partition of " \
            "one disk, the layout of an installation with automatic partitioning" % (
                st["source"], "+".join(str(k) for k in st["kinds"]) or "nothing seen", len(st["parts"]), len(st["disks"])), None
    part, disk = st["parts"][0], st["disks"][0]
    if (disk.get("pttype") or part.get("pttype")) != "gpt":
        return "refuse", "%s has no GPT partition table (%s)" % (disk["path"], disk.get("pttype") or "none seen"), None
    if st.get("fstype") not in ("xfs", "ext4"):
        return "refuse", "the file system of / is %s: only xfs and ext4 are grown" % (st.get("fstype") or "not seen"), None
    if None in (st.get("partn"), st.get("start"), st.get("sectors"), st.get("disk_sectors")):
        return "refuse", "the kernel does not say where %s starts and ends" % part["path"], None
    if st.get("later"):
        return "refuse", "%s is not the last partition of %s (after it: %s): there is nothing next to it to grow into" % (
            part["path"], disk["path"], ", ".join(st["later"])), None
    free = (st["disk_sectors"] - st["start"] - st["sectors"]) * 512
    plan = {"disk": disk["path"], "part": part["path"], "partn": st["partn"], "lv": st["source"], "thin": bool(st.get("thin")),
            "free": free, "disk_bytes": st["disk_sectors"] * 512}
    if free < GROW_LEAST:
        return "full", "%s already ends where %s does (%.1f GB; %d MB after it, the partition table's own copy among them)" % (
            part["path"], disk["path"], plan["disk_bytes"] / 1e9, free >> 20), plan
    return "grow", "%s (%.1f GB) has %.1f GB after %s that nothing uses" % (disk["path"], plan["disk_bytes"] / 1e9, free / 1e9, part["path"]), plan


def grow_lvm(text, source):
    """from what `lvs` says (LVS) after the physical volume grew: (commands, lines to say). None when the volume of /
    is not among its lines. A volume of its own gets all that is free. A thin volume: its pool grows by what is free
    less the installer's share of the group, and the volume of / by as much as its pool"""
    rows = []
    for line in text.splitlines():
        f = [x.strip() for x in line.split("|")]
        if len(f) == len(LVS[-1].split(",")) and all(x.isdigit() for x in f[4:]):
            rows.append(dict(zip(("path", "vg", "lv", "pool", "size", "vg_size", "vg_free", "extent"), f[:4] + [int(x) for x in f[4:]])))
    mine = next((r for r in rows if r["path"] == source), None)
    if mine is None or not mine["extent"]:
        return None
    gb = lambda n: "%.1f GB" % (n / 1e9)
    if not mine["pool"]:
        if mine["vg_free"] < mine["extent"]:
            return [], ["the volume group %s has nothing free: / already has all of it" % mine["vg"]]
        return [["lvextend", "--resizefs", "--extents", "+100%FREE", source]], \
               ["/ (%s) gets the %s that are free in the volume group %s" % (gb(mine["size"]), gb(mine["vg_free"]), mine["vg"])]
    reserve = min(max(mine["vg_size"] // RESERVE_PART, RESERVE_LEAST), RESERVE_MOST)
    add = (mine["vg_free"] - reserve) // mine["extent"]
    if add * mine["extent"] < GROW_LEAST:       # (the installer's own share is not exactly a fifth: a few extents more are not a reason)
        return [], ["the volume group %s has %s free, the share the installer leaves beside the thin pool (%s): the pool %s "
                    "and / stay as they are" % (mine["vg"], gb(mine["vg_free"]), gb(reserve), mine["pool"])]
    return [["lvextend", "--extents", "+%d" % add, "%s/%s" % (mine["vg"], mine["pool"])],
            ["lvextend", "--resizefs", "--extents", "+%d" % add, source]], \
           ["the thin pool %s/%s and / (%s) grow by %s each; %s of the volume group stay free, the share the installer "
            "leaves beside the pool" % (mine["vg"], mine["pool"], gb(mine["size"]), gb(add * mine["extent"]), gb(mine["vg_free"] - add * mine["extent"]))]


def grow(ctx, a):
    silik = SILIK
    what, text, plan = grow_plan(grow_read(silik))
    if what == "refuse":
        silik.die("%s. %s" % (text, NO_GROW), 2)
    print("silik: " + text)
    if what == "grow":
        print("silik: the partition %s goes up to the end of %s, then the LVM volume%s and the file system of / (%s). "
              "Nothing is moved or formatted; no other partition is touched" % (
                  plan["part"], plan["disk"], " (its thin pool first)" if plan["thin"] else "", plan["lv"]))
        if not (ctx.dry or a.yes):
            if not sys.stdin.isatty():
                silik.die("not asked at a terminal: add --yes when that is the disk", 2)
            try:
                ok = input("silik: go on with %s? [y/N] " % plan["disk"]).strip().lower() in ("y", "yes", "s", "si", "sí")
            except EOFError:
                ok = False
            if not ok:
                silik.die("nothing changed", 1)
        # the partition table's second copy to the end of the disk (it sits where the image ended), then the
        # partition up to it: sfdisk writes the table and nothing else, and the kernel learns the new size while the
        # partition is in use (partx)
        ctx.run(silik.as_root(["sfdisk", "--no-reread", "--no-tell-kernel", "--relocate", "gpt-bak-std", plan["disk"]]))
        if not ctx.quiet:
            print("    | , +", flush=True)
        ctx.run(silik.as_root(["sfdisk", "--no-reread", "--no-tell-kernel", "-N", str(plan["partn"]), plan["disk"]]), stdin=", +\n")
        ctx.run(silik.as_root(["partx", "--update", "--nr", str(plan["partn"]), plan["disk"]]))
    # the steps above the partition are run each time: they do nothing when there is nothing to take, and a run
    # that stopped after the partition is finished by the next one
    ctx.run(silik.as_root(["pvresize", plan["part"]]))
    rc, out = ctx.run(silik.as_root(LVS), check=False, capture=True)
    if ctx.dry:
        print("silik: then, from what lvs says: " + ("lvextend of the thin pool and of / by what is free, less the share the "
              "installer leaves in the volume group" if plan["thin"] else "lvextend --resizefs --extents +100%FREE " + plan["lv"]))
        return 0
    steps = grow_lvm(out, plan["lv"]) if rc == 0 else None
    if steps is None:
        silik.die("lvs %s: the volume of / (%s) was not read; the file system was not grown" % (
            "exited %d" % rc if rc else "did not name it", plan["lv"]), 1)
    for line in steps[1]:
        print("silik: " + line)
    for argv in steps[0]:
        ctx.run(silik.as_root(argv))
    rc, out = silik.sec_cmd(["df", "-h", "--output=size,avail", "/"])
    line = out.strip().splitlines()[-1].split() if rc == 0 and out.strip() else []
    if len(line) == 2:
        print("silik: / is %s, %s free" % (line[0], line[1]))
    return 0


def language(env=None):
    """en | ca | es, as the COMMAND bar reads it"""
    env = os.environ if env is None else env
    for k in ("SILIK_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        v = (env.get(k) or "")[:2].lower()
        if v:
            return v if v in NOTICE else "en"
    return "en"


def notice(ctx, a):
    """the installer cannot propose encryption without taking the choice of the disk from the person (docs/DISK.md),
    so the first login says it when it was not chosen: once for each state (again when what is in clear changes)"""
    import shutil
    silik = SILIK
    bad = [r["name"] for r in rows(probe(silik, deep=False)) if r["state"] == "bad" and r["id"] in ("/", "/home", "swap")]
    stamp = os.path.join(silik.STATE, "disk-notice")
    if not bad or (silik.read(stamp).strip() == " ".join(bad) and not a.again):
        return 0
    msg = NOTICE[language()] % ", ".join(bad)
    if os.environ.get("DISPLAY") and shutil.which("notify-send"):
        ctx.run(["notify-send", "--app-name=SilikOS", "SilikOS", msg], check=False)
    else:
        print(msg)
    if not ctx.dry:
        try:
            os.makedirs(silik.STATE, exist_ok=True)
            with open(stamp, "w") as f:
                f.write(" ".join(bad) + "\n")
        except OSError:
            pass
    return 0


def tpm_help(ctx, a):
    print(__doc__)
    return 2


def register(group, silik):
    global SILIK
    SILIK = silik
    group.add_argument("--json", action="store_true")
    group.set_defaults(fn=status)
    sub = group.add_subparsers(dest="cmd")
    x = sub.add_parser("check", help="the same, and what to do so that the disk is neither opened nor lost: commands printed, none run")
    x.add_argument("--json", action="store_true")
    x.set_defaults(fn=status)
    t = sub.add_parser("tpm", help="unlock with the TPM and a PIN: enroll | remove")
    t.set_defaults(fn=tpm_help)
    ts = t.add_subparsers(dest="tpm_cmd")
    x = ts.add_parser("enroll", help="a TPM2 key slot with a PIN bound to the Secure Boot state, /etc/crypttab, the initramfs; the passphrase slot stays")
    x.add_argument("device", nargs="?", metavar="DEVICE", help="a LUKS volume of this machine (default: the one / is on)")
    x.add_argument("--yes", action="store_true", help="do not ask about the device")
    x.add_argument("--no-pin", action="store_true", help="the TPM alone: the disk opens by itself for whoever holds the machine")
    x.add_argument("--even-without-secure-boot", action="store_true", help="enroll although PCR 7 then binds the key to nothing useful")
    x.add_argument("--pcrs", default=PCRS, metavar="N+N", help="the PCRs the key is bound to (default %s: the Secure Boot state)" % PCRS)
    x.add_argument("--unlock-key-file", metavar="FILE", help="a file with the passphrase, for systemd-cryptenroll (away from a terminal)")
    x.set_defaults(fn=tpm_enroll)
    x = ts.add_parser("remove", help="wipe the TPM2 key slot, take the option out of /etc/crypttab, make the initramfs again")
    x.add_argument("device", nargs="?", metavar="DEVICE")
    x.add_argument("--yes", action="store_true")
    x.set_defaults(fn=tpm_remove)
    x = sub.add_parser("recovery", help="one more key slot with a generated recovery key, shown once")
    x.add_argument("device", nargs="?", metavar="DEVICE")
    x.add_argument("--yes", action="store_true")
    x.add_argument("--unlock-key-file", metavar="FILE", help="a file with the passphrase (away from a terminal)")
    x.set_defaults(fn=recovery)
    x = sub.add_parser("grow", help="the system on the whole disk it is on: the last partition, the LVM volume and / grown; nothing moved or formatted")
    x.add_argument("--yes", action="store_true", help="do not ask about the disk")
    x.set_defaults(fn=grow)
    x = sub.add_parser("notice", help="at a login: say once, as a notification, that the disk is not encrypted")
    x.add_argument("--again", action="store_true", help="although it was said before")
    x.set_defaults(fn=notice)

