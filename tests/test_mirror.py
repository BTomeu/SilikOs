# `silik mirror` (packages/silik-tools/files/plugins/mirror.py; docs/OFFLINE.md): the package sources as a local copy
# for a network without Internet, the offline ISO's script and its workflow.
# The commands dnf, rpmkeys, rpm, createrepo_c, modifyrepo_c, gpg and sudo are stand-ins here (tests/offline/standin.py:
# text files for packages and keys); what the real ones do with real packages was run in almalinux:9 containers by
# tests/offline/container_run.sh, and its output of 13/11/2026 is kept in tests/offline/run-2026-11-13.log.
#   python3 -m unittest discover -s tests -v
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SILIK = os.path.join(ROOT, "packages/silik-tools/files/silik")
PLUGIN = os.path.join(ROOT, "packages/silik-tools/files/plugins/mirror.py")
STANDIN = os.path.join(ROOT, "tests/offline/standin.py")


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


mirror = load("silik_mirror_under_test", PLUGIN)
ALMA, EPEL = mirror.KEYS["almalinux"][1], mirror.KEYS["epel"][1]


def read(rel):
    with open(os.path.join(ROOT, rel)) as f:
        return f.read()


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        j = lambda *a: os.path.join(self.t, *a)
        self.j = j
        for d in ("bin", "up/BaseOS", "up/AppStream", "up/CRB", "up/extras", "up/epel", "keys", "reposd", "state", "own"):
            os.makedirs(j(d))
        for name in ("dnf", "rpmkeys", "rpm", "createrepo_c", "modifyrepo_c", "gpg", "sudo"):
            os.symlink(STANDIN, j("bin", name))
        self.write("keys/RPM-GPG-KEY-AlmaLinux-9", "fpr: %s\n" % ALMA)
        self.write("keys/RPM-GPG-KEY-EPEL-9", "fpr: %s\n" % EPEL)
        self.pkg("up/BaseOS/bash-5.1-1.el9.x86_64.rpm", ALMA)
        self.pkg("up/BaseOS/tzdata-2026a-1.el9.noarch.rpm", ALMA)
        self.pkg("up/AppStream/gnome-shell-40.10-1.el9.x86_64.rpm", ALMA)
        self.pkg("up/epel/tio-3.9-1.el9.x86_64.rpm", EPEL)
        self.pkg("own/silik-tools-0.6.14-1.el9.noarch.rpm", None)
        self.write("up/BaseOS/comps.xml", "<comps><group><id>core</id></group></comps>\n")
        self.write("up/AppStream/comps.xml", "<comps><environment><id>workstation-product-environment</id></environment></comps>\n")
        self.write("up/AppStream/modules.yaml", "---\n")
        self.write("up/BaseOS/updateinfo.xml", "<updates/>\n")
        self.write("reposd/base.repo", "[baseos]\nname=BaseOS\nbaseurl=https://example.invalid/BaseOS\nenabled=1\ngpgcheck=1\n\n"
                                       "[baseos-debuginfo]\nname=debug\nbaseurl=https://example.invalid/debug\nenabled=0\n")
        self.write("reposd/epel.repo", "[epel]\nname=EPEL\nmetalink=https://example.invalid/epel\nenabled=1\n")
        self.env = dict(os.environ, PATH=j("bin") + os.pathsep + os.environ["PATH"], STANDIN_UPSTREAM=j("up"),
                        STANDIN_LOG=j("log"), SILIK_MIRROR_KEYS=j("keys"), SILIK_MIRROR_REPOSD=j("reposd"),
                        SILIK_MIRROR_STATE=j("state"), SILIK_MIRROR_UNPRIVILEGED="1", SILIK_ARCH="x86_64",
                        SILIK_STATE=j("silik-state"), XDG_RUNTIME_DIR=j("nowhere"))
        self.m = j("m")

    def tearDown(self):
        shutil.rmtree(self.t)

    def write(self, rel, text):
        with open(self.j(rel), "w") as f:
            f.write(text)

    def pkg(self, rel, signer, built=1000):
        self.write(rel, ("signed-by: %s\n" % signer if signer else "unsigned\n") + "built: %d\npayload of %s\n" % (built, os.path.basename(rel)))

    def silik(self, *argv, stdin=None):
        r = subprocess.run([sys.executable, SILIK] + list(argv), capture_output=True, text=True, env=self.env, input=stdin)
        return r.returncode, r.stdout, r.stderr

    def ok(self, *argv, **kw):
        rc, out, err = self.silik(*argv, **kw)
        self.assertEqual(rc, 0, out + err)
        return out

    def create(self, *more):
        return self.ok("mirror", "create", self.m, "--silikos", self.j("own"), "--yes", *more)

    def manifest(self, d=None):
        with open(os.path.join(d or self.m, "silik-mirror.json")) as f:
            return json.load(f)

    def calls(self, program):
        with open(self.j("log")) as f:
            return [c[1:] for c in map(json.loads, f) if c[0] == program]


