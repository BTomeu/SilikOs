# silik-plugin: sbom
# help: the software bill of materials of this system, from the rpm database: SPDX 2.3 or CycloneDX 1.6 (JSON); diff of two
# words: export diff
"""silik sbom export [--format spdx|cyclonedx] [-o FILE] [--stamp]     every installed package, as rpm records it
silik sbom diff A B [--json]                                         added / removed / changed versions between two bills

What a bill holds for each package: name, epoch, version, release, architecture, the licence as rpm has it (the base's
packages state theirs in Fedora's older notation, which is not an SPDX expression: it is carried as text, not
translated), the vendor rpm names as its supplier, the source rpm it was built from, the upstream URL, the sha256 of
the package header and of its payload as rpm recorded them at build time (NOT the sha256 of an .rpm file: no .rpm file
is on the system any more), the key that signed it, and a package URL (purl, type rpm: the namespace is the vendor,
the version is version-release, qualifiers arch / distro / epoch). SilikOS's own packages are marked (origin silikos).

The bill is a function of the rpm database alone: the same packages give the same bytes (sorted, no time of the
run in it). SPDX must carry a creation time: it is the time of the last package change, since when the bill is true;
--stamp writes the time of the run instead (and CycloneDX then gets its timestamp).

What it does not hold: software rpm did not install (the vendors' tools in /opt, pip, containers, Wine prefixes,
firmware), the files of each package, a dependency graph. docs/COMPLIANCE.md"""
import json
import os
import sys

# one line per package; rpm writes (none) for a tag the package does not have
TAGS = ("NAME", "EPOCH", "VERSION", "RELEASE", "ARCH", "LICENSE", "VENDOR", "SOURCERPM", "SHA256HEADER", "PAYLOADDIGEST",
        "PAYLOADDIGESTALGO", "RSAHEADER:pgpsig", "DSAHEADER:pgpsig", "URL", "INSTALLTIME", "SUMMARY")
QUERY = ["rpm", "-qa", "--qf", "\\t".join("%{" + t + "}" for t in TAGS) + "\\n"]
# the source packages SilikOS builds (the Name of every recipe in packages/, eda/, dev/, wine/: a test holds this list
# to the repository) and SilikStudio (SilikVolt's own product, built in its repository). A package is SilikOS's own
# when it was built from one of these AND rpm names no other vendor for it (ngspice from EPEL would be EPEL's).
OWN = frozenset("""devsim dfu-util kicad kicad-footprints kicad-packages3d kicad-symbols kicad-templates klayout magic netgen
ngspice nng nvc opencascade openocd qucs-s savvycan sdcc sigrok sigrok-firmware-fx2lafw silik-command silik-dev
silik-eda-compat silik-eda-open silik-pylab silik-tools silik-win silik-wine silik-wine-addons silikos-branding
silikos-desktop silikos-power silikos-security stm32flash xschem yosys silikstudio""".split())
OWN_VENDORS = ("", "SilikVolt")
OWN_SUPPLIER = "SilikVolt"
# rpm's Vendor -> the purl namespace ("the vendor such as Fedora or OpenSUSE ... lowercased": purl-spec, rpm type)
NAMESPACE = {"AlmaLinux": "almalinux", "Fedora Project": "fedora", "Red Hat, Inc.": "redhat", "CentOS": "centos",
             "Rocky Enterprise Software Foundation": "rocky"}
ORIGIN = {"almalinux": "base", "fedora": "epel"}       # the words of the "origin" mark
SPDX_NS = "https://spdx.org/spdxdocs/"                 # (the namespace SPDX's own tools use for a document without a home)
UUID_NS = "6ba7b811-9dad-11d1-80b4-00c04fd430c8"       # RFC 4122's namespace for URLs: the ids below are uuid5 of the content


