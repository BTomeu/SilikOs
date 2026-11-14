#!/usr/bin/env python3
"""port_system.py: the "SilikOS 10 lab" system, made from the SilikOS 9 product by rules (as port_shell.py makes the
shell extension): the packages and the installer's kickstart, with only what EL 10 forces changed.

    python3 el10/port_system.py --packages DIR     DIR/<package>/ for every package of packages/ that goes on the lab
                                                   ISO: the recipe and its files/, the rules below applied; the shell
                                                   extension in it is the port (port_shell.py), with el10/shell-ext's
                                                   metadata.json
    python3 el10/port_system.py --kickstart EPEL   the kickstart of the lab ISO on standard output: kickstart/silikos.ks
                                                   with the rules below; EPEL is the minor release of the base the ISO
                                                   is made from (10.2: EPEL 10 has one tree per minor of the base)
    python3 el10/port_system.py --rules            the rules: what EL 10 forces, and where that was seen

Nothing of the EL 9 product is written: packages/ and kickstart/ are read. A rule says how many places it expects to
change; when the EL 9 file has moved and a rule no longer finds its place, the script stops and names the rule. What
of the result has run, and where: docs/EL10.md (the lab ISO). Python standard library only.
"""
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGES = os.path.join(ROOT, "packages")
KICKSTART = os.path.join(ROOT, "kickstart", "silikos.ks")
EL10 = os.path.join(ROOT, "el10")

# packages of the product that are not on the lab ISO, and why (each seen with dnf repoquery in almalinux:10 on
# 14/11/2026, or read in the package itself)
LEFT_OUT = {
    "silik-win": "it requires xorg-x11-server-Xephyr, which EL 10 does not have (no package of BaseOS, AppStream, CRB, "
                 "extras or EPEL 10.2 provides it), and there is no Wine for EL 10 (docs/EL10.md section 3)",
    "silikos-repos": "its repository holds the EL 9 builds (repo/el9/...): an update from it would put the GNOME Shell "
                     "40 desktop on an EL 10 system",
}

# (file under packages/, id, why EL 10 forces it, kind "lit" or "re", old, new, expected count)
PACKAGE_RULES = [
    ("silikos-desktop/silikos-desktop.spec", "no-x11-login",
     "EL 10 has no Xorg server and no X11 session (docs/EL10.md section 1): a login screen with Wayland off could "
     "start no session. GDM's own default (Wayland) is left as it is",
     "lit",
     "# the login screen starts X11 sessions (Xorg is part of the EL9 base); on the first installation only: a person's own\n"
     "# change to Wayland stays through upgrades\n"
     "if [ $1 -eq 1 ] && [ -f %{_sysconfdir}/gdm/custom.conf ]; then\n"
     "  if grep -q '^#\\?WaylandEnable=' %{_sysconfdir}/gdm/custom.conf; then\n"
     "    sed -i 's/^#\\?WaylandEnable=.*/WaylandEnable=false/' %{_sysconfdir}/gdm/custom.conf\n"
     "  else\n"
     "    sed -i 's/^\\[daemon\\]/[daemon]\\nWaylandEnable=false/' %{_sysconfdir}/gdm/custom.conf\n"
     "  fi\n"
     "fi\n",
     "# (EL 10: the login screen starts Wayland sessions, GDM's own default; there is no Xorg server to turn to)\n", 1),
    ("silikos-desktop/silikos-desktop.spec", "no-shell-overlay-install",
     "the shell theme is not made on GNOME Shell 49 (its stylesheet has other names: docs/EL10.md section 4), so the "
     "session's environment does not put SilikOS files in the place of the shell's own",
     "lit",
     "install -Dm0644 %{_sourcedir}/60-silikos-shell.conf %{buildroot}%{_prefix}/lib/environment.d/60-silikos-shell.conf\n", "", 1),
    ("silikos-desktop/silikos-desktop.spec", "no-shell-overlay-file", "(the same file, in the list of the package's files)",
     "lit", "%{_prefix}/lib/environment.d/60-silikos-shell.conf\n", "", 1),
    ("silikos-desktop/files/00-silikos", "favourites",
     "EL 10 has no gnome-terminal and its Workstation set has no gedit: the terminal is Ptyxis, the editor GNOME Text "
     "Editor (dnf repoquery, 14/11/2026)",
     "lit", "'org.gnome.Terminal.desktop', 'firefox.desktop', 'org.gnome.gedit.desktop'",
     "'org.gnome.Ptyxis.desktop', 'firefox.desktop', 'org.gnome.TextEditor.desktop'", 1),
    ("silik-command/silik-command.spec", "terminal-package", "EL 10 has no gnome-terminal; its terminal is ptyxis (AppStream)",
     "lit", "Recommends:     gnome-terminal\n", "Recommends:     ptyxis\n", 1),
    ("silik-command/files/silik-command", "terminal-program",
     "the same: the COMMAND bar opens a terminal as `ptyxis -- COMMAND` where it was `gnome-terminal -- COMMAND`",
     "lit", 'TERMINAL = os.environ.get("SILIK_TERMINAL") or "gnome-terminal"', 'TERMINAL = os.environ.get("SILIK_TERMINAL") or "ptyxis"', 1),
    ("silik-tools/silik-tools.spec", "xhost-package",
     "EL 10 has no xorg-x11-server-utils; xhost, the one program of it `silik` calls, is a package of its own (AppStream)",
     "lit", "Recommends:     xorg-x11-server-utils\n", "Recommends:     xhost\n", 1),
    ("silik-eda-compat/silik-eda-compat.spec", "xhost-package", "the same: xhost in the place of xorg-x11-server-utils",
     "lit", "Recommends:     xorg-x11-server-utils\n", "Recommends:     xhost\n", 1),
]