class TheSet(unittest.TestCase):
    def test_the_sources_and_the_set_are_the_kickstart_s(self):
        sources, specs, excl = mirror.kickstart(read("kickstart/silikos.ks"))
        self.assertEqual(sources, [(n, u.format(arch="x86_64")) for n, u in mirror.SOURCES])
        self.assertEqual(tuple(specs), mirror.SET)
        self.assertEqual(excl, [])

    def test_an_environment_is_named_as_dnf_s_command_line_takes_it(self):
        # (`dnf install @^NAME` is refused by EL 9.8's dnf 4.14: "Module or Group '^...' is not available")
        self.assertEqual(mirror.dnf_spec("@^workstation-product-environment"), "@workstation-product-environment")
        self.assertEqual(mirror.dnf_spec("@core"), "@core")
        self.assertEqual(mirror.dnf_spec("silik-tools"), "silik-tools")

    def test_the_installer_s_own_packages_are_in_the_set_for_both_architectures(self):
        for arch, boot in (("x86_64", ("grub2-efi-x64", "shim-x64", "grub2-pc")), ("aarch64", ("grub2-efi-aa64", "shim-aa64"))):
            for p in boot:
                self.assertIn(p, mirror.INSTALLER[arch])
        for p in ("@core", "kernel", "efibootmgr", "langpacks-ca", "langpacks-es", "lvm2", "cryptsetup", "dnf-plugins-core", "createrepo_c"):
            self.assertIn(p, mirror.INSTALLER[""])

    def test_a_kickstart_s_file_sources_and_comments_are_not_network_sources(self):
        s, p, x = mirror.kickstart("url --url=http://h/os/\nrepo --name=a --baseurl=file:///run/x\n# repo --name=b --baseurl=http://h/b\n"
                                   "%packages\n@core\nfoo # why\n-bar\n%end\n%post\nrepo --name=c --baseurl=http://h/c\n%end\n")
        self.assertEqual((s[0], p, x), (("BaseOS", "http://h/os/"), ["@core", "foo"], ["bar"]))


