# silik-plugin: evidence
# help: one dated folder (and its tar.gz) of what this system is: both SBOMs, the CVE report, the audit, status, repositories and keys, a MANIFEST
# words: -o --with-host --no-audit --profile --offline
"""silik evidence [-o DIR] [--with-host] [--no-audit] [--profile NAME] [--offline]

Writes DIR/silikos-evidence-YYYYMMDD/ (DIR: the current folder) and DIR/silikos-evidence-YYYYMMDD.tar.gz:
    sbom.spdx.json  sbom.cdx.json      silik sbom export, both formats
    cve.json  cve.txt                  silik cve
    audit/report.html  audit/testresult.xml  audit/summary.json     silik audit (when the scanner is installed)
    status.json  secure-status.json  doctor.json                    silik status / secure status / doctor, --json
    repositories.json                  the enabled repositories, their keys' fingerprints, the keys rpm trusts
    kernel-cmdline.txt  secure-boot.txt
    evidence.json                      what was run, what was left out and why
    README.txt                         what each file is and what it does not prove (EN, CA, ES)
    MANIFEST                           sha256 of every file above (sha256sum -c MANIFEST)

Nothing personal goes in unless --with-host: the user's name and home folder, the host name, MAC and IP addresses of
the audit's target and the disk identifiers of the kernel command line are replaced (<user>, ~, <host>, <mac>,
<address>, <uuid>), and the audit's ARF document (it holds what the checks read: accounts, mounts) is left out.
--with-host keeps all of it, and adds audit/results.xml and audit/arf.xml as the scanner wrote them.

The same system on the same day gives the same sbom.*, repositories.json, kernel-cmdline.txt, secure-boot.txt and
status.json, byte for byte; the other files carry times (the scan's, "last run 5 h ago") and say so in evidence.json.
The archive is made the same way every time (sorted, owner 0, the day's date): the same files give the same archive.
SilikOS makes no statement of compliance: this is what the tools saw, for the person who has to make one.
docs/COMPLIANCE.md"""
import json
import os
import sys