# (id, why, kind, old, new, expected count); @EPEL@ in new is the base's minor release
KICKSTART_RULES = [
    ("header", "(the file says what it is)", "re",
     r"\A# SilikOS — kickstart for the installer \(the EL9 base's Anaconda\), x86_64\.",
     "# SilikOS 10 LAB — made by el10/port_system.py from kickstart/silikos.ks (the EL 9 product's) for the EL 10 base's\n"
     "# Anaconda, x86_64 (x86-64-v3). A lab system: docs/EL10.md says what of it has run. What follows is the product's text:\n"
     "# SilikOS — kickstart for the installer (the EL9 base's Anaconda), x86_64.", 1),
    ("base-repos", "the base is AlmaLinux 10", "re",
     r"https://repo\.almalinux\.org/almalinux/9/(BaseOS|AppStream|CRB|extras)/x86_64/os/",
     r"https://repo.almalinux.org/almalinux/10/\1/x86_64/os/", 4),
    ("epel-repo", "EPEL 10 has one tree per minor release of the base (pub/epel/10.2/); pub/epel/10/ is the next minor's", "lit",
     "https://dl.fedoraproject.org/pub/epel/9/Everything/x86_64/", "https://dl.fedoraproject.org/pub/epel/@EPEL@/Everything/x86_64/", 1),
    ("no-silik-win", LEFT_OUT["silik-win"], "lit", "silik-win\n", "", 1),
    ("no-silikos-repos", LEFT_OUT["silikos-repos"], "lit", "boom-boot\nsilikos-repos\n", "boom-boot\n", 1),
    ("authselect-profile",
     "an installation with no profile selected gets the base's default profile with the switch: on EL 10 that profile is "
     "`local` (seen: the system the lab installs has the profile local with without-nullok, workflow run 43587575827)", "lit",
     "else authselect select sssd without-nullok --force || :; fi", "else authselect select local without-nullok --force || :; fi", 1),
]

# what must not be left in the lab's kickstart
KICKSTART_LEFT = [r"almalinux/9/", r"epel/9/", r"^silik-win$", r"^silikos-repos$", r"@EPEL@"]


