# Tests of `silik manifest export | diff | apply`: two machines the same from one file. dnf, rpm and the rest are
# stand-ins here; the real round trip (export, install, diff, apply --prune, apply) ran in an almalinux:9 container
# (docs/STATUS.md).
#   python3 -m unittest discover -s tests -v
import json
import os
import unittest

from test_dev import call, text, tools
from test_silik import silik

A = "x86_64"


def man(packages=(), kernel=(), **over):
    m = {"manifest": 1, "silik": "0.6.14", "base": {"id": "almalinux", "version": "9.8", "arch": A, "release": "AlmaLinux release 9.8 (Olive Jaguar)"},
         "repos": ["appstream", "baseos"], "packages": sorted(packages),
         "kernel": {"running": "5.14.0-687.66.2.el9_8.x86_64", "packages": sorted(kernel), "args": ["quiet", "rhgb", "vsyscall=xonly"]},
         "settings": {"look": "silik", "accent": "ink", "glass": "on",
                      "power": {"auto": True, "profile": None, "ac": "performance", "battery": "balanced"}, "update_auto": "all"},
         "boxes": [], "tools": {"versions": {}, "ides": {}}}
    m.update(over)
    return m


BASH = "bash-0:5.1.8-9.el9.x86_64 @baseos"
KSH = "ksh-3:1.0.6-7.el9.x86_64 @appstream"
K1 = "kernel-core-0:5.14.0-687.66.2.el9_8.x86_64 @baseos"
K2 = "kernel-core-0:5.14.0-687.70.1.el9_8.x86_64 @baseos"


