# Tests of the supply chain and of the corresponding source: every source a build downloads is pinned (an archive by
# its sha256, a git tree by its commit) and checked by the build scripts; every build makes its source package and the
# workflows keep it beside the binary; a replaced package moves to the release sources-archive (tools/release_keep.sh,
# run here against a stand-in of gh); the licence metadata of the upstream packages.
#   python3 -m unittest discover -s tests -v
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def text(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def lines(rel):
    return [l.split() for l in text(rel).splitlines() if l.strip() and not l.startswith("#")]


def specs(d):
    return sorted(f for f in os.listdir(os.path.join(ROOT, d)) if f.endswith(".spec"))


class Pinned(unittest.TestCase):
    def test_every_eda_source_is_pinned(self):
        for w in lines("eda/versions"):
            name, url, tag = w[:3]
            self.assertNotIn("latest:", tag, name)                       # (a tag found at build time cannot be pinned)
            if len(w) == 4:                                               # a git tree at its commit
                self.assertRegex(w[3], HEX40, name)
                self.assertTrue(url.startswith("https://"), name)
            else:                                                         # a release archive and its sha256
                self.assertEqual(len(w), 5, name)
                self.assertTrue(w[3].startswith("https://"), name)
                self.assertRegex(w[4], HEX64, name)

    def test_every_dev_source_is_pinned(self):
        for w in lines("dev/versions"):
            name, url = w[:2]
            if url == "multi":                                            # the recipe's "# source: URL COMMIT" lines
                src = [l.split() for l in text("dev/%s.spec" % name).splitlines() if l.startswith("# source: ")]
                self.assertTrue(src, name)
                for s in src:
                    self.assertEqual(len(s), 4, s)
                    self.assertRegex(s[3], HEX40, s)
            elif url == "pypi":                                           # (tests/test_dev.py: every line hashed)
                self.assertEqual(len(w), 3, name)
            elif len(w) == 4:
                self.assertRegex(w[3], HEX40, name)
            else:
                self.assertEqual(len(w), 5, name)
                self.assertRegex(w[4], HEX64, name)

    def test_the_build_scripts_check_what_they_fetch(self):
        for script in ("tools/build_eda.sh", "tools/build_dev.sh"):
            s = text(script)
            self.assertIn("sha256sum -c --quiet", s, script)
            self.assertIn("rev-parse HEAD)", s, script)
            self.assertIn("not at the pinned commit", s, script)
        self.assertNotIn("latest:", text("tools/build_eda.sh"))
        self.assertIn("SILIK_EDA_PIN", text("tools/build_eda.sh"))      # another tag: never unpinned
        b = text("tools/bench_ngspice_flags.sh")
        self.assertIn("sha256sum -c --quiet", b)
        self.assertNotIn("ls-remote", b)

    def test_wine_and_its_addons_are_pinned(self):
        rows = {w[0]: w for w in lines("wine/sources")}
        for name, w in rows.items():
            self.assertEqual(len(w), 3, name)
            self.assertRegex(w[1], HEX64, name)
            self.assertTrue(w[2].startswith("https://") and w[2].endswith(name.replace("wine-mono-10.4.1-COPYING", "COPYING")), name)
        ver = re.search(r"wine_version:([0-9.]+)\}", text("wine/silik-wine.spec")).group(1)
        addons = text("wine/silik-wine-addons.spec")
        mono = re.search(r"mono_ver:([0-9.]+)\}", addons).group(1)
        gecko = re.search(r"gecko_ver:([0-9.]+)\}", addons).group(1)
        for f in ("wine-%s.tar.xz" % ver, "wine-mono-%s-x86.tar.xz" % mono, "wine-mono-%s-src.tar.xz" % mono,
                  "wine-mono-%s-COPYING" % mono, "wine-gecko-%s-x86.tar.xz" % gecko,
                  "wine-gecko-%s-x86_64.tar.xz" % gecko, "wine-gecko-%s-src.tar.xz" % gecko):
            self.assertIn(f, rows)
        w = text("tools/build_wine.sh")
        fpr = re.search(r"^WINE_KEY_FPR=([0-9A-F]{40})$", w, re.M).group(1)
        self.assertIn('VALIDSIG .* $WINE_KEY_FPR', w)
        self.assertIn("sha256sum -c --quiet", w)
        self.assertEqual(fpr, "DA23579A74D4AD9AF9D3F945CEFAC8EAAF17519D")
        a = text("tools/build_wine_addons.sh")
        self.assertIn("sha256sum -c --quiet", a)
        self.assertIn("wine/sources", a)

    def test_the_base_iso_is_checked_against_almalinux_signed_checksums(self):
        s = text("tools/build_iso.sh")
        fpr = re.search(r"^ALMA_KEY_FPR=([0-9A-F]{40})$", s, re.M).group(1)
        self.assertIn('VALIDSIG .* $ALMA_KEY_FPR', s)
        self.assertIn('--output "$g/signed"', s)                       # only the signed text is read
        self.assertIn("sha256sum -c --quiet", s)
        # checked before the ISO is read for anything else
        self.assertLess(s.index("sha256sum -c --quiet"), s.index("-pvd_info"))
        f = text("tools/fetch_base_sources.sh")
        self.assertIn("ALMA_KEY_FPR=" + fpr, f)
        self.assertIn("rpmkeys", f)


class SourcePackages(unittest.TestCase):
    def test_every_build_makes_its_source_package(self):
        for script in ("tools/build_eda.sh", "tools/build_dev.sh", "tools/build_wine.sh", "tools/build_wine_addons.sh",
                       "tools/build_rpms.sh"):
            s = text(script)
            self.assertIn("rpmbuild -bs", s.replace('"$what"', "-bs"), script)
            self.assertIn("build/srpm", s, script)
        for script in ("tools/build_eda.sh", "tools/build_dev.sh"):
            s = text(script)
            self.assertLess(s.index("rpmbuild -bs"), s.index("rpmbuild -bb"), script)   # (a %prep may remove its source)
            self.assertIn("Source100:      common.inc", s, script)        # the source package carries common.inc
            self.assertIn('echo "%global upver $ver"', s, script)          # and rebuilds without a --define

    def test_the_source_packages_never_reach_the_iso(self):
        for script in ("tools/build_eda.sh", "tools/build_dev.sh", "tools/build_wine.sh", "tools/build_wine_addons.sh"):
            self.assertNotRegex(text(script), r"src\.rpm[^\n]*build/extra", script)
        self.assertIn("rm -f build/extra/*.src.rpm", text(".github/workflows/ci.yml"))
        self.assertIn("grep -v '\\.src\\.rpm$'", text("tools/build_eda.sh"))  # (a dependency is never a source package)
        self.assertIn("rm -f deps/*.src.rpm", text("eda/keep.sh"))

    def test_the_workflows_keep_sources_and_delete_nothing(self):
        for wf in ("eda", "dev", "wine"):
            s = text(".github/workflows/%s.yml" % wf)
            self.assertIn("srpm-", s, wf)
            self.assertIn(".src.rpm", s, wf)
            self.assertNotIn("delete-asset", s, wf)
        self.assertIn("tools/release_keep.sh", text(".github/workflows/dev.yml"))
        self.assertIn("tools/release_keep.sh", text(".github/workflows/wine.yml"))
        self.assertIn("tools/release_keep.sh", text("eda/keep.sh"))
        self.assertNotIn("delete-asset", text("eda/keep.sh"))
        ci = text(".github/workflows/ci.yml")
        self.assertIn("name: silikos-sources", ci)
        self.assertIn("build/srpm/*.src.rpm", ci)


FAKE_GH = r'''#!/usr/bin/env python3
# a stand-in of `gh release ...`: each release a folder of $FAKE_GH_DIR, its assets the files in it
import fnmatch, os, shutil, sys
a = sys.argv[1:]
top = os.environ["FAKE_GH_DIR"]
def opt(name):
    return a[a.index(name) + 1] if name in a else None
assert a[0] == "release", a
cmd, rel = a[1], a[2]
d = os.path.join(top, rel)
if cmd == "view":
    if not os.path.isdir(d):
        sys.exit("release not found")
    if opt("--json") == "assets":
        print("\n".join(sorted(os.listdir(d))))
elif cmd == "create":
    os.makedirs(d)
elif cmd == "upload":
    files = [x for x in a[3:] if os.path.isfile(x)]
    for f in files:
        dst = os.path.join(d, os.path.basename(f))
        if os.path.exists(dst) and "--clobber" not in a:
            sys.exit("asset under the same name already exists: " + os.path.basename(f))
        shutil.copy(f, dst)
elif cmd == "download":
    for n in os.listdir(d):
        if fnmatch.fnmatch(n, opt("--pattern")):
            shutil.copy(os.path.join(d, n), os.path.join(opt("--dir"), n))
elif cmd == "delete-asset":
    os.unlink(os.path.join(d, a[3]))
else:
    sys.exit("not in the stand-in: " + cmd)
'''


class ReleaseKeep(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        bin_ = os.path.join(self.d, "bin")
        os.makedirs(bin_)
        with open(os.path.join(bin_, "gh"), "w") as f:
            f.write(FAKE_GH)
        os.chmod(os.path.join(bin_, "gh"), 0o755)
        self.gh = os.path.join(self.d, "gh")
        os.makedirs(os.path.join(self.gh, "tools"))
        self.env = dict(os.environ, PATH=bin_ + os.pathsep + os.environ["PATH"], FAKE_GH_DIR=self.gh,
                        GITHUB_REPOSITORY="o/r")

    def file(self, name, body):
        p = os.path.join(self.d, "f", body, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(body)
        return p

    def keep(self, *files):
        r = subprocess.run(["bash", os.path.join(ROOT, "tools/release_keep.sh"), "tools"] + list(files),
                           env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        return r.stdout

    def rel(self, name):
        p = os.path.join(self.gh, name)
        return sorted(os.listdir(p)) if os.path.isdir(p) else None

    def read(self, rel, name):
        with open(os.path.join(self.gh, rel, name)) as f:
            return f.read()

    def test_a_replaced_package_moves_to_the_archive_with_its_source(self):
        self.keep(self.file("a-1.0-1.el9.x86_64.rpm", "b1"), self.file("a-1.0-1.el9.src.rpm", "s1"),
                  self.file("a-devel-1.0-1.el9.x86_64.rpm", "d1"))
        self.assertEqual(self.rel("tools"), ["a-1.0-1.el9.src.rpm", "a-1.0-1.el9.x86_64.rpm", "a-devel-1.0-1.el9.x86_64.rpm"])
        self.assertEqual(self.rel("sources-archive"), [])
        # a new version of a (not of a-devel): the old binary and its source go to the archive, a-devel stays
        self.keep(self.file("a-1.1-1.el9.x86_64.rpm", "b2"), self.file("a-1.1-1.el9.src.rpm", "s2"))
        self.assertEqual(self.rel("tools"), ["a-1.1-1.el9.src.rpm", "a-1.1-1.el9.x86_64.rpm", "a-devel-1.0-1.el9.x86_64.rpm"])
        self.assertEqual(self.rel("sources-archive"), ["a-1.0-1.el9.src.rpm", "a-1.0-1.el9.x86_64.rpm"])
        self.assertEqual(self.read("sources-archive", "a-1.0-1.el9.src.rpm"), "s1")

    def test_a_rebuild_under_the_same_name_keeps_the_old_one(self):
        self.keep(self.file("a-1.0-1.el9.x86_64.rpm", "b1"), self.file("a-1.0-1.el9.src.rpm", "s1"))
        out = self.keep(self.file("a-1.0-1.el9.x86_64.rpm", "b1"))         # the same file: nothing moves
        self.assertIn("same: tools/a-1.0-1.el9.x86_64.rpm", out)
        self.assertEqual(self.rel("sources-archive"), [])
        self.keep(self.file("a-1.0-1.el9.x86_64.rpm", "b1-rebuilt"), self.file("a-1.0-1.el9.src.rpm", "s1-rebuilt"))
        self.assertEqual(self.read("tools", "a-1.0-1.el9.x86_64.rpm"), "b1-rebuilt")
        arch = self.rel("sources-archive")
        self.assertEqual(len(arch), 2)
        for n in arch:
            self.assertRegex(n, r"^[0-9]{8}-a-1\.0-1\.el9\.(x86_64|src)\.rpm$")
        self.assertEqual(sorted(self.read("sources-archive", n) for n in arch), ["b1", "s1"])

    def test_the_arm_build_stays_beside_the_x86_64_one(self):
        self.keep(self.file("a-1.0-1.el9.x86_64.rpm", "x1"), self.file("a-1.0-1.el9.src.rpm", "s1"))
        self.keep(self.file("a-1.0-1.el9.aarch64.rpm", "r1"))
        self.assertEqual(self.rel("tools"), ["a-1.0-1.el9.aarch64.rpm", "a-1.0-1.el9.src.rpm", "a-1.0-1.el9.x86_64.rpm"])
        self.assertEqual(self.rel("sources-archive"), [])
        # a newer aarch64 build replaces the aarch64 one only
        self.keep(self.file("a-1.1-1.el9.aarch64.rpm", "r2"))
        self.assertEqual(self.rel("tools"), ["a-1.0-1.el9.src.rpm", "a-1.0-1.el9.x86_64.rpm", "a-1.1-1.el9.aarch64.rpm"])
        self.assertEqual(self.rel("sources-archive"), ["a-1.0-1.el9.aarch64.rpm"])
        for wf in ("dev", "eda"):                                  # (the ARM jobs keep through the same script)
            self.assertGreaterEqual(text(".github/workflows/%s.yml" % wf).count("srpm-%sarm-" % wf), 2, wf)

    def test_a_name_that_starts_like_another_is_another_package(self):
        self.keep(self.file("kicad-10.0.8-1.el9.x86_64.rpm", "k"), self.file("kicad-symbols-10.0.8-1.el9.noarch.rpm", "s"))
        self.keep(self.file("kicad-10.0.9-1.el9.x86_64.rpm", "k2"))
        self.assertEqual(self.rel("tools"), ["kicad-10.0.9-1.el9.x86_64.rpm", "kicad-symbols-10.0.8-1.el9.noarch.rpm"])
        self.assertEqual(self.rel("sources-archive"), ["kicad-10.0.8-1.el9.x86_64.rpm"])


class Licences(unittest.TestCase):
    def test_no_upstream_package_says_licenseref_upstream(self):
        for d in ("eda", "dev", "wine"):
            for f in specs(d):
                s = text("%s/%s" % (d, f))
                self.assertNotIn("LicenseRef-Upstream", s, f)
                self.assertNotIn("LicenseRef-see-subpackages", s, f)
                for lic in re.findall(r"(?m)^License: +(.+)$", s):
                    for tok in re.findall(r"[^\s()]+", lic):
                        if tok in ("AND", "OR", "WITH"):
                            continue
                        self.assertRegex(tok, r"^(LicenseRef-[A-Za-z0-9.-]+|[A-Za-z0-9][A-Za-z0-9.+-]*)$", (f, tok))
        self.assertIn("License:        HPND-UC-export-US AND", text("eda/magic.spec"))
        self.assertIn("License:        GPL-1.0-or-later\n", text("eda/netgen.spec"))
        self.assertIn("MPL-2.0", text("eda/ngspice.spec").split("\nLicense:")[1].split("\n")[0])
        self.assertIn("MIT-Modern-Variant", text("eda/yosys.spec").split("\nLicense:")[1].split("\n")[0])

    def test_the_licences_macro_finds_every_licence_file_or_stops(self):
        inc = text("eda/common.inc")
        m = [l for l in inc.splitlines() if l.startswith("%define licences()")][0]
        for pat in ("[Ll][Ii][Cc][Ee][Nn][CcSs][Ee]*", "[Cc][Oo][Pp][Yy][Ii][Nn][Gg]*", "[Cc][Oo][Pp][Yy][Rr][Ii][Gg][Hh][Tt]*", "%*"):
            self.assertIn(pat, m)
        self.assertIn("exit 1", m)
        for d in ("eda", "dev"):
            for f in specs(d):
                s = text("%s/%s" % (d, f))
                self.assertTrue("%licences" in s or "%{_datadir}/licenses/%{name}" in s, f)
        self.assertIn("%licences gpl-2.0.txt", text("dev/stm32flash.spec"))

    def test_each_part_brings_its_licence(self):
        sig = text("dev/sigrok.spec")
        for part in ("libsigrok-", "libsigrokdecode-", "sigrok-cli-", "pulseview-"):
            self.assertRegex(sig, r"for p in [^;]*%s[0-9a-f]{40}" % part)
        self.assertIn("COPYING.${p%%-*}", sig)
        addons = text("wine/silik-wine-addons.spec")
        for sub in ("silik-wine-mono", "silik-wine-gecko"):
            files = addons.split("%%files -n %s\n" % sub)[1].split("\n\n")[0]
            self.assertIn("%license", files, sub)
        py = text("dev/silik-pylab.spec")
        self.assertIn('sys.exit("error: no licence file for "', py)
        self.assertIn("--no-index --find-links dl", py)
        font = os.path.join(ROOT, "installer/product/usr/share/fonts/silikos")
        self.assertIn("CascadiaMono.ttf", os.listdir(font))
        ofl = text("installer/product/usr/share/fonts/silikos/CascadiaMono-LICENSE.txt")
        self.assertIn("SIL OPEN FONT LICENSE Version 1.1", ofl)
        self.assertIn("Microsoft Corporation", ofl)


if __name__ == "__main__":
    unittest.main()