NAME = "silikos-evidence-"
FORMAT = 1
SILIK = None
XCCDF_NS = "http://checklists.nist.gov/xccdf/1.2"
# file, the same bytes for the same system on the same day, what it is (en, ca, es)
FILES = (
    ("sbom.spdx.json", True, "software bill of materials, SPDX 2.3 (silik sbom export)",
     "llista de materials de programari, SPDX 2.3 (silik sbom export)", "lista de materiales de software, SPDX 2.3 (silik sbom export)"),
    ("sbom.cdx.json", True, "software bill of materials, CycloneDX 1.6 (silik sbom export --format cyclonedx)",
     "llista de materials de programari, CycloneDX 1.6 (silik sbom export --format cyclonedx)",
     "lista de materiales de software, CycloneDX 1.6 (silik sbom export --format cyclonedx)"),
    ("cve.json", False, "pending security advisories and their CVEs, the running kernel, the automatic updates (silik cve --json)",
     "avisos de seguretat pendents i els seus CVE, el kernel en marxa, les actualitzacions automàtiques (silik cve --json)",
     "avisos de seguridad pendientes y sus CVE, el kernel en marcha, las actualizaciones automáticas (silik cve --json)"),
    ("cve.txt", False, "the same for a person (silik cve)", "el mateix per a una persona (silik cve)", "lo mismo para una persona (silik cve)"),
    ("audit/report.html", False, "OpenSCAP's report of the profile's evaluation (silik audit)",
     "informe d'OpenSCAP de l'avaluació del perfil (silik audit)", "informe de OpenSCAP de la evaluación del perfil (silik audit)"),
    ("audit/testresult.xml", False, "the XCCDF TestResult of that evaluation: every rule's result",
     "el TestResult XCCDF d'aquesta avaluació: el resultat de cada regla", "el TestResult XCCDF de esa evaluación: el resultado de cada regla"),
    ("audit/summary.json", False, "its counts and its failed rules", "els recomptes i les regles que han fallat", "los recuentos y las reglas que han fallado"),
    ("audit/results.xml", False, "XCCDF results as the scanner wrote them (--with-host)",
     "resultats XCCDF tal com els ha escrit l'escàner (--with-host)", "resultados XCCDF tal como los ha escrito el escáner (--with-host)"),
    ("audit/arf.xml", False, "Asset Reporting Format document as the scanner wrote it (--with-host)",
     "document Asset Reporting Format tal com l'ha escrit l'escàner (--with-host)", "documento Asset Reporting Format tal como lo ha escrito el escáner (--with-host)"),
    ("status.json", True, "silik status --json", "silik status --json", "silik status --json"),
    ("secure-status.json", False, "silik secure status --json: the security settings, judged",
     "silik secure status --json: la configuració de seguretat, jutjada", "silik secure status --json: la configuración de seguridad, juzgada"),
    ("doctor.json", False, "silik doctor --json: the workstation's health, judged",
     "silik doctor --json: la salut de l'estació de treball, jutjada", "silik doctor --json: la salud de la estación de trabajo, juzgada"),
    ("repositories.json", True, "the enabled package repositories, the fingerprints of their keys, the keys rpm trusts",
     "els repositoris de paquets activats, les empremtes de les seves claus, les claus en què rpm confia",
     "los repositorios de paquetes activados, las huellas de sus claves, las claves en las que rpm confía"),
    ("kernel-cmdline.txt", True, "the running kernel's command line (/proc/cmdline)",
     "la línia d'ordres del kernel en marxa (/proc/cmdline)", "la línea de órdenes del kernel en marcha (/proc/cmdline)"),
    ("secure-boot.txt", True, "Secure Boot: enabled, disabled, bios (not started through UEFI) or unknown",
     "Secure Boot: enabled, disabled, bios (no arrencat per UEFI) o unknown", "Secure Boot: enabled, disabled, bios (no arrancado por UEFI) o unknown"),
)
LANGS = ("en", "ca", "es")
OWN_FILES = (       # the two the folder always has, about itself
    ("evidence.json", "what was run, what was left out and why", "què s'ha executat, què s'ha deixat fora i per què",
     "qué se ha ejecutado, qué se ha dejado fuera y por qué"),
    ("MANIFEST", "sha256 of each file: sha256sum -c MANIFEST", "sha256 de cada fitxer: sha256sum -c MANIFEST",
     "sha256 de cada fichero: sha256sum -c MANIFEST"),
)
README = {
    "en": """SilikOS evidence folder, %(date)s (silik %(silik)s)

What a set of tools saw on one system on that day. It is evidence for the person who has to state something about
that system; it is not a statement of compliance with any regulation or standard, and SilikOS makes none.

%(files)s

What it does not show:
- software that rpm did not install: the vendors' tools in /opt, pip, containers, Wine prefixes, firmware;
- flaws for which the repositories publish no advisory (SilikOS's own packages; flaws without a fixed package yet);
- that an audit rule which passed keeps passing, or that a failed one matters for this machine;
- who uses the machine or what is done on it%(host)s.
The bill of materials is the workstation's, not that of a product built on it.
""",
    "ca": """Carpeta d'evidències de SilikOS, %(date)s (silik %(silik)s)

El que unes eines van veure en un sistema aquell dia. És evidència per a la persona que ha d'afirmar alguna cosa
sobre aquest sistema; no és cap declaració de conformitat amb cap reglament ni norma, i SilikOS no en fa cap.

%(files)s

El que no mostra:
- el programari que rpm no ha instal·lat: les eines dels fabricants a /opt, pip, contenidors, prefixos de Wine, firmware;
- les fallades per a les quals els repositoris no publiquen cap avís (els paquets propis de SilikOS; les que encara
  no tenen paquet corregit);
- que una regla de l'auditoria que ha passat continuï passant, ni que una que ha fallat importi en aquesta màquina;
- qui fa servir la màquina ni què s'hi fa%(host)s.
La llista de materials és la de l'estació de treball, no la d'un producte que s'hi construeixi.
""",
    "es": """Carpeta de evidencias de SilikOS, %(date)s (silik %(silik)s)

Lo que unas herramientas vieron en un sistema ese día. Es evidencia para la persona que tiene que afirmar algo sobre
ese sistema; no es ninguna declaración de conformidad con ningún reglamento ni norma, y SilikOS no hace ninguna.

%(files)s

Lo que no muestra:
- el software que rpm no ha instalado: las herramientas de los fabricantes en /opt, pip, contenedores, prefijos de
  Wine, firmware;
- los fallos para los que los repositorios no publican ningún aviso (los paquetes propios de SilikOS; los que aún
  no tienen paquete corregido);
- que una regla de la auditoría que ha pasado siga pasando, ni que una que ha fallado importe en esta máquina;
- quién usa la máquina ni qué se hace en ella%(host)s.
La lista de materiales es la de la estación de trabajo, no la de un producto que se construya en ella.
""",
}
HOST_NOTE = {
    "en": ("\n  (the user's name, the host name, MAC and IP addresses and disk identifiers were replaced)", "\n  (--with-host: the host's names and addresses are in it)"),
    "ca": ("\n  (el nom de l'usuari, el nom de la màquina, les adreces MAC i IP i els identificadors de disc s'han substituït)", "\n  (--with-host: hi ha els noms i les adreces de la màquina)"),
    "es": ("\n  (el nombre del usuario, el nombre de la máquina, las direcciones MAC e IP y los identificadores de disco se han sustituido)", "\n  (--with-host: contiene los nombres y las direcciones de la máquina)"),
}