def slurp(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def runs(steps):
    return [" ".join(w) for k, w in steps if k == "run"]


def says(steps):
    return "\n".join(w for k, w in steps if k == "say")


class Names(unittest.TestCase):
    def test_nevra(self):
        self.assertEqual(silik.nevra("bash", "0", "5.1.8", "9.el9", "x86_64"), "bash-0:5.1.8-9.el9.x86_64")
        self.assertEqual(silik.nevra_parse("gcc-c++-0:11.5.0-14.el9.alma.1.x86_64"), ("gcc-c++", "x86_64", "0:11.5.0-14.el9.alma.1"))
        self.assertEqual(silik.nevra_parse("compat-openssl11-1:1.1.1k-5.el9_8.6.x86_64"), ("compat-openssl11", "x86_64", "1:1.1.1k-5.el9_8.6"))
        self.assertIsNone(silik.nevra_parse("not a package"))

    def test_evr(self):
        self.assertEqual(silik.evr_cmp("0:2.34-284.el9_8.4", "0:2.34-283.el9_8"), 1)
        self.assertEqual(silik.evr_cmp("0:9.9-1", "1:1.0-1"), -1)         # the epoch first
        self.assertEqual(silik.evr_cmp("0:1.0-1.el9", "0:1.0-1.el9"), 0)

    def test_the_kernels_command_line_without_this_machines_disks(self):
        got = silik.kernel_args("BOOT_IMAGE=(hd0,gpt2)/vmlinuz-5.14 root=/dev/mapper/a-root ro resume=UUID=1234 rd.lvm.lv=a/root "
                                "rd.luks.uuid=luks-99 rhgb quiet vsyscall=xonly crashkernel=1G-4G:192M")
        self.assertEqual(got, ["crashkernel=1G-4G:192M", "quiet", "rhgb", "vsyscall=xonly"])


class Diff(unittest.TestCase):
    def test_the_same(self):
        self.assertEqual(silik.manifest_diff(man([BASH, KSH], [K1]), man([BASH, KSH], [K1])), {})

    def test_the_repository_a_package_came_from_is_not_a_difference(self):
        self.assertEqual(silik.manifest_diff(man([BASH.replace("@baseos", "@anaconda")]), man([BASH])), {})

    def test_packages(self):
        d = silik.pkg_diff([BASH, "zlib-0:1.2.11-41.el9.x86_64", "old-0:2.0-1.el9.noarch", "glibc-0:2.34-284.el9.x86_64"],
                           [BASH, KSH, "old-0:1.0-1.el9.noarch", "glibc-0:2.34-285.el9.x86_64"])
        self.assertEqual(d["install"], ["glibc-0:2.34-285.el9.x86_64", "ksh-3:1.0.6-7.el9.x86_64"])
        self.assertEqual(d["downgrade"], ["old-0:1.0-1.el9.noarch"])
        self.assertEqual(d["remove"], ["zlib.x86_64"])
        self.assertEqual(sorted(x[0] for x in d["changed"]), ["glibc.x86_64", "old.noarch"])

    def test_two_architectures_of_one_name_are_two_packages(self):
        d = silik.pkg_diff(["glibc-0:2.34-1.el9.x86_64"], ["glibc-0:2.34-1.el9.x86_64", "glibc-0:2.34-1.el9.i686"])
        self.assertEqual((d["install"], d["downgrade"], d["remove"]), (["glibc-0:2.34-1.el9.i686"], [], []))

    def test_kernels_stand_side_by_side(self):
        d = silik.pkg_diff([K1], [K1, K2], installonly=True)
        self.assertEqual((d["install"], d["downgrade"]), ([K2.split(" @")[0]], []))
        d = silik.pkg_diff([K1, K2], [K1], installonly=True)
        self.assertEqual((d["install"], d["remove"]), ([], [K2.split(" @")[0]]))

    def test_the_lines(self):
        have = man([BASH, "zlib-0:1.2.11-41.el9.x86_64", "glibc-0:2.34-284.el9.x86_64"], [K1], repos=["appstream", "baseos", "crb"])
        want = man([BASH, KSH, "glibc-0:2.34-283.el9.x86_64"], [K1, K2], repos=["appstream", "baseos", "epel"],
                   boxes=[{"name": "ic616", "image": "docker.io/library/centos:6", "el": "6"}])
        want["settings"]["look"] = "bar"
        want["kernel"]["args"] = ["quiet", "rhgb", "vsyscall=emulate"]
        d = silik.manifest_diff(have, want)
        self.assertEqual(d["repos"], ["+ epel", "- crb"])
        self.assertEqual(d["packages"], ["+ ksh-3:1.0.6-7.el9.x86_64", "~ glibc.x86_64: 0:2.34-284.el9 here, 0:2.34-283.el9 in the file", "- zlib.x86_64"])
        self.assertEqual(d["kernel"], ["+ " + K2.split(" @")[0], "+ argument vsyscall=emulate", "- argument vsyscall=xonly"])
        self.assertEqual(d["settings"], ["~ look: silik here, bar in the file"])
        self.assertEqual(d["boxes"], ["+ ic616 (el 6, docker.io/library/centos:6)"])
        self.assertNotIn("tools", d)
        d = silik.manifest_diff(man(), man(base={"id": "almalinux", "version": "9.7", "arch": A}))
        self.assertEqual(d["base"], ["~ version: 9.8 here, 9.7 in the file"])


class Plan(unittest.TestCase):
    def test_nothing_to_do(self):
        self.assertEqual(silik.manifest_plan(man([BASH], [K1]), man([BASH], [K1])), [])

    def test_packages_are_never_removed_without_prune(self):
        have, want = man([BASH, KSH]), man([BASH])
        steps = silik.manifest_plan(have, want)
        self.assertEqual(runs(steps), [])
        self.assertIn("1 packages are here and not in the manifest: kept (--prune removes them)", says(steps))
        self.assertEqual(runs(silik.manifest_plan(have, want, prune=True)), ["sudo dnf -y remove ksh.x86_64"])

    def test_install_and_downgrade_are_exact_versions(self):
        steps = silik.manifest_plan(man([BASH, "glibc-0:2.34-284.el9.x86_64"]), man([BASH, KSH, "glibc-0:2.34-283.el9.x86_64"]))
        self.assertEqual(runs(steps), ["sudo dnf -y install ksh-3:1.0.6-7.el9.x86_64", "sudo dnf -y downgrade glibc-0:2.34-283.el9.x86_64"])

    def test_the_kernel_is_left_alone_without_kernel(self):
        have, want = man([BASH], [K1]), man([BASH], [K2])
        steps = silik.manifest_plan(have, want, prune=True)
        self.assertEqual(runs(steps), [])
        self.assertIn("left alone (--kernel installs the manifest's)", says(steps))
        self.assertIn("never removed by this command", says(steps))
        steps = silik.manifest_plan(have, want, prune=True, kernel=True)
        self.assertEqual(runs(steps), ["sudo dnf -y install " + K2.split(" @")[0]])      # installed beside; the one here stays
        self.assertNotIn("remove", " ".join(runs(steps)))

    def test_another_architecture_stops(self):
        steps = silik.manifest_plan(man(), man(base={"id": "almalinux", "version": "9.8", "arch": "aarch64"}))
        self.assertEqual([k for k, _ in steps], ["stop"])

    def test_another_minor_version_is_said(self):
        steps = silik.manifest_plan(man([BASH]), man([BASH, KSH], base={"id": "almalinux", "version": "9.7", "arch": A}))
        self.assertIn("almalinux 9.7 and this system is almalinux 9.8", says(steps))
        self.assertEqual(len(runs(steps)), 1)

    def test_repositories(self):
        steps = silik.manifest_plan(man(repos=["baseos", "extra-here"]), man(repos=["baseos", "epel", "crb", "bad name;x"]))
        self.assertEqual(runs(steps), ["sudo dnf -y install epel-release", "sudo dnf config-manager --set-enabled crb"])
        self.assertIn("left as they are): extra-here", says(steps))

    def test_kernel_arguments(self):
        have, want = man(), man()
        want["kernel"]["args"] = ["quiet", "rhgb", "vsyscall=emulate"]
        steps = silik.manifest_plan(have, want)
        self.assertEqual(runs(steps), ["sudo grubby --update-kernel=ALL --args=vsyscall=emulate"])
        self.assertIn("kept (--prune removes them): vsyscall=xonly", says(steps))
        self.assertIn("sudo grubby --update-kernel=ALL --remove-args=vsyscall=xonly", runs(silik.manifest_plan(have, want, prune=True)))

    def test_settings_go_through_silik(self):
        want = man()
        want["settings"].update(look="bar", accent="steel", glass="off", update_auto="security")
        want["settings"]["power"] = {"auto": False, "profile": "saver", "ac": "performance", "battery": "balanced"}
        steps = silik.manifest_plan(man(), want)
        self.assertEqual([w for k, w in steps if k == "silik"],
                         [["look", "bar", "--accent", "steel", "--glass", "off"], ["power", "saver"], ["update", "--auto", "security"]])
        want["settings"]["power"] = {"auto": True, "profile": None, "ac": "balanced", "battery": "saver"}
        self.assertIn(["power", "auto", "--ac", "balanced", "--battery", "saver"], [w for k, w in silik.manifest_plan(man(), want) if k == "silik"])
        # a value silik does not know is not handed on
        want["settings"].update(look="x; rm", accent="?", glass="maybe", update_auto="never")
        want["settings"]["power"] = {"auto": False, "profile": "turbo"}
        self.assertEqual([w for k, w in silik.manifest_plan(man(), want) if k == "silik"], [])

    def test_boxes_are_made_never_removed(self):
        want = man(boxes=[{"name": "ic616", "image": "docker.io/library/centos:6", "el": "6"},
                          {"name": "uni", "image": "localhost/silik-eda-import/uni", "el": "6"},
                          {"name": "odd", "image": "docker.io/library/ubuntu:24.04", "el": None},
                          {"name": "bad name", "image": "x", "el": "7"}])
        have = man(boxes=[{"name": "mine", "image": "docker.io/library/centos:7", "el": "7"}])
        steps = silik.manifest_plan(have, want, prune=True)
        self.assertEqual([w for k, w in steps if k == "silik"],
                         [["eda", "create", "ic616", "--el", "6"], ["eda", "create", "uni", "--el", "6", "--image", "localhost/silik-eda-import/uni"]])
        self.assertIn("what is installed inside a box is not in a manifest", says(steps))
        self.assertIn("never removed by this command): mine", says(steps))
        self.assertIn("the box odd", says(steps))

    def test_a_vendors_ide_is_said_not_installed(self):
        want = man(tools={"versions": {}, "ides": {"stm32cubeide": "/opt/st/stm32cubeide_2.1.0/stm32cubeide"}})
        steps = silik.manifest_plan(man(), want)
        self.assertEqual(runs(steps), [])
        self.assertIn("silik dev install FILE", says(steps))

    def test_a_place_for_more_sections(self):
        def export(ctx):
            return {"mode": "fast"}

        def diff(have, want):
            return ["~ mode: %s here, %s in the file" % ((have or {}).get("mode"), (want or {}).get("mode"))] if have != want else []

        def plan(have, want, prune):
            return [("silik", ["speed", (want or {}).get("mode")])] if have != want and want else []
        silik.MANIFEST_SECTIONS.append(("speed", export, diff, plan))
        try:
            have, want = man(speed={"mode": "calm"}), man(speed={"mode": "fast"})
            self.assertEqual(silik.manifest_diff(have, want), {"speed": ["~ mode: calm here, fast in the file"]})
            self.assertEqual(silik.manifest_plan(have, want), [("silik", ["speed", "fast"])])
            cm = tools({"dnf": FAKE_DNF})
            d = cm.__enter__()
            self.addCleanup(cm.__exit__, None, None, None)
            with open(os.path.join(d, "installed"), "w") as f:
                f.write(QUERY)
            self.assertEqual(silik.manifest_now(silik.Ctx(True, True))["speed"], {"mode": "fast"})      # and in the export
        finally:
            silik.MANIFEST_SECTIONS.pop()


# stand-ins: dnf answers `repoquery --installed` from a made-up system and notes every other call; no rpm needed
QUERY = ("bash\t0\t5.1.8\t9.el9\tx86_64\t@baseos\tbash-5.1.8-9.el9.src.rpm\n"
         "ksh\t3\t1.0.6\t7.el9\tx86_64\tappstream\tksh-1.0.6-7.el9.src.rpm\n"
         "kernel-core\t0\t5.14.0\t687.66.2.el9_8\tx86_64\tanaconda\tkernel-5.14.0-687.66.2.el9_8.src.rpm\n"
         "kernel-headers\t0\t5.14.0\t687.66.2.el9_8\tx86_64\tappstream\tkernel-5.14.0-687.66.2.el9_8.src.rpm\n"
         "kmod-libs\t0\t28\t11.el9\tx86_64\tbaseos\tkmod-28-11.el9.src.rpm\n"
         "kmod-nvidia\t3\t580.1\t1.el9\tx86_64\tnvidia\tnvidia-kmod-580.1-1.el9.src.rpm\n"
         "gpg-pubkey\t0\tb86b3716\t61e69f29\tnoarch\t\t(none)\n")
FAKE_DNF = '''case "$*" in
  *"repoquery --installed"*) while IFS= read -r l; do printf '%s\n' "$l"; done < "$HOME/installed";;
  *) echo "dnf $*" >> "$HOME/ran";;
esac'''
FAKE_SUDO = 'echo "sudo $*" >> "$HOME/ran"'


class Command(unittest.TestCase):
    def setUp(self):
        self.uid = silik.os.geteuid
        silik.os.geteuid = lambda: 1000

    def tearDown(self):
        silik.os.geteuid = self.uid

    def box(self):
        cm = tools({"dnf": FAKE_DNF, "sudo": FAKE_SUDO})
        d = cm.__enter__()
        self.addCleanup(cm.__exit__, None, None, None)
        with open(os.path.join(d, "installed"), "w") as f:
            f.write(QUERY)
        return d

    def test_export(self):
        d = self.box()
        f = os.path.join(d, "m.json")
        rc, out, err = call("manifest", "export", f)
        self.assertEqual(rc, 0)
        self.assertIn("3 packages, 3 of the kernel", out)
        self.assertIn("no host name, user or address in it", out)
        body = slurp(f)
        m = json.loads(body)
        self.assertEqual(m["packages"], ["bash-0:5.1.8-9.el9.x86_64 @baseos", "kmod-libs-0:28-11.el9.x86_64 @baseos", "ksh-3:1.0.6-7.el9.x86_64 @appstream"])
        # the kernel, what is built with it and a driver built for it are apart: apply leaves them alone
        self.assertEqual([p.split("-0:")[0].split("-3:")[0] for p in m["kernel"]["packages"]], ["kernel-core", "kernel-headers", "kmod-nvidia"])
        self.assertNotIn("gpg-pubkey", body)
        self.assertEqual(sorted(m), ["base", "boxes", "kernel", "manifest", "packages", "repos", "settings", "silik", "tools"])
        self.assertNotIn("host", m)
        self.assertEqual(body, silik.manifest_dump(m))                # sorted keys: the file is its own normal form
        rc, out2, err = call("manifest", "export")                    # to the terminal: the same bytes
        self.assertEqual(out2, body)
        self.assertEqual(os.path.exists(os.path.join(d, "ran")), False)       # nothing but queries

    def test_with_host_is_asked_for(self):
        d = self.box()
        rc, out, err = call("manifest", "export", "--with-host")
        m = json.loads(out)
        self.assertEqual(m["host"]["name"], os.uname().nodename)
        self.assertIn("user", m["host"])
        self.assertIn("cards", m["host"])

    def test_dry_run_writes_nothing(self):
        d = self.box()
        f = os.path.join(d, "m.json")
        rc, out, err = call("--dry-run", "manifest", "export", f)
        self.assertFalse(os.path.exists(f))
        self.assertIn("would write", out)

    def test_diff_and_apply(self):
        d = self.box()
        f = os.path.join(d, "m.json")
        call("manifest", "export", f)
        rc, out, err = call("manifest", "diff", f)
        self.assertEqual((rc, out.strip()), (0, "the same as " + f))
        m = json.loads(slurp(f))
        m["packages"] = ["bash-0:5.1.8-10.el9.x86_64 @baseos", "tcsh-0:6.22.03-6.el9.x86_64 @appstream"]       # newer bash, tcsh; no ksh, no kmod-libs
        m["kernel"]["packages"].append("kernel-core-0:5.14.0-687.70.1.el9_8.x86_64 @baseos")
        m["settings"]["look"] = "island"
        with open(f, "w") as fh:
            json.dump(m, fh)
        rc, out, err = call("manifest", "diff", f)
        self.assertEqual(rc, 1)
        self.assertIn("~ bash.x86_64: 0:5.1.8-9.el9 here, 0:5.1.8-10.el9 in the file", out)
        self.assertIn("+ tcsh-0:6.22.03-6.el9.x86_64", out)
        self.assertIn("- ksh.x86_64", out)
        self.assertIn("+ kernel-core-0:5.14.0-687.70.1.el9_8.x86_64", out)
        rc, js, err = call("manifest", "diff", f, "--json")
        self.assertEqual(json.loads(js)["same"], False)
        # --dry-run: every command printed, none run
        rc, out, err = call("--dry-run", "manifest", "apply", f)
        self.assertEqual(rc, 0)
        self.assertEqual([l for l in out.splitlines() if l.startswith("$ ")],
                         ["$ sudo dnf -y install bash-0:5.1.8-10.el9.x86_64 tcsh-0:6.22.03-6.el9.x86_64", "$ silik look island"])
        self.assertIn("2 packages are here and not in the manifest: kept (--prune removes them)", out)
        self.assertIn("left alone (--kernel installs the manifest's)", out)
        self.assertFalse(os.path.exists(os.path.join(d, "ran")))
        rc, out, err = call("--dry-run", "manifest", "apply", f, "--prune", "--kernel")
        cmds = [l for l in out.splitlines() if l.startswith("$ ")]
        self.assertIn("$ sudo dnf -y remove kmod-libs.x86_64 ksh.x86_64", cmds)
        self.assertIn("$ sudo dnf -y install kernel-core-0:5.14.0-687.70.1.el9_8.x86_64", cmds)
        self.assertEqual([c for c in cmds if "remove" in c and "kernel" in c], [])
        # for real (the stand-ins note what they are handed)
        m["settings"]["look"] = None
        with open(f, "w") as fh:
            json.dump(m, fh)
        rc, out, err = call("manifest", "apply", f)
        self.assertEqual(slurp(os.path.join(d, "ran")).splitlines(), ["sudo dnf -y install bash-0:5.1.8-10.el9.x86_64 tcsh-0:6.22.03-6.el9.x86_64"])

    def test_a_file_that_is_not_a_manifest(self):
        d = self.box()
        f = os.path.join(d, "x.json")
        for body in ("{}", "[1]", '{"manifest": 99}', "not json"):
            with open(f, "w") as fh:
                fh.write(body)
            rc, out, err = call("manifest", "apply", f)
            self.assertEqual(rc, 1, body)
        self.assertEqual(call("manifest", "diff", os.path.join(d, "absent.json"))[0], 1)

    def test_no_package_database_no_manifest(self):
        with tools({}):
            rc, out, err = call("manifest", "export")
        self.assertEqual(rc, 1)
        self.assertIn("neither dnf nor rpm answered", err)


class Around(unittest.TestCase):
    def test_completion_usage_and_the_command_bar(self):
        comp = text("packages/silik-tools/files/silik.bash-completion")
        self.assertIn('manifest) COMPREPLY=($(compgen -W "export diff apply"', comp)
        self.assertIn("--prune --kernel", comp)
        self.assertIn("#   silik manifest export [FILE] [--with-host] | diff FILE [--json] | apply FILE [--prune] [--kernel]", text("packages/silik-tools/files/silik"))
        self.assertIn("manifest", silik.GROUPS)
        from test_silik import bar
        for lang in ("en", "ca", "es"):
            items = {i.address: i for i in bar.system_items(bar.TEXT[lang])}
            self.assertEqual(items["sys/manifest"].twin, "silik manifest export")
            self.assertTrue(items["sys/manifest"].terminal)


if __name__ == "__main__":
    unittest.main()