def apply(rules, name, text, fill=None):
    """TEXT with the rules for NAME applied; rules are (id, why, kind, old, new, count)."""
    for (rid, why, kind, old, new, want) in rules:
        if fill:
            for k, v in fill.items():
                new = new.replace(k, v)
        if kind == "lit":
            n = text.count(old)
            text = text.replace(old, new)
        else:
            text, n = re.subn(old, lambda m, new=new: m.expand(new) if "\\1" in new else new, text, flags=re.M)
        if n != want:
            sys.exit("error: rule '%s' expected %d place(s) in %s and found %d: the EL 9 file has changed there; "
                     "look at the rule in el10/port_system.py" % (rid, want, name, n))
    return text


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def kickstart(epel):
    if not re.match(r"^10\.\d+$", epel):
        sys.exit("error: --kickstart wants the base's minor release, as 10.2 (saw %r)" % epel)
    text = apply(KICKSTART_RULES, "kickstart/silikos.ks", read(KICKSTART), {"@EPEL@": epel})
    for pat in KICKSTART_LEFT:
        m = re.search(pat, text, flags=re.M)
        if m:
            sys.exit("error: the lab's kickstart still has %r after the rules" % m.group(0))
    return text


def packages(dst):
    """DST/<package>/ for every package of the lab; the names made."""
    sys.path.insert(0, EL10)
    import port_shell
    made = []
    os.makedirs(dst, exist_ok=True)
    by_file = {}
    for r in PACKAGE_RULES:
        by_file.setdefault(r[0], []).append(r[1:])
    seen = set()
    for name in sorted(os.listdir(PACKAGES)):
        src = os.path.join(PACKAGES, name)
        if not os.path.isdir(src) or name in LEFT_OUT:
            continue
        out = os.path.join(dst, name)
        if os.path.exists(out):
            shutil.rmtree(out)
        shutil.copytree(src, out, ignore=shutil.ignore_patterns("__pycache__"))
        for rel, rules in by_file.items():
            if rel.split("/", 1)[0] != name:
                continue
            path = os.path.join(dst, rel)
            text = apply(rules, "packages/" + rel, read(path))
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            seen.add(rel)
        if name == "silikos-desktop":
            ext = os.path.join(out, "files", "shell-ext")
            port = port_shell.build()
            for n in ("extension.js", "flow.js"):
                with open(os.path.join(ext, n), "w", encoding="utf-8") as f:
                    f.write(port[n])
            shutil.copy(os.path.join(EL10, "shell-ext", "metadata.json"), os.path.join(ext, "metadata.json"))
        made.append(name)
    missing = sorted(set(by_file) - seen)
    if missing:
        sys.exit("error: rules for files that are in no package of the lab: %s" % ", ".join(missing))
    for name in LEFT_OUT:
        if not os.path.isdir(os.path.join(PACKAGES, name)):
            sys.exit("error: %s is left out of the lab and is not a package of the product any more" % name)
    return made


def main(argv):
    if argv[:1] == ["--rules"]:
        for (rel, rid, why, kind, old, new, want) in PACKAGE_RULES:
            print("%-26s %-42s %d place(s)\n%s%s" % (rid, "packages/" + rel, want, " " * 27, why))
        for (rid, why, kind, old, new, want) in KICKSTART_RULES:
            print("%-26s %-42s %d place(s)\n%s%s" % (rid, "kickstart/silikos.ks", want, " " * 27, why))
        for name, why in sorted(LEFT_OUT.items()):
            print("%-26s %-42s left out\n%s%s" % (name, "packages/" + name, " " * 27, why))
        return 0
    if argv[:1] == ["--kickstart"] and len(argv) == 2:
        sys.stdout.write(kickstart(argv[1]))
        return 0
    if argv[:1] == ["--packages"] and len(argv) == 2:
        for name in packages(argv[1]):
            print(name)
        return 0
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