def plugin(silik, name):
    key = "silik_plugin_" + name.replace("-", "_")
    m = sys.modules.get(key)
    if m is None:
        m = sys.modules[key] = silik.load_plugin(name)
    m.SILIK = silik
    return m


# ---------------------------------------------------------------- nothing personal
def identity():
    """(user names, home folders, host names) of this run: what is replaced in the folder. The tests replace it"""
    import pwd
    users, homes = set(), set()
    for u in (os.environ.get("SUDO_USER"), os.environ.get("USER"), os.environ.get("LOGNAME")):
        if u:
            users.add(u)
    try:
        pw = pwd.getpwuid(os.getuid())
        users.add(pw.pw_name)
        homes.add(pw.pw_dir)
    except KeyError:
        pass
    for u in list(users):
        try:
            homes.add(pwd.getpwnam(u).pw_dir)
        except KeyError:
            pass
    homes.add(os.path.expanduser("~"))
    host = os.uname().nodename
    hosts = {host, host.split(".")[0]}
    return (sorted(u for u in users if u and u != "root"), sorted(h for h in homes if h and h not in ("/", "/root")),
            sorted(h for h in hosts if h and h not in ("localhost", "localhost.localdomain")))


def scrubber(with_host):
    """text -> the text without this user's name and home folder, the host name and MAC addresses"""
    if with_host:
        return lambda t: t
    import re
    users, homes, hosts = identity()
    mac = re.compile(r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}(?![0-9A-Fa-f:])")
    word = lambda w: re.compile(r"(?<![\w.-])%s(?![\w.-])" % re.escape(w))
    subs = [(re.compile(re.escape(h) + r"(?![\w.-])"), "~") for h in sorted(homes, key=len, reverse=True)]
    subs += [(re.compile(re.escape(h)), "<host>") for h in hosts if "." in h]          # (a full name, wherever it stands)
    subs += [(word(h), "<host>") for h in hosts if "." not in h]
    subs += [(word(u), "<user>") for u in users]
    subs.append((mac, "<mac>"))

    def scrub(text):
        for rx, to in subs:
            text = rx.sub(to, text)
        return text
    return scrub


