# Tests of `silik sbom` (packages/silik-tools/files/plugins/sbom.py): the bill of materials read from the rpm database.
# The rpm database is a recorded one: tests/data/compliance/rpm-qa.txt is the output of the plugin's own query in an
# almalinux:9 container (AlmaLinux 9.8, rpm 4.16.1.3, 13/11/2026) with silik-tools, silikos-security, openscap-scanner
# and scap-security-guide installed, and two kernel-core records added with `rpm -i --justdb`.
# Both formats are held to the official JSON schemas (tests/data/sbom: SPDX 2.3 from spdx/spdx-spec v2.3, CycloneDX 1.6
# from CycloneDX/specification 1.6, with their licences) by tests/schema_min.py, a validator of our own (standard
# library); the same two bills were also checked with python3-jsonschema 3.2.0 (AppStream) in the container: docs/STATUS.md.
#   python3 -m unittest discover -s tests -v
import contextlib
import copy
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import schema_min                                       # noqa: E402

DATA = os.path.join(ROOT, "tests/data/compliance")
SCHEMAS = os.path.join(ROOT, "tests/data/sbom")


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


def text(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return f.read()


silik = load("silik_sbom_cli", os.path.join(ROOT, "packages/silik-tools/files/silik"))
sbom = silik.load_plugin("sbom")
sbom.SILIK = silik
RPM_QA = text("rpm-qa.txt")
SYSTEM = {"name": "SilikOS", "version": "9.8", "pretty": "SilikOS 9.8", "id": "almalinux", "cpe": "cpe:/o:almalinux:almalinux:9::baseos",
          "arch": "x86_64", "base": "AlmaLinux release 9.8 (Olive Jaguar)", "silik": "0.0.0"}
ROW = "\t".join(["%s"] * 16)


def row(name, vendor="(none)", source=None, epoch="(none)", version="1.0", release="1.el9", arch="x86_64", licence="MIT", url="https://example.org/x"):
    return ROW % (name, epoch, version, release, arch, licence, vendor, source or "%s-%s-%s.src.rpm" % (name, version, release),
                  "ab" * 32, "cd" * 32, "8", "RSA/SHA256, Tue Apr 30 18:01:28 2024, Key ID d36cb86cb86b3716", "(none)", url, "1700000000", "a package")


def main(argv, rpm=RPM_QA):
    """silik.main with the rpm database of the recording: (exit code, stdout, stderr)"""
    def fake(cmd, timeout=20):
        return (0, rpm.strip()) if cmd[:2] == ["rpm", "-qa"] else (None, "")
    old, out, err = silik.sec_cmd, io.StringIO(), io.StringIO()
    silik.sec_cmd = fake
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                rc = silik.main(argv)
            except SystemExit as e:
                rc = e.code
    finally:
        silik.sec_cmd = old
    return rc, out.getvalue(), err.getvalue()


class Packages(unittest.TestCase):
    def setUp(self):
        self.pkgs = sbom.parse_packages(RPM_QA)

    def test_every_package_of_the_database_and_not_the_keys(self):
        lines = [l for l in RPM_QA.splitlines() if l.strip()]
        self.assertEqual(len(lines), 292)
        self.assertEqual(len(self.pkgs), 291)                      # (gpg-pubkey is a key rpm trusts, not software)
        self.assertNotIn("gpg-pubkey", [p["name"] for p in self.pkgs])
        self.assertEqual(self.pkgs, sorted(self.pkgs, key=lambda p: (p["name"], p["epoch"], p["version"], p["release"], p["arch"])))
        bash = next(p for p in self.pkgs if p["name"] == "bash")
        self.assertEqual((bash["version"], bash["release"], bash["arch"], bash["license"], bash["vendor"], bash["sourcerpm"], bash["source"], bash["key"]),
                         ("5.1.8", "9.el9", "x86_64", "GPLv3+", "AlmaLinux", "bash-5.1.8-9.el9.src.rpm", "bash", "d36cb86cb86b3716"))
        self.assertRegex(bash["sha256header"], r"^[0-9a-f]{64}$")
        self.assertRegex(bash["payload"], r"^[0-9a-f]{64}$")
        self.assertEqual(next(p for p in self.pkgs if p["name"] == "openssl-libs")["epoch"], "1")
        self.assertEqual(len([p for p in self.pkgs if p["name"] == "kernel-core"]), 2)        # (two versions of one package)

    def test_the_purl_is_the_specs(self):
        # purl-spec, type rpm: namespace = the vendor, lowercased; version = version-release; qualifiers arch, distro,
        # epoch, in the order of their keys; what is not a letter, digit or . - _ ~ is percent-encoded
        p = next(p for p in self.pkgs if p["name"] == "openssl-libs")
        self.assertEqual(sbom.purl(p, "almalinux-9.8"), "pkg:rpm/almalinux/openssl-libs@3.5.8-2.el9_8?arch=x86_64&distro=almalinux-9.8&epoch=1")
        p = next(p for p in self.pkgs if p["name"] == "bash")
        self.assertEqual(sbom.purl(p, "almalinux-9.8"), "pkg:rpm/almalinux/bash@5.1.8-9.el9?arch=x86_64&distro=almalinux-9.8")
        p = sbom.parse_packages(row("libstdc++", "AlmaLinux", version="11.5.0", release="14.el9.alma.1"))[0]
        self.assertEqual(sbom.purl(p, "almalinux-9.8"), "pkg:rpm/almalinux/libstdc%2B%2B@11.5.0-14.el9.alma.1?arch=x86_64&distro=almalinux-9.8")
        p = sbom.parse_packages(row("tio", "Fedora Project"))[0]
        self.assertTrue(sbom.purl(p, "almalinux-9.8").startswith("pkg:rpm/fedora/tio@"))

    def test_silikos_own_packages_are_marked(self):
        own = sorted(p["name"] for p in self.pkgs if sbom.own(p))
        self.assertEqual(own, ["silik-tools", "silikos-security"])
        p = next(p for p in self.pkgs if p["name"] == "silik-tools")
        self.assertEqual((sbom.origin(p), sbom.supplier(p)), ("silikos", "SilikVolt"))
        self.assertTrue(sbom.purl(p, "almalinux-9.8").startswith("pkg:rpm/silikos/silik-tools@0.6.14-1.el9?arch=noarch"))
        # a subpackage is its source package's; the same name from another vendor is that vendor's
        by = {p["name"]: p for p in sbom.parse_packages("\n".join([row("kicad-doc", source="kicad-10.0.8-1.el9.src.rpm"),
                                                                   row("ngspice", "Fedora Project"), row("bash", "AlmaLinux")]))}
        self.assertEqual([sbom.origin(by[n]) for n in ("kicad-doc", "ngspice", "bash")], ["silikos", "epel", "base"])

    def test_a_package_nobody_vouches_for_gets_no_purl(self):
        p = sbom.parse_packages(row("JLink_Linux"))[0]              # (no vendor in the package, not one of ours)
        self.assertEqual((sbom.origin(p), sbom.purl(p, "almalinux-9.8"), sbom.supplier(p)), ("unknown", "", ""))
        p = sbom.parse_packages(row("probe-tools", "Example Tools, Inc."))[0]       # (another vendor: its name as a word)
        self.assertTrue(sbom.purl(p, "almalinux-9.8").startswith("pkg:rpm/example-tools-inc/probe-tools@"))
        self.assertEqual(sbom.origin(p), "example-tools-inc")

    def test_the_list_of_our_recipes_is_the_repositorys(self):
        names = set()
        for d in ("packages", "eda", "dev", "wine"):
            for top, _, fs in os.walk(os.path.join(ROOT, d)):
                for f in fs:
                    if f.endswith(".spec"):
                        with open(os.path.join(top, f), encoding="utf-8") as fh:
                            names.add(re.search(r"(?m)^Name:\s*(\S+)", fh.read()).group(1))
        self.assertGreater(len(names), 30)
        self.assertEqual(sorted(names - sbom.OWN), [], "a recipe of the repository is missing in OWN of plugins/sbom.py")
        self.assertEqual(sorted(sbom.OWN - names), ["silikstudio"])       # (SilikVolt's product, built in its own repository)


class Formats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pkgs = sbom.parse_packages(RPM_QA)
        cls.spdx = sbom.spdx(cls.pkgs, SYSTEM)
        cls.cdx = sbom.cyclonedx(cls.pkgs, SYSTEM)

    def test_spdx_23_is_valid_by_the_official_schema(self):
        v = schema_min.Validator(os.path.join(SCHEMAS, "spdx-2.3.schema.json"))
        self.assertEqual(v.validate(json.loads(sbom.dumps(self.spdx))), [])
        self.assertEqual(self.spdx["spdxVersion"], "SPDX-2.3")
        bad = copy.deepcopy(self.spdx)                               # (the validator does say no)
        bad["packages"][3]["externalRefs"][0]["referenceCategory"] = "NOPE"
        del bad["packages"][5]["name"]
        self.assertEqual(len(v.validate(bad)), 2)

    def test_cyclonedx_16_is_valid_by_the_official_schema(self):
        v = schema_min.Validator(os.path.join(SCHEMAS, "bom-1.6.schema.json"))
        self.assertEqual(v.validate(json.loads(sbom.dumps(self.cdx))), [])
        self.assertEqual((self.cdx["bomFormat"], self.cdx["specVersion"]), ("CycloneDX", "1.6"))
        bad = copy.deepcopy(self.cdx)
        bad["components"][3]["type"] = "thing"
        bad["serialNumber"] = "x"
        bad["components"][4]["licenses"] = [{"license": {}}]
        self.assertEqual(len(v.validate(bad)), 3)

    def test_what_a_package_carries(self):
        p = next(p for p in self.spdx["packages"] if p["name"] == "openssl-libs")
        self.assertEqual((p["versionInfo"], p["supplier"], p["sourceInfo"], p["homepage"], p["comment"]),
                         ("1:3.5.8-2.el9_8", "Organization: AlmaLinux", "built from the source package openssl-3.5.8-2.el9_8.src.rpm",
                          "http://www.openssl.org/", "origin: base"))
        refs = {r["referenceType"]: r["referenceLocator"] for r in p["externalRefs"]}
        self.assertEqual(refs["purl"], "pkg:rpm/almalinux/openssl-libs@3.5.8-2.el9_8?arch=x86_64&distro=almalinux-9.8&epoch=1")
        self.assertEqual(refs["rpm-nevra"], "openssl-libs-1:3.5.8-2.el9_8.x86_64")
        self.assertRegex(refs["rpm-header-sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(refs["rpm-signing-key-id"], "d36cb86cb86b3716")
        self.assertNotIn("checksums", p)             # (rpm's header digest is not the sha256 of an .rpm file: not said as one)
        c = next(c for c in self.cdx["components"] if c["name"] == "openssl-libs")
        props = {x["name"]: x["value"] for x in c["properties"]}
        self.assertEqual((c["version"], c["purl"], c["supplier"], c["licenses"]),
                         ("1:3.5.8-2.el9_8", refs["purl"], {"name": "AlmaLinux"}, [{"license": {"name": "Apache-2.0"}}]))
        self.assertEqual((props["silikos:origin"], props["silikos:rpm:sourcerpm"], props["silikos:rpm:header-sha256"]),
                         ("base", "openssl-3.5.8-2.el9_8.src.rpm", refs["rpm-header-sha256"]))
        self.assertNotIn("hashes", c)
        own = [c["name"] for c in self.cdx["components"] if {"name": "silikos:origin", "value": "silikos"} in c["properties"]]
        self.assertEqual(own, ["silik-tools", "silikos-security"])
        self.assertEqual([p["name"] for p in self.spdx["packages"] if p.get("comment") == "origin: silikos"], own)

    def test_the_licence_is_rpms_own_text(self):
        # the base states its licences in Fedora's older notation ("GPLv3+"): not an SPDX expression, so it is carried
        # as extracted text under a LicenseRef, never rewritten
        texts = {x["licenseId"]: x["extractedText"] for x in self.spdx["hasExtractedLicensingInfos"]}
        bash = next(p for p in self.spdx["packages"] if p["name"] == "bash")
        self.assertEqual(texts[bash["licenseDeclared"]], "GPLv3+")
        self.assertEqual(bash["licenseConcluded"], "NOASSERTION")
        for p in self.spdx["packages"][1:]:
            self.assertIn(p["licenseDeclared"], texts, p["name"])

    def test_ids_are_valid_and_unique(self):
        ids = [p["SPDXID"] for p in self.spdx["packages"]]
        self.assertEqual(len(ids), len(set(ids)))
        for i in ids:
            self.assertRegex(i, r"^SPDXRef-[A-Za-z0-9.-]+$")
        refs = [c["bom-ref"] for c in self.cdx["components"]]
        self.assertEqual(len(refs), len(set(refs)))
        # the system the bill describes, and what it contains
        self.assertEqual(self.spdx["relationships"][0], {"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": "SPDXRef-System"})
        self.assertEqual(len([r for r in self.spdx["relationships"] if r["relationshipType"] == "CONTAINS"]), 291)
        self.assertEqual(self.cdx["metadata"]["component"]["type"], "operating-system")

    def test_the_same_system_gives_the_same_bytes(self):
        again = sbom.parse_packages("\n".join(reversed(RPM_QA.splitlines())))        # (whatever order rpm answers in)
        self.assertEqual(sbom.dumps(sbom.spdx(again, SYSTEM)), sbom.dumps(self.spdx))
        self.assertEqual(sbom.dumps(sbom.cyclonedx(again, SYSTEM)), sbom.dumps(self.cdx))
        # no time of the run: SPDX's required creation time is the last package change; CycloneDX has none
        last = max(p["installtime"] for p in self.pkgs)
        self.assertEqual(self.spdx["creationInfo"]["created"], sbom.iso(last))
        self.assertNotIn("timestamp", self.cdx["metadata"])
        # another system is another document
        other = sbom.spdx(self.pkgs[:-1], SYSTEM)
        self.assertNotEqual(other["documentNamespace"], self.spdx["documentNamespace"])
        self.assertRegex(self.cdx["serialNumber"], r"^urn:uuid:[0-9a-f-]{36}$")

    def test_stamp_writes_the_time_of_the_run(self):
        self.assertEqual(sbom.spdx(self.pkgs, SYSTEM, 1800000000)["creationInfo"]["created"], "2027-01-15T08:00:00Z")
        self.assertEqual(sbom.cyclonedx(self.pkgs, SYSTEM, 1800000000)["metadata"]["timestamp"], "2027-01-15T08:00:00Z")


class Commands(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.d)

    def test_export_to_the_standard_output_is_the_bill_alone(self):
        rc, out, err = main(["sbom", "export"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["spdxVersion"], "SPDX-2.3")                 # (nothing else on stdout)
        self.assertTrue(err.startswith("$ rpm -qa --qf "), err)                        # (the command it ran is said)
        rc, out2, err = main(["-q", "sbom", "export"])
        self.assertEqual((out2, err), (out, ""))
        rc, out, _ = main(["sbom", "export", "--format", "cyclonedx"])
        self.assertEqual(json.loads(out)["specVersion"], "1.6")

    def test_export_to_a_file_and_dry_run(self):
        f = os.path.join(self.d, "sub", "bom.json")
        rc, out, err = main(["--dry-run", "sbom", "export", "-o", f])
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(os.path.dirname(f)))                           # (--dry-run writes nothing)
        self.assertIn("# writes " + f, err)
        rc, out, err = main(["sbom", "export", "-o", f])
        self.assertEqual(rc, 0)
        self.assertIn("291 packages (2 SilikOS's own, 0 without a vendor), SPDX 2.3", out)
        with open(f) as fh:
            self.assertEqual(len(json.load(fh)["packages"]), 292)                      # (the system and its 291)

    def test_stamp_from_the_command(self):
        os.environ["SOURCE_DATE_EPOCH"] = "1800000000"
        try:
            rc, out, _ = main(["sbom", "export", "--stamp"])
        finally:
            del os.environ["SOURCE_DATE_EPOCH"]
        self.assertEqual(json.loads(out)["creationInfo"]["created"], "2027-01-15T08:00:00Z")

    def test_rpm_does_not_answer(self):
        old = silik.sec_cmd
        silik.sec_cmd = lambda cmd, timeout=20: (None, "")
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as e:
                silik.main(["sbom", "export"])
        finally:
            silik.sec_cmd = old
        self.assertEqual(e.exception.code, 1)
        self.assertIn("rpm gives no list of packages", err.getvalue())

    def bills(self):
        a, b, c = (os.path.join(self.d, n) for n in ("a.spdx.json", "b.cdx.json", "c.spdx.json"))
        self.assertEqual(main(["sbom", "export", "-o", a])[0], 0)
        lines = [l for l in RPM_QA.splitlines() if not l.startswith("zlib\t")]                       # removed
        lines = [l.replace("\t5.1.8\t9.el9\t", "\t5.1.8\t10.el9\t") if l.startswith("bash\t") else l for l in lines]   # another version
        lines.append(row("tio", "Fedora Project", version="3.9"))                                  # added
        later = "\n".join(lines)
        self.assertEqual(main(["sbom", "export", "--format", "cyclonedx", "-o", b], later)[0], 0)
        self.assertEqual(main(["sbom", "export", "-o", c], later)[0], 0)
        return a, b, c

    def test_diff(self):
        a, b, c = self.bills()
        rc, out, _ = main(["sbom", "diff", a, a])
        self.assertEqual((rc, out), (0, "0 added, 0 removed, 0 changed (%s: 291 packages, SPDX-2.3; %s: 291 packages, SPDX-2.3)\n" % (a, a)))
        for other in (c, b):                                # (an SPDX bill against an SPDX one, and against a CycloneDX one)
            rc, out, _ = main(["sbom", "diff", a, other])
            self.assertEqual(rc, 1)
            lines = out.splitlines()
            self.assertEqual(lines[0].split(), ["+", "tio.x86_64", "3.9-1.el9"])
            self.assertEqual(lines[1].split()[:2], ["-", "zlib.x86_64"])
            self.assertEqual(lines[2].split(), ["~", "bash.x86_64", "5.1.8-9.el9", "->", "5.1.8-10.el9"])
            self.assertTrue(lines[3].startswith("1 added, 1 removed, 1 changed ("))
        rc, out, _ = main(["sbom", "diff", "--json", a, b])
        d = json.loads(out)
        self.assertEqual((rc, d["added"], d["changed"]), (1, [["tio", "x86_64", ["3.9-1.el9"]]], [["bash", "x86_64", ["5.1.8-9.el9"], ["5.1.8-10.el9"]]]))
        self.assertEqual((d["a"]["format"], d["b"]["format"], d["b"]["packages"]), ("SPDX-2.3", "CycloneDX 1.6", 291))

    def test_diff_of_what_is_not_a_bill(self):
        f = os.path.join(self.d, "x.json")
        with open(f, "w") as fh:
            fh.write('{"hello": 1}')
        rc, _, err = main(["sbom", "diff", f, f])
        self.assertEqual(rc, 2)
        self.assertIn("neither an SPDX nor a CycloneDX document", err)
        rc, _, err = main(["sbom", "diff", f, os.path.join(self.d, "nowhere.json")])
        self.assertEqual(rc, 2)


class Validator(unittest.TestCase):
    """the validator of the tests refuses what it does not know instead of passing it"""
    def test_an_unknown_keyword_stops_the_check(self):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "s.json")
            with open(p, "w") as f:
                json.dump({"type": "object", "dependentRequired": {"a": ["b"]}}, f)
            with self.assertRaises(schema_min.Unsupported):
                schema_min.Validator(p).validate({})
            with open(p, "w") as f:
                json.dump({"type": "object", "required": ["a"], "properties": {"a": {"type": "array", "items": {"$ref": "#/definitions/n"}, "uniqueItems": True}},
                           "additionalProperties": False, "definitions": {"n": {"type": "integer", "minimum": 1}}}, f)
            v = schema_min.Validator(p)
            self.assertEqual(v.validate({"a": [1, 2]}), [])
            self.assertEqual(len(v.validate({"a": [1, 1, 0, "x"], "b": 1})), 4)
        finally:
            import shutil
            shutil.rmtree(d)

    def test_the_schemas_are_the_published_ones(self):
        import hashlib
        want = {"spdx-2.3.schema.json": "239208b7ac287b3cf5d9a9af23f9d69863971102a5e1587a27a398b43490b89b",
                "bom-1.6.schema.json": "3e92dddbc30cf7f6a02b80f0942b1a4cfd4fb1c26f1dfc4310afa9d613cafb93",
                "spdx.schema.json": "baa9d3bd1ed57b6751b0887edead6b5063ff53ff7429cf85d476c6c94af0166e"}
        for n, h in want.items():
            with open(os.path.join(SCHEMAS, n), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), h, n)
        for n in ("LICENSE.spdx-spec", "LICENSE.cyclonedx", "README"):
            self.assertTrue(os.path.isfile(os.path.join(SCHEMAS, n)), n)


if __name__ == "__main__":
    unittest.main()