def run_ro(ctx, argv, timeout=120):
    """a read-only command: printed like every command of silik (to stderr, so that a bill or a report written to the
    standard output stays one), run under --dry-run too; (exit code or None, stdout) as silik's sec_cmd"""
    import shlex
    if not ctx.quiet:
        print("$ " + " ".join(shlex.quote(a.replace("\t", "\\t").replace("\n", "\\n")) for a in argv), file=sys.stderr, flush=True)
    return SILIK.sec_cmd(argv, timeout=timeout)


def none(v):
    return "" if v in ("(none)", None) else v.strip()


def parse_packages(text):
    """[{name, epoch, version, release, arch, license, vendor, source, sha256header, payload, key, url, installtime,
    summary}] from QUERY's lines, sorted; rpm's own records of the keys it trusts (gpg-pubkey) are not software"""
    out = []
    for l in text.splitlines():
        f = l.split("\t")
        if len(f) < len(TAGS) or f[0] == "gpg-pubkey":
            continue
        d = dict(zip(TAGS, (none(x) for x in f[:len(TAGS) - 1] + ["\t".join(f[len(TAGS) - 1:])])))
        sig = d["RSAHEADER:pgpsig"] or d["DSAHEADER:pgpsig"]
        key = sig.rsplit("Key ID ", 1)[1].strip() if "Key ID " in sig else ""
        src = d["SOURCERPM"]
        out.append({
            "name": d["NAME"], "epoch": d["EPOCH"], "version": d["VERSION"], "release": d["RELEASE"], "arch": d["ARCH"],
            "license": d["LICENSE"], "vendor": d["VENDOR"], "sourcerpm": src,
            # NAME-VERSION-RELEASE.src.rpm: the name is what is left of the last two "-"
            "source": src.rsplit("-", 2)[0] if src.endswith(".rpm") and src.count("-") >= 2 else "",
            "sha256header": d["SHA256HEADER"], "payload": d["PAYLOADDIGEST"] if d["PAYLOADDIGESTALGO"] == "8" else "",
            "key": key, "url": d["URL"], "installtime": int(d["INSTALLTIME"]) if d["INSTALLTIME"].isdigit() else 0,
            "summary": d["SUMMARY"],
        })
    out.sort(key=lambda p: (p["name"], p["epoch"], p["version"], p["release"], p["arch"]))
    return out


def own(p):
    return p["source"] in OWN and p["vendor"] in OWN_VENDORS


def namespace(p):
    """the purl namespace: silikos for our own, the vendor's for the others; '' when rpm names no vendor"""
    if own(p):
        return "silikos"
    v = p["vendor"]
    if v in NAMESPACE:
        return NAMESPACE[v]
    slug = "".join(c if c.isalnum() else "-" for c in v.lower()).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug


def origin(p):
    """silikos | base | epel | the vendor's name as a word | unknown (no vendor in the package, and not ours)"""
    ns = namespace(p)
    return ORIGIN.get(ns, ns) or "unknown"


def supplier(p):
    return OWN_SUPPLIER if own(p) else p["vendor"]


def evr(p):
    return ("%s:" % p["epoch"] if p["epoch"] else "") + p["version"] + "-" + p["release"]


def nevra(p):
    return "%s-%s.%s" % (p["name"], evr(p), p["arch"])


def purl(p, distro):
    """pkg:rpm/NAMESPACE/NAME@VERSION-RELEASE?arch=..&distro=..&epoch=.. (qualifiers in order of their keys); '' for
    a package without a vendor: the purl of an rpm needs one, and guessing it would be saying where it came from"""
    from urllib.parse import quote
    ns = namespace(p)
    if not ns:
        return ""
    q = [("arch", p["arch"])] + ([("distro", distro)] if distro else []) + ([("epoch", p["epoch"])] if p["epoch"] else [])
    return "pkg:rpm/%s/%s@%s?%s" % (quote(ns, safe=""), quote(p["name"], safe=""), quote(p["version"] + "-" + p["release"], safe=""),
                                    "&".join("%s=%s" % (k, quote(v, safe="")) for k, v in sorted(q)))