def scrub_cmdline(text, with_host):
    """the kernel command line without the disks' identifiers (root=UUID=..., rd.luks.uuid=...: they name the machine)"""
    if with_host:
        return text
    import re
    return re.sub(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", "<uuid>", text)


def scrub_xccdf(text):
    """XCCDF results without what names the machine: the target, its addresses, the facts that identify it, who ran it"""
    import re
    text = re.sub(r"(<target>)[^<]*(</target>)", r"\1&lt;host&gt;\2", text)
    text = re.sub(r"(<target-address>)[^<]*(</target-address>)", r"\1&lt;address&gt;\2", text)
    text = re.sub(r"(<identity\b[^>]*>)[^<]*(</identity>)", r"\1&lt;user&gt;\2", text)
    text = re.sub(r'(<fact name="urn:xccdf:fact:(?:asset:identifier|ethernet):[^"]*"[^>]*>)[^<]*(</fact>)',
                  lambda m: m.group(1) + ("&lt;mac&gt;" if "mac" in m.group(1).lower() else "&lt;address&gt;" if "ipv" in m.group(1) else "&lt;host&gt;") + m.group(2), text)
    return text


def test_result(text):
    """the TestResult element of XCCDF results as a document of its own ('' when there is none)"""
    a, b = text.find("<TestResult"), text.rfind("</TestResult>")
    if a < 0 or b < 0:
        return ""
    body = text[a:b + len("</TestResult>")]
    if "xmlns=" not in body[:body.index(">")]:
        body = body.replace("<TestResult", '<TestResult xmlns="%s"' % XCCDF_NS, 1)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"


# ---------------------------------------------------------------- the parts
def silik_json(silik, argv):
    """a command of silik run here, its standard output caught: (exit code, text). The tests replace it"""
    import contextlib
    import io
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            rc = silik.main(["-q"] + list(argv))
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
    return rc, out.getvalue()


def key_fingerprints(ctx, silik, path, home):
    """[{fingerprint, uid, created, expires}] of the OpenPGP keys in a key file, as gpg reads them"""
    run = plugin(silik, "sbom").run_ro
    rc, out = run(ctx, ["gpg", "--homedir", home, "--batch", "--no-tty", "--show-keys", "--with-colons", "--with-fingerprint", path], 30)
    keys, cur, want = [], None, False
    for l in out.splitlines() if rc == 0 else []:
        f = l.split(":")
        if f[0] == "pub":
            cur = {"fingerprint": "", "uid": "", "created": f[5] if len(f) > 5 else "", "expires": f[6] if len(f) > 6 else ""}
            keys.append(cur)
            want = True
        elif f[0] == "fpr" and cur is not None and want and len(f) > 9:
            cur["fingerprint"], want = f[9], False
        elif f[0] == "uid" and cur is not None and not cur["uid"] and len(f) > 9:
            cur["uid"] = f[9]
        elif f[0] == "sub":
            want = False
    return keys if rc == 0 else None


def repositories(ctx, silik):
    """{repositories: [...], rpm_keys: [...]}: the enabled repositories with the fingerprints of the keys their
    packages are checked against, and the keys the rpm database trusts"""
    import shutil
    import tempfile
    cv, run = plugin(silik, "cve"), plugin(silik, "sbom").run_ro
    reps = cv.repos()
    home = tempfile.mkdtemp(prefix="silik-evidence-gpg-")
    try:
        seen = {}
        for r in reps:
            r["keys"] = []
            for k in r["gpgkey"]:
                path = k[len("file://"):] if k.startswith("file://") else ""
                if not path:
                    r["keys"].append({"key": k, "fingerprints": None, "note": "not a file on this system: not fetched"})
                    continue
                if path not in seen:
                    seen[path] = key_fingerprints(ctx, silik, path, home) if os.path.isfile(path) else None
                r["keys"].append({"key": k, "fingerprints": seen[path]} if seen[path] is not None else
                                 {"key": k, "fingerprints": None, "note": "the file is missing or gpg does not read it"})
    finally:
        shutil.rmtree(home, ignore_errors=True)
    rc, out = run(ctx, ["rpm", "-q", "gpg-pubkey", "--qf", "%{VERSION}-%{RELEASE}\\t%{SUMMARY}\\n"], 30)
    keys = [dict(zip(("id", "summary"), l.split("\t", 1))) for l in sorted(out.splitlines()) if "\t" in l] if rc == 0 else None
    return {"repositories": reps, "rpm_keys": keys}


def audit_part(ctx, silik, a, scrub, files, skipped):
    """the audit into FILES; why not into SKIPPED"""
    import shutil
    import tempfile
    au = plugin(silik, "audit")
    if a.no_audit:
        skipped["audit"] = "left out (--no-audit)"
        return None
    if not shutil.which("oscap") or not au.datastream(silik):
        skipped["audit"] = "the scanner or its content is not installed: " + au.INSTALL
        return None
    tmp = tempfile.mkdtemp(prefix="silik-evidence-audit-")
    try:
        sm = au.evaluate(ctx, silik, a.profile, tmp)
        if sm is None:
            return None
        with open(os.path.join(tmp, "results.xml"), encoding="utf-8", errors="replace") as f:
            results = f.read()
        if a.with_host:
            files["audit/results.xml"] = results.encode()
            for name in ("arf.xml", "report.html"):
                with open(os.path.join(tmp, name), "rb") as f:
                    files["audit/" + name] = f.read()
        else:
            results = scrub(scrub_xccdf(results))
            clean = os.path.join(tmp, "results-clean.xml")
            with open(clean, "w", encoding="utf-8") as f:
                f.write(results)
            # (the report is written again from the results without the machine's names)
            rc, html = ctx.run(["oscap", "xccdf", "generate", "report", clean], check=False, capture=True)
            if rc == 0 and html:
                files["audit/report.html"] = scrub(html).encode()
            else:
                skipped["audit/report.html"] = "oscap did not write the report from the cleaned results (exit %s)" % rc
            skipped["audit/arf.xml"] = "holds what the checks read (accounts, mounts, addresses): only with --with-host"
        files["audit/testresult.xml"] = test_result(results).encode()
        files["audit/summary.json"] = (json.dumps(sm, indent=1) + "\n").encode()
        return sm
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def collect(ctx, silik, a):
    """{relative path: bytes} of the folder, and evidence.json's facts"""
    sb, cv = plugin(silik, "sbom"), plugin(silik, "cve")
    scrub = scrubber(a.with_host)
    files, skipped, results = {}, {}, {}
    say = lambda line: None if ctx.quiet else print("$ " + line, file=sys.stderr, flush=True)

    say("silik sbom export --format spdx; silik sbom export --format cyclonedx")
    bills, pkgs = sb.bills(ctx, silik)
    files["sbom.spdx.json"], files["sbom.cdx.json"] = bills["spdx"].encode(), bills["cyclonedx"].encode()
    results["packages"] = len(pkgs)

    say("silik cve --json%s" % (" --offline" if a.offline else ""))
    rep = cv.report(cv.probe(ctx, silik, offline=a.offline))
    files["cve.json"] = scrub(json.dumps(rep, indent=1) + "\n").encode()
    files["cve.txt"] = scrub(cv.text(rep, {"ok": "ok", "warn": "warn", "bad": "bad", "unknown": "?"}) + "\n").encode()
    results["cve"] = rep["summary"]

    say("silik audit --profile %s" % a.profile)
    sm = audit_part(ctx, silik, a, scrub, files, skipped)
    if sm:
        results["audit"] = {"profile": sm["profile"], "counts": sm["counts"]}

    for name, argv in (("status.json", ["status", "--json"]), ("secure-status.json", ["secure", "status", "--json", "--offline"]),
                       ("doctor.json", ["doctor", "--json"])):
        say("silik " + " ".join(argv))
        rc, text = silik_json(silik, argv)
        try:
            d = json.loads(text)
        except ValueError:
            skipped[name] = "silik %s gave no JSON (exit %s)" % (" ".join(argv), rc)
            continue
        if isinstance(d, dict):
            d.pop("seconds", None)          # (how long the doctor took: not a fact of the system)
        files[name] = scrub(json.dumps(d, indent=1) + "\n").encode()

    files["repositories.json"] = scrub(json.dumps(repositories(ctx, silik), indent=1) + "\n").encode()
    files["kernel-cmdline.txt"] = scrub(scrub_cmdline(silik.read("/proc/cmdline").strip() or "unknown", a.with_host) + "\n").encode()
    sbt = silik.sec_secureboot(silik.sec_container())
    files["secure-boot.txt"] = ((sbt or "unknown") + "\n").encode()
    return files, skipped, results


def manifest(files):
    import hashlib
    return "".join("%s  %s\n" % (hashlib.sha256(files[k]).hexdigest(), k) for k in sorted(files))


def archive(path, top, files, mtime):
    """the folder as a tar.gz that is the same bytes for the same files: sorted, owner 0, one date, no gzip time"""
    import gzip
    import io
    import tarfile
    tmp = path + ".part"
    with open(tmp, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.USTAR_FORMAT) as tar:
                for k in sorted(files):
                    ti = tarfile.TarInfo(top + "/" + k)
                    ti.size, ti.mtime, ti.mode, ti.uid, ti.gid, ti.uname, ti.gname = len(files[k]), mtime, 0o644, 0, 0, "", ""
                    tar.addfile(ti, io.BytesIO(files[k]))
    os.replace(tmp, path)


def evidence(ctx, a):
    import calendar
    import shutil
    import time
    silik = SILIK
    sb = plugin(silik, "sbom")
    day = time.gmtime(sb.now())
    date, top = time.strftime("%Y-%m-%d", day), NAME + time.strftime("%Y%m%d", day)
    out = os.path.abspath(a.output or ".")
    folder, tgz = os.path.join(out, top), os.path.join(out, top + ".tar.gz")
    if os.path.exists(folder) and not os.path.isfile(os.path.join(folder, "evidence.json")) and (not os.path.isdir(folder) or os.listdir(folder)):
        silik.die("%s exists and is not an evidence folder: choose another -o DIR" % folder, 2)
    if ctx.dry:
        for line in ("silik sbom export --format spdx -o %s/sbom.spdx.json" % folder, "silik sbom export --format cyclonedx -o %s/sbom.cdx.json" % folder,
                     "silik cve --json%s > %s/cve.json" % (" --offline" if a.offline else "", folder),
                     "silik audit --profile %s   # -> %s/audit%s" % (a.profile, folder, " (left out: --no-audit)" if a.no_audit else ""),
                     "silik status --json > %s/status.json" % folder, "silik secure status --json --offline > %s/secure-status.json" % folder,
                     "silik doctor --json > %s/doctor.json" % folder,
                     "# and repositories.json, kernel-cmdline.txt, secure-boot.txt, evidence.json, README.txt, MANIFEST; then %s" % tgz):
            print("$ " + line if not line.startswith("#") else line)
        return 0
    files, skipped, results = collect(ctx, silik, a)
    sy = sb.system(silik)
    listed = [f for f in FILES if f[0] in files]
    info = {
        "format": FORMAT, "date": date, "silik": silik.VERSION,
        "system": {"name": sy["name"], "version": sy["version"], "base": sy["base"], "arch": sy["arch"]},
        "with_host": bool(a.with_host), "offline": bool(a.offline), "results": results,
        "files": [{"file": f[0], "what": f[2], "same_bytes_for_the_same_system": f[1]} for f in listed],
        "left_out": skipped,
        "statement": "what the tools saw on this system on this day; not a statement of compliance with any regulation or standard",
    }
    files["evidence.json"] = (json.dumps(info, indent=1) + "\n").encode()
    files["README.txt"] = "\n".join(
        README[l] % {"date": date, "silik": silik.VERSION, "host": HOST_NOTE[l][1 if a.with_host else 0],
                     "files": "\n".join(["%-22s %s" % (f[0], f[2 + n]) for f in listed] + ["%-22s %s" % (f[0], f[1 + n]) for f in OWN_FILES])}
        for n, l in enumerate(LANGS)).encode()
    files["MANIFEST"] = manifest(files).encode()
    if os.path.isdir(folder):
        shutil.rmtree(folder)          # (an evidence folder of the same day: this run replaces it)
    for k in sorted(files):
        p = os.path.join(folder, k)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(files[k])
    archive(tgz, top, files, calendar.timegm(day[:3] + (0, 0, 0)))
    for k in sorted(files):
        print("%-22s %8d bytes" % (k, len(files[k])))
    for k in sorted(skipped):
        print("%-22s left out: %s" % (k, skipped[k]))
    c = results.get("cve", {})
    print("cve: %d ok, %d warn, %d bad, %d unknown%s" % (c.get("ok", 0), c.get("warn", 0), c.get("bad", 0), c.get("unknown", 0),
          "; audit: " + ", ".join("%d %s" % (v, k) for k, v in results["audit"]["counts"].items()) if "audit" in results else ""))
    print("%s\n%s" % (folder, tgz))
    print("what the tools saw today, for the person who has to state something about this system: not a statement of compliance")
    return 0


def register(group, silik):
    global SILIK
    SILIK = silik
    group.add_argument("-o", "--output", metavar="DIR", help="where the dated folder and its tar.gz go (default: here)")
    group.add_argument("--with-host", action="store_true", help="keep the user's and the host's names and addresses, and the audit's full documents")
    group.add_argument("--no-audit", action="store_true", help="leave the OpenSCAP evaluation out")
    group.add_argument("--profile", default="cis_workstation_l1", metavar="NAME", help="the audit's profile (silik audit profiles)")
    group.add_argument("--offline", action="store_true", help="dnf's cache only: the repositories are not asked")
    group.set_defaults(fn=evidence)