class Create(Base):
    def test_a_mirror_holds_each_source_s_packages_checked_and_a_manifest_of_every_file(self):
        out = self.create()
        m = self.manifest()
        rpms = sorted(r for r in m["files"] if r.endswith(".rpm"))
        self.assertEqual(rpms, ["AppStream/Packages/gnome-shell-40.10-1.el9.x86_64.rpm", "BaseOS/Packages/bash-5.1-1.el9.x86_64.rpm",
                                "BaseOS/Packages/tzdata-2026a-1.el9.noarch.rpm", "epel/Packages/tio-3.9-1.el9.x86_64.rpm",
                                "silikos/Packages/silik-tools-0.6.14-1.el9.noarch.rpm"])
        for rel, e in m["files"].items():
            self.assertEqual(e["sha256"], sha(os.path.join(self.m, rel)), rel)
            self.assertEqual(e["size"], os.path.getsize(os.path.join(self.m, rel)), rel)
        self.assertIn("keys/RPM-GPG-KEY-AlmaLinux-9", m["files"])
        self.assertIn("BaseOS/repodata/repomd.xml", m["files"])
        self.assertEqual(m["keys"]["epel"]["fingerprint"], EPEL)
        self.assertEqual((m["generation"], m["arch"], m["keep"]), (1, "x86_64", 3))
        self.assertEqual(m["repos"]["BaseOS"]["key"], "almalinux")
        self.assertEqual(m["repos"]["epel"]["key"], "epel")
        self.assertIsNone(m["repos"]["silikos"]["key"])
        self.assertNotIn("CRB", m["repos"])                   # (a source nothing of the set comes from)
        # the installer's groups, modules and advisories travel with the metadata
        self.assertEqual(m["repos"]["AppStream"]["metadata"], ["group", "modules"])
        self.assertEqual(m["repos"]["BaseOS"]["metadata"], ["group", "updateinfo"])
        self.assertIn("workstation-product-environment", open(os.path.join(self.m, "AppStream/comps.xml")).read())
        self.assertIn("generation 1: 5 packages added", out)
        self.assertIn("not signed today", out)

    def test_dnf_resolves_as_the_installer_does_and_every_command_is_printed(self):
        out = self.create()
        dnf = [c for c in self.calls("dnf") if "install" in c][0]
        root = os.path.join(self.m, ".root")
        for word in ("--installroot=" + root, "--releasever=9", "--setopt=module_platform_id=platform:el9", "--downloadonly", "-y",
                     "--setopt=reposdir=" + root + "/etc/yum.repos.d", "--repo=BaseOS", "--repo=epel", "--repo=silikos",
                     "--repofrompath=BaseOS,https://repo.almalinux.org/almalinux/9/BaseOS/x86_64/os/",
                     "@workstation-product-environment", "silik-dev", "kernel", "@core", "grub2-efi-x64", "shim-x64"):
            self.assertIn(word, dnf)
        self.assertNotIn("grub2-efi-aa64", dnf)
        self.assertNotIn("--forcearch=x86_64", dnf)
        self.assertNotIn("@^workstation-product-environment", dnf)
        for line in ("$ dnf --installroot=", "$ rpmkeys --dbpath ", "--checksig <2 packages of BaseOS>", "$ createrepo_c --quiet --groupfile",
                     "$ modifyrepo_c --mdtype=modules"):
            self.assertIn(line, out)
        # each source's packages against that source's key only
        imports = [c[-1] for c in self.calls("rpmkeys") if "--import" in c]
        self.assertEqual(sorted(os.path.basename(i) for i in imports), ["RPM-GPG-KEY-AlmaLinux-9", "RPM-GPG-KEY-EPEL-9"])

    def test_the_other_architecture(self):
        self.ok("mirror", "create", self.m, "--silikos", self.j("own"), "--yes", "--arch", "aarch64")
        dnf = [c for c in self.calls("dnf") if "install" in c][0]
        self.assertIn("--forcearch=aarch64", dnf)
        self.assertIn("--repofrompath=epel,https://dl.fedoraproject.org/pub/epel/9/Everything/aarch64/", dnf)
        self.assertIn("grub2-efi-aa64", dnf)
        self.assertNotIn("grub2-pc", dnf)
        self.assertEqual(self.manifest()["arch"], "aarch64")

    def test_dnf_asks_before_downloading_unless_yes(self):
        rc, out, err = self.silik("mirror", "create", self.m, "--silikos", self.j("own"), stdin="n\n")
        self.assertNotEqual(rc, 0)
        self.assertIn("Total download size", out)
        self.assertIn("Is this ok", out)
        self.assertFalse(os.path.exists(os.path.join(self.m, "silik-mirror.json")))
        self.assertNotIn("-y", [c for c in self.calls("dnf") if "install" in c][0])

    def test_a_package_without_the_source_s_signature_is_refused(self):
        for name, signer in (("evil-1-1.el9.x86_64.rpm", None),           # not signed at all
                             ("evil-1-1.el9.x86_64.rpm", "0" * 40),       # signed by somebody else
                             ("evil-1-1.el9.x86_64.rpm", EPEL)):          # EPEL's signature on a package of BaseOS
            shutil.rmtree(self.m, ignore_errors=True)
            self.pkg("up/BaseOS/" + name, signer)
            rc, out, err = self.silik("mirror", "create", self.m, "--silikos", self.j("own"), "--yes")
            self.assertEqual(rc, 3, out + err)
            self.assertIn("REFUSED", err)
            self.assertIn("BaseOS/evil-1-1.el9.x86_64.rpm", err)
            self.assertFalse(os.path.exists(os.path.join(self.m, "silik-mirror.json")))
            found = [f for _, _, fs in os.walk(self.m) for f in fs if f.startswith("evil")]
            self.assertEqual(found, [], "a refused package stays nowhere")

    def test_a_key_with_another_fingerprint_is_not_taken(self):
        self.write("keys/RPM-GPG-KEY-AlmaLinux-9", "fpr: %s\n" % ("A" * 40))
        rc, out, err = self.silik("mirror", "create", self.m, "--silikos", self.j("own"), "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("its fingerprint is", err)
        self.assertEqual([c for c in self.calls("dnf")], [])
        os.remove(self.j("keys/RPM-GPG-KEY-EPEL-9"))
        self.write("keys/RPM-GPG-KEY-AlmaLinux-9", "fpr: %s\n" % ALMA)
        rc, out, err = self.silik("mirror", "create", self.m, "--silikos", self.j("own"), "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("epel-release", err)

    def test_dry_run_prints_and_writes_nothing(self):
        out = self.ok("--dry-run", "mirror", "create", self.m, "--silikos", self.j("own"))
        self.assertIn("$ dnf --installroot=", out)
        self.assertFalse(os.path.exists(self.m))
        self.assertEqual(self.calls("dnf") + self.calls("rpmkeys") + self.calls("createrepo_c"), [])   # (gpg read the keys' fingerprints)

    def test_what_create_refuses(self):
        rc, _, err = self.silik("mirror", "create", self.m, "--yes")
        self.assertEqual(rc, 1)
        self.assertIn("--silikos", err)
        os.makedirs(self.m)
        self.write("m/something", "x")
        rc, _, err = self.silik("mirror", "create", self.m, "--silikos", self.j("own"), "--yes")
        self.assertIn("not empty", err)
        self.env.pop("SILIK_MIRROR_UNPRIVILEGED")
        if os.geteuid() != 0:
            shutil.rmtree(self.m)
            rc, _, err = self.silik("mirror", "create", self.m, "--silikos", self.j("own"), "--yes")
            self.assertEqual(rc, 1)
            self.assertIn("sudo silik mirror create", err)

    def test_this_machine_s_packages_instead(self):
        self.env["STANDIN_INSTALLED"] = "bash-5.1-1.el9.x86_64 tzdata-2026a-1.el9.noarch vendor-tool-1-1.x86_64 gpg-pubkey-b86b3716-61e69f29"
        out = self.ok("mirror", "create", self.m, "--only-installed", "--yes")
        dnf = [c for c in self.calls("dnf") if "install" in c][0]
        self.assertIn("bash.x86_64", dnf)                    # (by name: the newest version, what an update needs)
        self.assertIn("tzdata.noarch", dnf)
        self.assertIn("--setopt=strict=0", dnf)
        self.assertEqual([x for x in dnf if x.startswith("gpg-pubkey")], [])
        self.assertNotIn("kernel", dnf)
        self.assertIn("vendor-tool", out)                    # (said: installed here, offered by no source)
        self.assertEqual(self.manifest()["set"]["missing"], ["vendor-tool"])


class Update(Base):
    def test_newer_versions_come_in_and_the_last_n_of_each_stay(self):
        self.create("--keep", "2")
        self.pkg("up/BaseOS/tzdata-2026b-1.el9.noarch.rpm", ALMA, 2000)
        out = self.ok("mirror", "update", self.m, "--yes")
        self.assertIn("generation 2: 1 packages added", out)
        have = lambda: sorted(os.listdir(os.path.join(self.m, "BaseOS/Packages")))
        self.assertEqual(have(), ["bash-5.1-1.el9.x86_64.rpm", "tzdata-2026a-1.el9.noarch.rpm", "tzdata-2026b-1.el9.noarch.rpm"])
        m = self.manifest()
        self.assertEqual(m["files"]["BaseOS/Packages/tzdata-2026b-1.el9.noarch.rpm"]["gen"], 2)
        self.assertEqual(m["files"]["BaseOS/Packages/tzdata-2026a-1.el9.noarch.rpm"]["gen"], 1)
        self.pkg("up/BaseOS/tzdata-2026c-1.el9.noarch.rpm", ALMA, 3000)
        out = self.ok("mirror", "update", self.m, "--yes")
        self.assertIn("1 old versions removed", out)
        self.assertEqual(have(), ["bash-5.1-1.el9.x86_64.rpm", "tzdata-2026b-1.el9.noarch.rpm", "tzdata-2026c-1.el9.noarch.rpm"])
        m = self.manifest()
        self.assertNotIn("BaseOS/Packages/tzdata-2026a-1.el9.noarch.rpm", m["files"])
        self.assertEqual([h["added"] for h in m["history"]], [5, 1, 1])
        self.assertEqual(self.ok("mirror", "verify", self.m).count("▼"), 0)
        # nothing the mirror holds is downloaded again (the stand-in copies only what dnf's cache lacks; the real dnf
        # takes the newest version only, so the source's older ones are taken away here)
        os.remove(self.j("up/BaseOS/tzdata-2026a-1.el9.noarch.rpm"))
        self.assertIn("generation 4: 0 packages added", self.ok("mirror", "update", self.m, "--yes"))

    def test_a_newer_package_of_silikos_s_own(self):
        self.create()
        os.makedirs(self.j("own2"))
        self.pkg("own2/silik-tools-0.6.15-1.el9.noarch.rpm", None, 5000)
        self.ok("mirror", "update", self.m, "--silikos", self.j("own2"), "--yes")
        self.assertEqual(sorted(os.listdir(os.path.join(self.m, "silikos/Packages"))),
                         ["silik-tools-0.6.14-1.el9.noarch.rpm", "silik-tools-0.6.15-1.el9.noarch.rpm"])

    def test_an_update_that_brings_a_bad_package_leaves_the_mirror_as_it_was(self):
        self.create()
        before = open(os.path.join(self.m, "silik-mirror.json"), "rb").read()
        self.pkg("up/epel/tio-4.0-1.el9.x86_64.rpm", None)
        rc, _, err = self.silik("mirror", "update", self.m, "--yes")
        self.assertEqual(rc, 3)
        self.assertIn("epel/tio-4.0-1.el9.x86_64.rpm", err)
        self.assertEqual(open(os.path.join(self.m, "silik-mirror.json"), "rb").read(), before)
        self.assertEqual(os.listdir(os.path.join(self.m, "epel/Packages")), ["tio-3.9-1.el9.x86_64.rpm"])


class Verify(Base):
    def test_a_good_mirror_verifies_and_each_kind_of_damage_is_named(self):
        self.create()
        out = self.ok("mirror", "verify", self.m)
        self.assertIn("everything is as the manifest and the keys say", out)
        self.assertIn("not signed today", out)                # (said, not hidden: SilikOS's own packages)
        r = json.loads(self.ok("-q", "mirror", "verify", self.m, "--json"))
        self.assertTrue(r["ok"])
        self.assertEqual((r["packages"], r["unsigned"]), (5, 1))
        victim = os.path.join(self.m, "BaseOS/Packages/bash-5.1-1.el9.x86_64.rpm")
        good = open(victim).read()
        cases = (
            (lambda: open(victim, "a").write("x"), "sha256", "bash-5.1"),                                    # a byte more
            (lambda: open(victim, "w").write(good.replace("signed-by: " + ALMA, "unsigned")), "signatures BaseOS", "bash-5.1"),
            (lambda: os.remove(victim), "files", "bash-5.1"),
            (lambda: open(os.path.join(self.m, "epel/Packages/extra-1-1.el9.x86_64.rpm"), "w").write("unsigned\n"), "strangers", "extra-1-1"),
            (lambda: open(os.path.join(self.m, "BaseOS/repodata/repomd.xml"), "a").write(" "), "sha256", "repomd.xml"),
        )
        for damage, row, word in cases:
            shutil.rmtree(self.m)
            shutil.rmtree(self.j("log"), ignore_errors=True)
            self.create()
            damage()
            rc, out, err = self.silik("-q", "mirror", "verify", self.m, "--json")
            self.assertEqual(rc, 1, row)
            r = json.loads(out)
            self.assertFalse(r["ok"])
            bad = {x["what"]: x["detail"] for x in r["rows"] if x["state"] == "bad"}
            self.assertIn(row, bad, bad)
            self.assertIn(word, bad[row])

    def test_what_cannot_be_checked_is_not_ok(self):
        self.create()
        os.remove(self.j("keys/RPM-GPG-KEY-EPEL-9"))
        rc, out, _ = self.silik("mirror", "verify", self.m)
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"\? signatures epel +not checked")
        self.assertIn("NOT VERIFIED", out)
        # the mirror's own copy of a key is taken only when asked, and only with the known fingerprint
        self.assertEqual(self.silik("mirror", "verify", self.m, "--mirror-keys")[0], 0)
        self.write("m/keys/RPM-GPG-KEY-EPEL-9", "fpr: %s\n" % ("B" * 40))
        rc, out, _ = self.silik("mirror", "verify", self.m, "--mirror-keys")
        self.assertEqual(rc, 1)
        self.assertIn("its fingerprint is", out)

    def test_the_file_alone_verifies_without_silik(self):
        # (the offline ISO's kickstart runs it so, in the installer's environment, on a medium that cannot be written)
        self.create()
        os.chmod(self.m, 0o555)
        try:
            r = subprocess.run([sys.executable, PLUGIN, "verify", self.m, "--keys", self.j("keys")], capture_output=True, text=True, env=self.env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("everything is as the manifest and the keys say", r.stdout)
            open(os.path.join(self.m, "BaseOS/Packages/bash-5.1-1.el9.x86_64.rpm"), "a").write("x")
            r = subprocess.run([sys.executable, PLUGIN, "verify", self.m, "--keys", self.j("keys")], capture_output=True, text=True, env=self.env)
            self.assertEqual(r.returncode, 1)
            r = subprocess.run([sys.executable, PLUGIN, "create", self.j("x")], capture_output=True, text=True, env=self.env)
            self.assertEqual(r.returncode, 2)                 # (alone, it only verifies)
        finally:
            os.chmod(self.m, 0o755)

    def test_a_manifest_cannot_name_a_file_outside_the_mirror(self):
        self.create()
        m = self.manifest()
        m["files"]["../../etc/passwd"] = {"sha256": "0" * 64, "size": 1}
        with open(os.path.join(self.m, "silik-mirror.json"), "w") as f:
            json.dump(m, f)
        rc, _, err = self.silik("mirror", "verify", self.m)
        self.assertEqual(rc, 1)
        self.assertIn("outside the mirror", err)


class Serve(Base):
    def test_plain_http_read_only_and_says_what_it_is_not(self):
        self.create()
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        p = subprocess.Popen([sys.executable, SILIK, "mirror", "serve", self.m, "--bind", "127.0.0.1", "--port", str(port)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env)
        try:
            base = "http://127.0.0.1:%d" % port
            for _ in range(50):
                try:
                    body = urllib.request.urlopen(base + "/silik-mirror.json", timeout=2).read()
                    break
                except OSError:
                    time.sleep(0.1)
            self.assertEqual(json.loads(body.decode())["generation"], 1)
            got = urllib.request.urlopen(base + "/BaseOS/Packages/bash-5.1-1.el9.x86_64.rpm", timeout=2).read()
            self.assertEqual(hashlib.sha256(got).hexdigest(), self.manifest()["files"]["BaseOS/Packages/bash-5.1-1.el9.x86_64.rpm"]["sha256"])

            def code(path, method="GET", data=None):
                try:
                    return urllib.request.urlopen(urllib.request.Request(base + path, method=method, data=data), timeout=2).status
                except urllib.error.HTTPError as e:
                    return e.code
            self.assertEqual(code("/.root/etc/yum.repos.d/"), 404)        # (dnf's working folder is not the mirror)
            self.assertEqual(code("/BaseOS/"), 404)                       # (no listings)
            self.assertEqual(code("/../../etc/passwd"), 404)
            for method in ("PUT", "POST", "DELETE"):
                self.assertEqual(code("/x", method, b"x"), 501, method)
            self.assertFalse(os.path.exists(os.path.join(self.m, "x")))
            # this machine's dnf at it, and what the client sees of it
            self.ok("mirror", "use", base)
            st = json.loads(self.ok("mirror", "status", "--json"))
            self.assertEqual((st["in_use"], st["url"], st["mirror"]["packages"], st["mirror"]["metadata_as_manifest"]), (True, base, 5, True))
            open(os.path.join(self.m, "epel/repodata/repomd.xml"), "a").write(" ")
            rc, out, _ = self.silik("mirror", "status")
            self.assertEqual(rc, 1)
            self.assertIn("NOT what its manifest says: epel", out)
        finally:
            p.terminate()
            out, _ = p.communicate(timeout=10)
        self.assertIn("No TLS and no authentication", out)
        self.assertIn("read-only", out)

    def test_the_address_is_the_one_the_person_names(self):
        self.create()
        rc, _, err = self.silik("mirror", "serve", self.m)
        self.assertEqual(rc, 2)
        self.assertIn("--bind", err)
        out = self.ok("--dry-run", "mirror", "serve", self.m, "--bind", "192.0.2.7")
        self.assertIn("http://192.0.2.7:8080/", out)


class Use(Base):
    def test_use_points_dnf_at_the_mirror_and_off_puts_everything_back_exactly(self):
        self.create()
        before = {f: open(self.j("reposd", f), "rb").read() for f in os.listdir(self.j("reposd"))}
        os.remove(self.j("log"))
        out = self.ok("mirror", "use", self.m)
        self.assertIn("$ dnf config-manager --set-disabled baseos epel", out)           # (printed; dnf's own tool)
        self.assertIn("2 repositories disabled, not deleted: baseos epel", out)
        self.assertEqual(sorted(os.listdir(self.j("reposd"))), ["base.repo", "epel.repo", "silikos-mirror.repo"])
        repo = open(self.j("reposd/silikos-mirror.repo")).read()
        url = "file://" + self.m
        for line in ("[silikos-mirror-BaseOS]", "baseurl=%s/BaseOS" % url, "[silikos-mirror-epel]", "[silikos-mirror-silikos]"):
            self.assertIn(line, repo)
        sections = dict((s.split("]")[0], s) for s in repo.split("\n[")[1:])
        # the base's packages: signatures on, against this machine's keys (never a key from the mirror's folder)
        self.assertIn("gpgcheck=1\n", sections["silikos-mirror-BaseOS"])
        self.assertIn("gpgkey=file://%s\n" % self.j("keys/RPM-GPG-KEY-AlmaLinux-9"), sections["silikos-mirror-BaseOS"])
        self.assertIn("gpgkey=file://%s\n" % self.j("keys/RPM-GPG-KEY-EPEL-9"), sections["silikos-mirror-epel"])
        self.assertIn("gpgcheck=0\n", sections["silikos-mirror-silikos"])
        self.assertNotIn(self.m + "/keys", repo)
        self.assertIn("enabled=0", open(self.j("reposd/base.repo")).read())
        st = json.loads(self.ok("mirror", "status", "--json"))
        self.assertEqual((st["in_use"], st["disabled"]), (True, ["baseos", "epel"]))
        # a second `use` (another address) keeps the first one's record of what was there before
        self.ok("mirror", "use", "file://" + self.m)
        out = self.ok("mirror", "use", "off")
        self.assertIn("$ dnf config-manager --set-enabled baseos epel", out)
        self.assertIn("2 of 2 repository files are byte for byte as before", out)
        self.assertEqual({f: open(self.j("reposd", f), "rb").read() for f in os.listdir(self.j("reposd"))}, before)
        self.assertEqual(os.listdir(self.j("state")), [])
        self.assertFalse(json.loads(self.ok("mirror", "status", "--json"))["in_use"])
        self.assertIn("no mirror is in use", self.ok("mirror", "use", "off"))
        # no repository file was written by hand or deleted
        for c in self.calls("sudo") if os.geteuid() != 0 else []:
            self.assertNotIn(c[0], ("sed", "tee"))

    def test_a_file_changed_meanwhile_is_not_replaced(self):
        self.create()
        self.ok("mirror", "use", self.m)
        with open(self.j("reposd/epel.repo"), "a") as f:
            f.write("# the administrator's note\n")
        out = self.ok("mirror", "use", "off")
        self.assertIn("epel.repo was changed while the mirror was in use", out)
        text = open(self.j("reposd/epel.repo")).read()
        self.assertIn("the administrator's note", text)
        self.assertIn("enabled=1", text)

    def test_dry_run_changes_nothing(self):
        self.create()
        before = {f: open(self.j("reposd", f), "rb").read() for f in os.listdir(self.j("reposd"))}
        out = self.ok("--dry-run", "mirror", "use", self.m)
        self.assertIn("dnf config-manager --set-disabled baseos epel", out)
        self.assertIn("[silikos-mirror-BaseOS]", out)
        self.assertEqual({f: open(self.j("reposd", f), "rb").read() for f in os.listdir(self.j("reposd"))}, before)
        self.assertEqual(os.listdir(self.j("state")), [])

    def test_what_use_refuses(self):
        self.create()
        rc, _, err = self.silik("mirror", "use", self.j("nowhere"))
        self.assertEqual(rc, 1)
        rc, _, err = self.silik("mirror", "use", "http://127.0.0.1:1/a b")
        self.assertEqual(rc, 1)
        # a machine without dnf's config-manager is told how to take it from the mirror, before anything is changed
        self.env["STANDIN_NO_CONFIG_MANAGER"] = "1"
        rc, _, err = self.silik("mirror", "use", self.m)
        self.assertEqual(rc, 1)
        self.assertIn("--repofrompath=boot,file://%s/BaseOS" % self.m, err)
        self.assertEqual(os.listdir(self.j("state")), [])
        self.env.pop("STANDIN_NO_CONFIG_MANAGER")
        self.env["SILIK_ARCH"] = "aarch64"
        rc, _, err = self.silik("mirror", "use", self.m)
        self.assertIn("is for x86_64, this machine is aarch64", err)
        self.env["SILIK_ARCH"] = "x86_64"
        open(os.path.join(self.m, "BaseOS/repodata/repomd.xml"), "a").write(" ")
        rc, _, err = self.silik("mirror", "use", self.m)
        self.assertEqual(rc, 3)
        self.assertIn("does not serve what its manifest says", err)
        self.assertEqual(os.listdir(self.j("reposd")).count("silikos-mirror.repo"), 0)

    def test_a_missing_key_of_the_base_comes_from_the_mirror_only_with_the_known_fingerprint(self):
        self.create()
        os.remove(self.j("keys/RPM-GPG-KEY-EPEL-9"))
        out = self.ok("mirror", "use", self.m)
        self.assertIn("taken from the mirror, its fingerprint is the known " + EPEL, out)
        self.assertTrue(os.path.isfile(self.j("keys/RPM-GPG-KEY-EPEL-9")))
        self.ok("mirror", "use", "off")
        self.assertFalse(os.path.exists(self.j("keys/RPM-GPG-KEY-EPEL-9")))
        self.write("m/keys/RPM-GPG-KEY-EPEL-9", "fpr: %s\n" % ("C" * 40))        # (somebody's own key under EPEL's name)
        m = self.manifest()
        m["files"]["keys/RPM-GPG-KEY-EPEL-9"]["sha256"] = sha(os.path.join(self.m, "keys/RPM-GPG-KEY-EPEL-9"))
        json.dump(m, open(os.path.join(self.m, "silik-mirror.json"), "w"))
        out = self.ok("mirror", "use", self.m)
        self.assertIn("the mirror's copy is not taken", out)
        self.assertFalse(os.path.exists(self.j("keys/RPM-GPG-KEY-EPEL-9")))

    def test_signed_metadata_is_checked_by_dnf_when_the_lab_s_key_is_given(self):
        self.create("--sign", "LABKEY")
        m = self.manifest()
        self.assertEqual(m["sign"], "LABKEY")
        self.assertTrue(os.path.isfile(os.path.join(self.m, "BaseOS/repodata/repomd.xml.asc")))
        self.assertTrue(os.path.isfile(os.path.join(self.m, "silik-mirror.json.asc")))
        out = self.ok("mirror", "use", self.m)
        self.assertIn("without --key FILE", out)
        self.assertIn("repo_gpgcheck=0", open(self.j("reposd/silikos-mirror.repo")).read())
        self.write("lab.asc", "fpr: LABKEY\n")
        self.ok("mirror", "use", self.m, "--key", self.j("lab.asc"))
        repo = open(self.j("reposd/silikos-mirror.repo")).read()
        self.assertEqual(repo.count("repo_gpgcheck=1"), len(m["repos"]))
        self.assertIn(self.j("keys/RPM-GPG-KEY-silik-mirror"), repo)
        self.ok("mirror", "use", "off")
        self.assertFalse(os.path.exists(self.j("keys/RPM-GPG-KEY-silik-mirror")))
        rc, out, _ = self.silik("mirror", "verify", self.m)                 # (signed, and no key to check it with)
        self.assertEqual(rc, 1)
        self.assertRegex(out, r"\? metadata signature")


class Pack(Base):
    def test_the_whole_mirror_and_a_delta_cross_the_air_gap(self):
        self.create()
        out = self.ok("mirror", "pack", self.m, "-o", self.j("full.tar"))
        self.assertIn("the whole mirror: 5 of 5 packages", out)
        self.assertIn(sha(self.j("full.tar")), open(self.j("full.tar.sha256")).read())
        with tarfile.open(self.j("full.tar")) as t:
            names = t.getnames()
        self.assertIn("silik-mirror.json", names)
        self.assertFalse([n for n in names if n.startswith(".") or "/.root" in n])    # (dnf's working folder stays)
        lab = self.j("lab")
        out = self.ok("mirror", "unpack", self.j("full.tar"), lab)
        self.assertIn("everything is as the manifest and the keys say", out)
        self.pkg("up/BaseOS/tzdata-2026b-1.el9.noarch.rpm", ALMA, 2000)
        self.ok("mirror", "update", self.m, "--keep", "1", "--yes")
        out = self.ok("mirror", "pack", self.m, "-o", self.j("delta.tar"), "--since-gen", "1")
        self.assertIn("a delta: 1 of 5 packages", out)
        with tarfile.open(self.j("delta.tar")) as t:
            self.assertEqual([n for n in t.getnames() if n.endswith(".rpm")], ["BaseOS/Packages/tzdata-2026b-1.el9.noarch.rpm"])
        today = time.strftime("%Y-%m-%d")
        self.assertIn("a delta: 5 of 5", self.ok("--dry-run", "mirror", "pack", self.m, "-o", self.j("d2.tar"), "--since", today))
        self.assertIn("a delta: 0 of 5", self.ok("--dry-run", "mirror", "pack", self.m, "-o", self.j("d2.tar"), "--since", "2999-01-01"))
        out = self.ok("mirror", "unpack", self.j("delta.tar"), lab)
        self.assertIn("generation 2 unpacked", out)
        self.assertIn("everything is as the manifest and the keys say", out)
        # the lab's mirror is now the same as the one outside, the pruned version gone
        self.assertEqual(sorted(os.listdir(os.path.join(lab, "BaseOS/Packages"))), sorted(os.listdir(os.path.join(self.m, "BaseOS/Packages"))))
        self.assertEqual(self.manifest(lab)["files"], self.manifest()["files"])

    def test_a_delta_over_nothing_and_a_tar_that_is_not_a_pack_are_refused(self):
        self.create()
        self.pkg("up/BaseOS/tzdata-2026b-1.el9.noarch.rpm", ALMA, 2000)
        self.ok("mirror", "update", self.m, "--yes")
        self.ok("mirror", "pack", self.m, "-o", self.j("delta.tar"), "--since-gen", "1")
        rc, _, err = self.silik("mirror", "unpack", self.j("delta.tar"), self.j("empty"))
        self.assertEqual(rc, 3)
        self.assertIn("is a delta and this mirror lacks", err)
        with tarfile.open(self.j("evil.tar"), "w") as t:
            ti = tarfile.TarInfo("../outside")
            ti.size = 0
            t.addfile(ti)
        rc, _, err = self.silik("mirror", "unpack", self.j("evil.tar"), self.j("lab"))
        self.assertEqual(rc, 3)
        self.assertIn("is not a pack of a mirror", err)
        self.assertFalse(os.path.exists(self.j("outside")))
        with tarfile.open(self.j("link.tar"), "w") as t:
            ti = tarfile.TarInfo("BaseOS")
            ti.type, ti.linkname = tarfile.SYMTYPE, "/etc"
            t.addfile(ti)
        self.assertEqual(self.silik("mirror", "unpack", self.j("link.tar"), self.j("lab"))[0], 3)

    def test_a_signed_mirror_packs_each_file_once(self):
        # (found in the real run of 13/11/2026: a signature listed twice went into the tar as a link, and unpack
        # refused its own pack)
        self.create("--sign", "LABKEY")
        self.ok("mirror", "pack", self.m, "-o", self.j("full.tar"))
        with tarfile.open(self.j("full.tar")) as t:
            members = t.getmembers()
        self.assertEqual([ti.name for ti in members if not ti.isfile()], [])
        self.assertEqual(len(members), len(set(ti.name for ti in members)))
        self.assertIn("BaseOS/repodata/repomd.xml.asc", [ti.name for ti in members])
        self.assertIn("silik-mirror.json.asc", [ti.name for ti in members])
        rc, out, err = self.silik("mirror", "unpack", self.j("full.tar"), self.j("lab"))
        self.assertIn("generation 1 unpacked", out, err)
        self.assertEqual(rc, 1)                               # (signed metadata and no key given: not checked is not ok)
        self.assertRegex(out, r"\? metadata signature")

    def test_a_pack_damaged_on_the_way_does_not_verify(self):
        self.create()
        self.ok("mirror", "pack", self.m, "-o", self.j("full.tar"))
        lab = self.j("lab")
        self.ok("mirror", "unpack", self.j("full.tar"), lab)
        open(os.path.join(lab, "epel/Packages/tio-3.9-1.el9.x86_64.rpm"), "a").write("x")
        rc, out, _ = self.silik("mirror", "verify", lab)
        self.assertEqual(rc, 1)


class OfflineIso(unittest.TestCase):
    """tools/build_offline_iso.sh and .github/workflows/offline.yml, read as text (what they do when run: docs/STATUS.md)"""

    def test_the_script_is_new_and_leaves_the_network_installer_s_alone(self):
        s = read("tools/build_offline_iso.sh")
        self.assertEqual(subprocess.run(["bash", "-n", os.path.join(ROOT, "tools/build_offline_iso.sh")]).returncode, 0)
        self.assertIn('bash "$root/tools/build_iso.sh"', s)              # (the network installer is its base)
        self.assertNotIn("offline", read("tools/build_iso.sh"))

    def test_the_medium_is_verified_before_it_is_made_and_before_it_installs(self):
        s = read("tools/build_offline_iso.sh")
        self.assertLess(s.index('python3 "$plugin" verify "$mirror" --mirror-keys'), s.index("xorriso -indev \"$net\" -outdev"))
        self.assertIn("%pre --erroronfail", s)
        self.assertIn("python3 /run/install/repo/silik-mirror.py verify /run/install/repo/mirror --mirror-keys", s)
        self.assertIn('-map "$plugin" /silik-mirror.py', s)

    def test_its_kickstart_names_only_the_medium_and_never_a_disk(self):
        s = read("tools/build_offline_iso.sh")
        code = s.split("<<'EOF'\n", 1)[1].split("\nEOF\n", 1)[0]
        with tempfile.TemporaryDirectory() as t:
            repos = {n: {} for n in ("BaseOS", "AppStream", "CRB", "epel", "silikos")}      # (no `extras`: nothing of the set is there)
            _, specs, _ = mirror.kickstart(read("kickstart/silikos.ks"))
            files = {"x/Packages/%s.rpm" % p: {"name": p} for p in specs if not p.startswith("@")}
            with open(os.path.join(t, "m.json"), "w") as f:
                json.dump({"repos": repos, "files": files}, f)
            r = subprocess.run([sys.executable, "-", os.path.join(ROOT, "kickstart/silikos.ks"), os.path.join(t, "m.json"), os.path.join(t, "out.ks")],
                               input=code, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            ks = open(os.path.join(t, "out.ks")).read()
            # a package of the kickstart that the mirror lacks stops the build
            del files["x/Packages/silik-dev.rpm"]
            with open(os.path.join(t, "m.json"), "w") as f:
                json.dump({"repos": repos, "files": files}, f)
            r = subprocess.run([sys.executable, "-", os.path.join(ROOT, "kickstart/silikos.ks"), os.path.join(t, "m.json"), os.path.join(t, "out2.ks")],
                               input=code, capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("silik-dev", r.stderr)
        live = "\n".join(l for l in ks.splitlines() if not l.lstrip().startswith("#"))
        self.assertIn("url --url=file:///run/install/repo/mirror/BaseOS\n", live)
        for n in ("AppStream", "CRB", "epel", "silikos"):
            self.assertIn("repo --name=%s --baseurl=file:///run/install/repo/mirror/%s\n" % (n, n), live)
        self.assertNotIn("--name=extras", live)
        self.assertNotRegex(live, r"https?://")
        self.assertNotRegex(live, r"(?m)^network ")
        self.assertEqual(re.findall(r"(?m)^(clearpart|zerombr|ignoredisk|autopart|part |partition |logvol|volgroup|raid|reqpart|rootpw|user )", live), [])
        # the rest is the shipped kickstart's: the same packages, the same security lines
        _, shipped, _ = mirror.kickstart(read("kickstart/silikos.ks"))
        self.assertEqual(mirror.kickstart(ks)[1], shipped)
        for line in ("selinux --enforcing", "firewall --enabled --remove-service=ssh", "services --enabled=NetworkManager,gdm"):
            self.assertIn(line, live)
        self.assertLess(live.index("%pre --erroronfail"), live.index("silik-mirror.py verify"))

    def test_the_workflow_is_started_by_hand_and_its_machine_has_no_network_device(self):
        w = read(".github/workflows/offline.yml")
        head = w.split("\njobs:\n")[0] + "\n"
        self.assertIn("\non:\n  workflow_dispatch:\n", head)
        for trigger in ("push:", "pull_request", "schedule:", "workflow_run:"):
            self.assertNotIn(trigger, head)
        self.assertIn("\npermissions:\n  contents: read\n", head)
        self.assertNotIn(": write", w)
        self.assertIn("runs-on: ubuntu-24.04", w)
        self.assertIn("bash tools/build_offline_iso.sh build/mirror", w)
        self.assertIn("bash tests/install/offline.sh build/SilikOS-*-offline.iso", w)
        o = read("tests/install/offline.sh")
        self.assertEqual(subprocess.run(["bash", "-n", os.path.join(ROOT, "tests/install/offline.sh")]).returncode, 0)
        self.assertIn('bash "$here/run.sh" "$@"', o)                  # (the CI's own installation test, as it is)
        self.assertIn("args+=(none)", o)
        self.assertIn("-nic user", read("tests/install/run.sh"))        # (what the wrapper replaces is still what run.sh says)

    def test_the_wrapper_takes_the_network_device_away(self):
        o = read("tests/install/offline.sh")
        shim = o.split("<<SHIM\n", 1)[1].split("\nSHIM\n", 1)[0].replace("\\$", "$")
        with tempfile.TemporaryDirectory() as t:
            fake = os.path.join(t, "real")
            with open(fake, "w") as f:
                f.write("#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
            os.chmod(fake, 0o755)
            path = os.path.join(t, "shim")
            with open(path, "w") as f:
                f.write(shim.replace('"$real"', '"%s"' % fake))
            r = subprocess.run(["bash", path, "-m", "4096", "-nic", "user,model=virtio-net-pci", "-cdrom", "x.iso"], capture_output=True, text=True)
        self.assertEqual(r.stdout.split(), ["-m", "4096", "-nic", "none", "-cdrom", "x.iso"])


class RecordedRun(unittest.TestCase):
    """the real run (almalinux:9 containers, 13/11/2026): what docs/OFFLINE.md and docs/STATUS.md quote is in its log"""
    LOG = os.path.join(ROOT, "tests/offline/run-2026-11-13.log")

    def test_the_log_shows_each_step_s_verdict(self):
        with open(self.LOG) as f:
            log = f.read()
        for line in (
            "network devices: lo",                                                    # (--network none)
            "curl to repo.almalinux.org: exit 6",                                     # (the internal network has no route out)
            "everything is as the manifest and the keys say",
            "sha256sum -c: every repository file of before is as it was",
            "silik mirror verify: exit 1",
            "silik mirror use: exit 3",
            "silik mirror create: exit 3",
        ):
            self.assertIn(line, log, line)
        self.assertRegex(log, r"generation 1: 1572 packages added")
        self.assertRegex(log, r"(?m)^dnf exit 0, \d+ s$")
        self.assertRegex(log, r"dnf install \S+: exit 1")
        self.assertRegex(log, r"=== done: ")
        self.assertNotRegex(log, r"(?i)https?_proxy|ca-bundle|127\.0\.0\.1:\d{5}|/home/")     # (nothing of the build machine's own)


if __name__ == "__main__":
    unittest.main()