def system(silik):
    """what the bill describes: the names os-release gives (SilikOS shows its own name; ID and VERSION_ID stay the
    base's, docs/PLAN.md) and the architecture"""
    osr = silik.os_release()
    return {"name": osr.get("NAME") or "Linux", "version": osr.get("VERSION_ID", ""), "pretty": osr.get("PRETTY_NAME", ""),
            "id": osr.get("ID", ""), "cpe": osr.get("CPE_NAME", ""), "arch": silik.host_arch(),
            "base": silik.read("/etc/redhat-release").strip(), "silik": silik.VERSION}


def distro(sy):
    return "%s-%s" % (sy["id"], sy["version"]) if sy["id"] and sy["version"] else sy["id"]


def digest(pkgs, sy):
    """sha256 over what the bill says: the ids of a document come from it, so the same system gives the same ids"""
    import hashlib
    h = hashlib.sha256()
    h.update(json.dumps([sy["name"], sy["version"], sy["arch"]] + [[nevra(p), p["sha256header"]] for p in pkgs]).encode())
    return h.hexdigest()


def doc_uuid(pkgs, sy, kind):
    import uuid
    return str(uuid.uuid5(uuid.UUID(UUID_NS), "silikos-sbom/%s/%s" % (kind, digest(pkgs, sy))))


def iso(t):
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def created(pkgs, stamp):
    """the time a bill carries: STAMP (the run's) when given, else the last package change"""
    return iso(stamp if stamp is not None else max([p["installtime"] for p in pkgs] or [0]))


def now():
    """the time of the run; SOURCE_DATE_EPOCH stands in for it (reproducible builds' convention)"""
    import time
    e = os.environ.get("SOURCE_DATE_EPOCH", "")
    return int(e) if e.isdigit() else int(time.time())


def is_url(u):
    return u.startswith(("http://", "https://", "ftp://")) and " " not in u and len(u) > 10


def spdx_id(p):
    """SPDXRef-Package-NAME-EVR-ARCH in the letters an SPDX id may have (letters, digits, . -); what had to be
    replaced gets the first hex of the header's sha256 so that two packages never share an id"""
    raw = "%s-%s-%s" % (p["name"], evr(p), p["arch"])
    ok = "".join(c if c.isalnum() and c.isascii() or c in ".-" else "-" for c in raw)
    return "SPDXRef-Package-" + ok + ("" if ok == raw else "-" + (p["sha256header"] or "0" * 8)[:8])


def licence_ref(text):
    import hashlib
    return "LicenseRef-rpm-" + hashlib.sha256(text.encode()).hexdigest()[:12]


def spdx(pkgs, sy, stamp=None):
    """the bill as an SPDX 2.3 document (JSON)"""
    dist = distro(sy)
    lic = {}
    packages, rel = [], []
    root = {
        "SPDXID": "SPDXRef-System", "name": sy["name"], "versionInfo": sy["version"], "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False, "primaryPackagePurpose": "OPERATING_SYSTEM", "licenseConcluded": "NOASSERTION",
        "licenseDeclared": "NOASSERTION", "copyrightText": "NOASSERTION",
        "comment": "%s%s, %s: the installed system this bill was read from" % (sy["pretty"] or sy["name"], " on " + sy["base"] if sy["base"] else "", sy["arch"]),
    }
    if sy["cpe"]:
        root["externalRefs"] = [{"referenceCategory": "SECURITY", "referenceType": "cpe22Type" if sy["cpe"].startswith("cpe:/") else "cpe23Type",
                                 "referenceLocator": sy["cpe"]}]
    packages.append(root)
    rel.append({"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": "SPDXRef-System"})
    for p in pkgs:
        i = spdx_id(p)
        d = {"SPDXID": i, "name": p["name"], "versionInfo": evr(p), "downloadLocation": "NOASSERTION", "filesAnalyzed": False,
             "supplier": "Organization: " + supplier(p) if supplier(p) else "NOASSERTION",
             "licenseConcluded": "NOASSERTION", "copyrightText": "NOASSERTION"}
        if p["license"]:
            lic.setdefault(licence_ref(p["license"]), p["license"])
            d["licenseDeclared"] = licence_ref(p["license"])
        else:
            d["licenseDeclared"] = "NOASSERTION"
        if p["summary"]:
            d["summary"] = p["summary"]
        if is_url(p["url"]):
            d["homepage"] = p["url"]
        if p["sourcerpm"]:
            d["sourceInfo"] = "built from the source package " + p["sourcerpm"]
        d["comment"] = "origin: " + origin(p)
        refs = []
        pu = purl(p, dist)
        if pu:
            refs.append({"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl", "referenceLocator": pu})
        refs.append({"referenceCategory": "OTHER", "referenceType": "rpm-nevra", "referenceLocator": nevra(p)})
        for k, v in (("rpm-header-sha256", p["sha256header"]), ("rpm-payload-sha256", p["payload"]), ("rpm-signing-key-id", p["key"])):
            if v:
                refs.append({"referenceCategory": "OTHER", "referenceType": k, "referenceLocator": v})
        d["externalRefs"] = refs
        packages.append(d)
        rel.append({"spdxElementId": "SPDXRef-System", "relationshipType": "CONTAINS", "relatedSpdxElement": i})
    doc = {
        "spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
        "name": "%s %s %s" % (sy["name"], sy["version"], sy["arch"]),
        "documentNamespace": SPDX_NS + "silikos-system-" + doc_uuid(pkgs, sy, "spdx"),
        "creationInfo": {
            "created": created(pkgs, stamp), "creators": ["Tool: silik-" + sy["silik"]],
            "comment": ("Read from the rpm database of the installed system (silik sbom export). "
                        + ("created: the time of the run. " if stamp is not None else "created: the time of the last package change, since when this bill is true. ")
                        + "Licences are the packages' own License tags, carried as text (hasExtractedLicensingInfos), not translated to SPDX expressions. "
                        "rpm-header-sha256 and rpm-payload-sha256 are rpm's records of the package's header and payload, not the sha256 of an .rpm file. "
                        "Not in this bill: software that rpm did not install (/opt, pip, containers, Wine prefixes, firmware)."),
        },
        "packages": packages,
        "relationships": rel,
    }
    if lic:
        doc["hasExtractedLicensingInfos"] = [{"licenseId": k, "name": "rpm License tag", "extractedText": lic[k]} for k in sorted(lic)]
    return doc


def cyclonedx(pkgs, sy, stamp=None):
    """the bill as a CycloneDX 1.6 document (JSON)"""
    dist = distro(sy)
    comps = []
    for p in pkgs:
        pu = purl(p, dist)
        c = {"type": "library", "bom-ref": pu or "rpm:" + nevra(p), "name": p["name"], "version": evr(p)}
        if supplier(p):
            c["supplier"] = {"name": supplier(p)}
        if p["summary"]:
            c["description"] = p["summary"]
        if p["license"]:
            c["licenses"] = [{"license": {"name": p["license"]}}]
        if pu:
            c["purl"] = pu
        if is_url(p["url"]):
            c["externalReferences"] = [{"type": "website", "url": p["url"]}]
        props = [("silikos:origin", origin(p)), ("silikos:rpm:nevra", nevra(p)), ("silikos:rpm:arch", p["arch"]), ("silikos:rpm:epoch", p["epoch"]),
                 ("silikos:rpm:sourcerpm", p["sourcerpm"]), ("silikos:rpm:header-sha256", p["sha256header"]),
                 ("silikos:rpm:payload-sha256", p["payload"]), ("silikos:rpm:signing-key-id", p["key"])]
        c["properties"] = [{"name": k, "value": v} for k, v in props if v]
        comps.append(c)
    meta = {
        "tools": {"components": [{"type": "application", "name": "silik", "version": sy["silik"]}]},
        "component": {"type": "operating-system", "bom-ref": "system", "name": sy["name"], "version": sy["version"],
                      "description": "%s%s, %s" % (sy["pretty"] or sy["name"], " on " + sy["base"] if sy["base"] else "", sy["arch"])},
        "properties": [{"name": "silikos:source", "value": "the rpm database of the installed system (silik sbom export)"},
                       {"name": "silikos:not-covered", "value": "software that rpm did not install: /opt, pip, containers, Wine prefixes, firmware"},
                       {"name": "silikos:hashes", "value": "header-sha256 and payload-sha256 are rpm's records of a package's header and payload, not the sha256 of an .rpm file"}],
    }
    if sy["cpe"]:
        meta["component"]["cpe"] = sy["cpe"]
    if stamp is not None:
        meta["timestamp"] = iso(stamp)
    return {"$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json", "bomFormat": "CycloneDX", "specVersion": "1.6",
            "serialNumber": "urn:uuid:" + doc_uuid(pkgs, sy, "cyclonedx"), "version": 1, "metadata": meta, "components": comps,
            "dependencies": [{"ref": "system", "dependsOn": [c["bom-ref"] for c in comps]}]}


FORMATS = {"spdx": spdx, "cyclonedx": cyclonedx}


def dumps(doc):
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def packages(ctx, silik):
    """the installed packages (one rpm call)"""
    rc, out = run_ro(ctx, QUERY)
    if rc != 0:
        silik.die("rpm gives no list of packages (rpm -qa: %s)" % ("not found" if rc is None else "exit %d" % rc), 1)
    return parse_packages(out)


def bills(ctx, silik, stamp=None):
    """{format: text} of both formats (silik evidence)"""
    pkgs, sy = packages(ctx, silik), system(silik)
    return {k: dumps(f(pkgs, sy, stamp)) for k, f in FORMATS.items()}, pkgs


def write(ctx, path, text):
    """a file this command makes: said, not written under --dry-run"""
    if not ctx.quiet:
        print("# writes %s (%d bytes)" % (path, len(text.encode())), file=sys.stderr)
    if ctx.dry:
        return
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def export(ctx, a):
    silik = SILIK
    pkgs, sy = packages(ctx, silik), system(silik)
    text = dumps(FORMATS[a.format](pkgs, sy, now() if a.stamp else None))
    if a.output and a.output != "-":
        write(ctx, a.output, text)
        if not ctx.quiet:
            n = sum(1 for p in pkgs if own(p))
            print("%s: %d packages (%d SilikOS's own, %d without a vendor), %s" % (
                a.output, len(pkgs), n, sum(1 for p in pkgs if origin(p) == "unknown"),
                {"spdx": "SPDX 2.3", "cyclonedx": "CycloneDX 1.6"}[a.format]))
    else:
        sys.stdout.write(text)
    return 0


# ---------------------------------------------------------------- diff
def purl_arch(pu):
    from urllib.parse import parse_qs
    return (parse_qs(pu.partition("?")[2]).get("arch") or [""])[0] if pu else ""


def load(path):
    """{(name, arch): [versions]} of a bill, SPDX or CycloneDX (ours, or another tool's: the architecture is then read
    from the purl, '' when the bill does not say); (kind, packages)"""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError("%s: %s" % (path, e))
    out = {}
    if isinstance(d, dict) and d.get("bomFormat") == "CycloneDX":
        kind = "CycloneDX " + str(d.get("specVersion", ""))
        for c in d.get("components") or []:
            props = {x.get("name"): x.get("value") for x in c.get("properties") or [] if isinstance(x, dict)}
            arch = props.get("silikos:rpm:arch") or purl_arch(c.get("purl", ""))
            out.setdefault((c.get("name", ""), arch), []).append(str(c.get("version", "")))
    elif isinstance(d, dict) and str(d.get("spdxVersion", "")).startswith("SPDX-"):
        kind = d["spdxVersion"]
        described = {r.get("relatedSpdxElement") for r in d.get("relationships") or [] if r.get("relationshipType") == "DESCRIBES"}
        for p in d.get("packages") or []:
            if p.get("SPDXID") in described and p.get("primaryPackagePurpose") in ("OPERATING_SYSTEM", "OPERATING-SYSTEM"):
                continue                   # (the system itself, not a package of it)
            refs = {r.get("referenceType"): r.get("referenceLocator", "") for r in p.get("externalRefs") or []}
            arch = refs.get("rpm-nevra", "").rpartition(".")[2] or purl_arch(refs.get("purl", ""))
            out.setdefault((p.get("name", ""), arch), []).append(str(p.get("versionInfo", "")))
    else:
        raise ValueError("%s: neither an SPDX nor a CycloneDX document (JSON)" % path)
    return kind, {k: sorted(v) for k, v in out.items()}


def compare(a, b):
    """{added, removed, changed} between two load()s: [[name, arch, versions]] and [[name, arch, old, new]]"""
    added = [[n, ar, b[(n, ar)]] for n, ar in sorted(b) if (n, ar) not in a]
    removed = [[n, ar, a[(n, ar)]] for n, ar in sorted(a) if (n, ar) not in b]
    changed = [[n, ar, a[(n, ar)], b[(n, ar)]] for n, ar in sorted(a) if (n, ar) in b and a[(n, ar)] != b[(n, ar)]]
    return {"added": added, "removed": removed, "changed": changed}


def diff(ctx, a):
    try:
        ka, pa = load(a.a)
        kb, pb = load(a.b)
    except ValueError as e:
        SILIK.die(str(e), 2)
    d = compare(pa, pb)
    same = not (d["added"] or d["removed"] or d["changed"])
    if a.json:
        print(json.dumps({"a": {"file": a.a, "format": ka, "packages": sum(len(v) for v in pa.values())},
                          "b": {"file": a.b, "format": kb, "packages": sum(len(v) for v in pb.values())},
                          "added": d["added"], "removed": d["removed"], "changed": d["changed"]}, indent=1))
        return 0 if same else 1
    def who(n, ar):
        return n + ("." + ar if ar else "")
    for n, ar, v in d["added"]:
        print("+ %-40s %s" % (who(n, ar), ", ".join(v)))
    for n, ar, v in d["removed"]:
        print("- %-40s %s" % (who(n, ar), ", ".join(v)))
    for n, ar, v, w in d["changed"]:
        print("~ %-40s %s -> %s" % (who(n, ar), ", ".join(v), ", ".join(w)))
    count = lambda p: sum(len(v) for v in p.values())       # (a package installed in two versions, a kernel, is two)
    print("%d added, %d removed, %d changed (%s: %d packages, %s; %s: %d packages, %s)" % (
        len(d["added"]), len(d["removed"]), len(d["changed"]), a.a, count(pa), ka, a.b, count(pb), kb))
    return 0 if same else 1


SILIK = None


def register(group, silik):
    global SILIK
    SILIK = silik
    sub = group.add_subparsers(dest="cmd")
    x = sub.add_parser("export", help="the bill of this system, to the standard output or to -o FILE")
    x.add_argument("--format", choices=sorted(FORMATS), default="spdx", help="spdx: SPDX 2.3 JSON (default); cyclonedx: CycloneDX 1.6 JSON")
    x.add_argument("-o", "--output", metavar="FILE")
    x.add_argument("--stamp", action="store_true", help="write the time of the run into the bill (without it the same system gives the same bytes)")
    x.set_defaults(fn=export)
    x = sub.add_parser("diff", help="what changed between two bills: + added, - removed, ~ another version; exit 1 when they differ")
    x.add_argument("a"); x.add_argument("b"); x.add_argument("--json", action="store_true")
    x.set_defaults(fn=diff)
