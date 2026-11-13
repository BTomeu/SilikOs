# Evidència de compliment: `silik sbom`, `silik cve`, `silik audit`, `silik evidence` (13/11/2026)

**Resum (català).** Quatre ordres noves de `silik` (plugins) diuen, amb fitxers que una eina o un auditor pot llegir,
què és aquesta estació de treball:

| Ordre | Què fa |
|---|---|
| `silik sbom export [--format spdx\|cyclonedx] [-o FITXER]` | La llista de materials de programari del sistema, de la base de dades d'rpm: SPDX 2.3 o CycloneDX 1.6 (JSON). El mateix sistema dona els mateixos bytes. `silik sbom diff A B`: què ha canviat entre dues llistes. |
| `silik cve [--json] [--offline]` | Els avisos de seguretat pendents i els seus CVE (de l'`updateinfo` dels repositoris), els CVE que el kernel en marxa encara té perquè no s'ha reiniciat, i sempre el que no pot saber. Estats i codis de sortida com `silik doctor`. |
| `silik audit [--profile NOM] [--report DIR]`, `silik audit profiles` | OpenSCAP (l'escàner i el contingut de la base) contra un perfil (CIS, ANSSI, STIG...). Només llegeix: informes i una taula. **No remedia mai.** |
| `silik evidence [-o DIR] [--with-host]` | Una carpeta amb data (i el seu `tar.gz`) amb tot això, l'estat, els repositoris i les empremtes de les claus, i un `MANIFEST` amb el sha256 de cada fitxer. Res de personal si no es demana. |

**SilikOS no declara que ningú compleixi res**: produeix evidència (el que les eines han vist aquell dia) per a la
persona que ha de signar. El text del Reglament (UE) 2024/2847 (CRA) citat aquí s'ha llegit d'una còpia de l'XHTML
d'EUR-Lex, no d'EUR-Lex mateix (la sessió no hi arribava): cal comprovar-lo allà abans de fer-lo servir (secció 2).
Les referències a ISO/SAE 21434, IEC 62443 i TISAX són de memòria [A]: aquestes normes no són públiques. **No és
consell legal** (⚖️). La llista de materials és la de l'estació de treball, no la d'un producte que s'hi construeixi.
Executat en un contenidor `almalinux:9`; no en un sistema instal·lat (`docs/STATUS.md`).

---

## 1. What this is, and what it is not

An engineering company is asked what software is on the machines its products are designed and built on: by its
customers' audits and, for what it ships in the EU, by the documentation the Cyber Resilience Act asks of a
manufacturer. The honest answer is a set of files made by tools, dated, that somebody else can check. These four
commands make those files from what the base system already knows about itself (the rpm database, the repositories'
advisories, the base's own SCAP content). They add no agent, no service and no network traffic of their own (`silik
cve` asks the repositories the system already updates from, as `dnf` does; `--offline` does not).

They do not make a machine compliant, they do not say that it is, and nothing they print is a certificate. Every
output says what it does not cover. `silik audit` changes nothing on the system.

## 2. The regulation: what its text says

Regulation (EU) 2024/2847 of 23 October 2024 (Cyber Resilience Act), OJ L, 2024/2847, 20.11.2024,
ELI: http://data.europa.eu/eli/reg/2024/2847/oj.

**Where the text below was read.** `eur-lex.europa.eu` and `op.europa.eu` are not reachable from the session that
wrote this (the session's network refuses them). The quotations are from a copy of EUR-Lex's English XHTML of the act
kept in a third party's public repository (github.com/Killerz007/cra-readiness-skill, `official/current/CRA-2024-2847.xhtml`,
sha256 `fe0cca4a0caec50e7cf5a91432b94a19b211f86be8584fdba56372bdcea571ed`, which names the Publications Office as its
source), read on 13/11/2026. Only the Official Journal is authentic: **check each quotation against EUR-Lex before
relying on it** (row in `docs/STATUS.md`, not verified). Nothing below is paraphrased from memory; what is ours is
marked "our reading".

**Dates** (Article 71, quoted whole):

> 1. This Regulation shall enter into force on the twentieth day following that of its publication in the Official
> Journal of the European Union.
> 2. This Regulation shall apply from 11 December 2027.
> However, Article 14 shall apply from 11 September 2026 and Chapter IV (Articles 35 to 51) shall apply from 11 June 2026.

Published on 20.11.2024, so in force since 10 December 2024 (our count of the twenty days). Article 69(2) and (3):

> 2. Products with digital elements that have been placed on the market before 11 December 2027 shall be subject to
> the requirements set out in this Regulation only if, from that date, those products are subject to a substantial
> modification.
> 3. By way of derogation from paragraph 2 of this Article, the obligations laid down in Article 14 shall apply to
> all products with digital elements that fall within the scope of this Regulation that have been placed on the
> market before 11 December 2027.

**Who and what** (Article 3, points (1), (13), (39); Article 2(1) and 2(2)):

> (1) 'product with digital elements' means a software or hardware product and its remote data processing solutions,
> including software or hardware components being placed on the market separately;
>
> (13) 'manufacturer' means a natural or legal person who develops or manufactures products with digital elements or
> has products with digital elements designed, developed or manufactured, and markets them under its name or
> trademark, whether for payment, monetisation or free of charge;
>
> (39) 'software bill of materials' means a formal record containing details and supply chain relationships of
> components included in the software elements of a product with digital elements;
>
> Article 2(1). This Regulation applies to products with digital elements made available on the market, the intended
> purpose or reasonably foreseeable use of which includes a direct or indirect logical or physical data connection
> to a device or network.
>
> Article 2(2). This Regulation does not apply to products with digital elements to which the following Union legal
> acts apply: (a) Regulation (EU) 2017/745; (b) Regulation (EU) 2017/746; (c) Regulation (EU) 2019/2144.

(Regulation (EU) 2019/2144 is the type-approval of motor vehicles: our reading is that a component type-approved
under it is outside the CRA, and that its cybersecurity is asked for by the vehicle rules and by the customer
instead ⚖️.)

**The bill of materials** (Annex I, Part II, point (1); Article 13(24); Annex VII, points 2(b) and 8; Annex II, point 9):

> Manufacturers of products with digital elements shall: (1) identify and document vulnerabilities and components
> contained in products with digital elements, including by drawing up a software bill of materials in a commonly
> used and machine-readable format covering at the very least the top-level dependencies of the products;
>
> Article 13(24). The Commission may, by means of implementing acts taking into account European or international
> standards and best practices, specify the format and elements of the software bill of materials referred to in
> Part II, point (1), of Annex I. [...]
>
> Annex VII, 2(b): necessary information and specifications of the vulnerability handling processes put in place by
> the manufacturer, including the software bill of materials, the coordinated vulnerability disclosure policy,
> evidence of the provision of a contact address for the reporting of the vulnerabilities and a description of the
> technical solutions chosen for the secure distribution of updates;
>
> Annex VII, 8: where applicable, the software bill of materials, further to a reasoned request from a market
> surveillance authority provided that it is necessary in order for that authority to be able to check compliance
> with the essential cybersecurity requirements set out in Annex I.
>
> Annex II, 9: If the manufacturer decides to make available the software bill of materials to the user, information
> on where the software bill of materials can be accessed.

No implementing act under Article 13(24) is known to us: whether one exists was not looked up [A]. SPDX and CycloneDX
are the two formats in common use; the act names none.

**Vulnerabilities and updates** (Annex I, Part I, point (2)(a) and (c); Part II, points (2), (3), (7); Article 13(5)
and 13(8), first sentence):

> (2) On the basis of the cybersecurity risk assessment referred to in Article 13(2) and where applicable, products
> with digital elements shall: (a) be made available on the market without known exploitable vulnerabilities; [...]
> (c) ensure that vulnerabilities can be addressed through security updates, including, where applicable, through
> automatic security updates that are installed within an appropriate timeframe enabled as a default setting, with a
> clear and easy-to-use opt-out mechanism, through the notification of available updates to users, and the option to
> temporarily postpone them;
>
> Part II (2) in relation to the risks posed to products with digital elements, address and remediate
> vulnerabilities without delay, including by providing security updates; [...]
> (3) apply effective and regular tests and reviews of the security of the product with digital elements;
> (7) provide for mechanisms to securely distribute updates for products with digital elements to ensure that
> vulnerabilities are fixed or mitigated in a timely manner and, where applicable for security updates, in an
> automatic manner;
>
> Article 13(5). For the purpose of complying with paragraph 1, manufacturers shall exercise due diligence when
> integrating components sourced from third parties so that those components do not compromise the cybersecurity of
> the product with digital elements, including when integrating components of free and open-source software that
> have not been made available on the market in the course of a commercial activity.
>
> Article 13(8). Manufacturers shall ensure, when placing a product with digital elements on the market, and for the
> support period, that vulnerabilities of that product, including its components, are handled effectively and in
> accordance with the essential cybersecurity requirements set out in Part II of Annex I.

**Reporting** (Article 14(1) and 14(2), the three deadlines; applies from 11 September 2026):

> 1. A manufacturer shall notify any actively exploited vulnerability contained in the product with digital elements
> that it becomes aware of simultaneously to the CSIRT designated as coordinator, in accordance with paragraph 7 of
> this Article, and to ENISA. [...]
> 2. [...] (a) an early warning notification of an actively exploited vulnerability, without undue delay and in any
> event within 24 hours of the manufacturer becoming aware of it [...]; (b) [...] a vulnerability notification,
> without undue delay and in any event within 72 hours of the manufacturer becoming aware of the actively exploited
> vulnerability [...]; (c) [...] a final report, no later than 14 days after a corrective or mitigating measure is
> available [...]

**The documentation** (Article 31(1) and (2); Article 13(13); Annex VII, points 2(c) and 6):

> Article 31(1). The technical documentation shall contain all relevant data or details of the means used by the
> manufacturer to ensure that the product with digital elements and the processes put in place by the manufacturer
> comply with the essential cybersecurity requirements set out in Annex I. It shall at least contain the elements
> set out in Annex VII.
> (2). The technical documentation shall be drawn up before the product with digital elements is placed on the
> market and shall be continuously updated, where appropriate, at least during the support period.
>
> Article 13(13). Manufacturers shall keep the technical documentation and the EU declaration of conformity at the
> disposal of the market surveillance authorities for at least 10 years after the product with digital elements has
> been placed on the market or for the support period, whichever is longer.
>
> Annex VII, 2(c): necessary information and specifications of the production and monitoring processes of the
> product with digital elements and the validation of those processes;
> Annex VII, 6: reports of the tests carried out to verify the conformity of the product with digital elements and
> of the vulnerability handling processes with the applicable essential cybersecurity requirements as set out in
> Parts I and II of Annex I;

**What the act does not say.** It asks for the bill of materials of the *product*. It does not ask, in the text
read, for a bill of materials of the machines a product is built on. Annex III lists "Operating systems" among the
important products of class I (point 11): that is about an operating system placed on the market as a product, and
is the question `docs/COMERCIAL.md` (B4) leaves to a lawyer for SilikOS itself.

## 3. Which question each command helps to answer

"Helps to answer" is our reading ⚖️. The right-hand column is as much part of the answer as the left.

| Command | Produces | Helps to answer | Does not prove |
|---|---|---|---|
| `silik sbom export` | Every rpm package of the system: name, epoch, version, release, architecture, licence text, supplier, source package, purl, rpm's header and payload digests, signing key id; SilikOS's own marked | **Product = this system** (an industrial PC, a test bench or an appliance shipped with it): Annex I Part II (1) for the operating-system layer, in a commonly used machine-readable format; Annex VII 2(b) and 8. **Workstation as the place of production**: Annex VII 2(c) (what the build environment is made of), Article 13(5) (which third-party components were there); the customer's question "which software, in which versions, is on your development machines" (ISO/SAE 21434, IEC 62443-4-1, TISAX: section 4) | That the list is complete: software rpm did not install is not in it (the vendors' tools in /opt, pip, containers, Wine prefixes, firmware). It is not the bill of the *product's* own software (firmware, libraries linked into it): that comes from the product's build. No dependency graph beyond "the system contains these" |
| `silik sbom diff A B` | Added, removed, changed versions between two bills | "What changed on the build machine between release X and release Y" (change control; Article 31(2) "continuously updated") | Why it changed |
| `silik cve` | The pending security advisories with their CVE ids and severities, each fixed by an available update; the CVEs still in the running kernel until a restart; when the automatic update last ran; what is not covered | Annex I Part I (2)(a) ("without known exploitable vulnerabilities") for the operating-system layer on the day of the report; Part II (2) (remediate without delay: how many advisories wait, since when); the customer's patch-management question | That no vulnerability exists. Only flaws for which the repositories published an advisory, that is, a fix: a known flaw without a fixed package is not listed. Nothing about SilikOS's own packages (no advisory feed), software outside rpm, firmware. "Exploitable" is not judged |
| `silik audit` | The scanner's HTML report, XCCDF results, ARF, a count of pass / fail / not applicable and the failed rules, for a published profile (CIS, ANSSI BP-028, STIG, BSI, CCN-STIC...) | Annex I Part II (3) ("effective and regular tests and reviews"), Annex VII 6 (test reports), for the configuration of the operating system; a customer's "is the workstation hardened against a recognised baseline, and where does it differ" | Compliance with the benchmark: a profile's rules are a tool's reading of it, many need a person's judgement, and a failed rule may be the right setting for an EDA workstation. Nothing about the product |
| `silik evidence` | All of the above, `silik status`, `silik secure status`, `silik doctor`, the enabled repositories with the fingerprints of their keys, the kernel command line, Secure Boot, a MANIFEST of sha256 | One dated, self-checking folder to file with the technical documentation (Article 31, Article 13(13): kept ten years) or to hand to an auditor; Annex VII 2(b) "the technical solutions chosen for the secure distribution of updates" (signed repositories, which keys) | Who made it and when: the folder is not signed and its date is the machine's clock. Sign or timestamp the `tar.gz` with your own means if that matters |

What SilikOS itself gives towards Annex I Part I (2)(c) and Part II (7), by design and independent of these commands:
automatic updates on by default with one command to turn them off, from GPG-checked repositories
(`docs/SECURITY.md`). That is a property of the workstation, not of a product built on it.

## 4. Other frameworks a customer may name

[A] for this whole section: ISO/SAE 21434, IEC 62443 and the VDA ISA catalogue behind TISAX are not public texts and
were **not read**; the clause names are from memory and must be checked in the customer's own copy before they are
written into an answer.

- **ISO/SAE 21434** (road vehicles, cybersecurity engineering): asks an organisation to manage the tools that can
  affect the cybersecurity of an item [A: "tool management", clause 5]. A dated bill of the development workstation
  and its pending advisories is the kind of record that answers it.
- **IEC 62443-4-1** (secure product development lifecycle): asks for a secured development environment and for
  control of third-party components [A: practices SM-7 and SM-9]. The audit report and the bill are inputs to both.
- **TISAX / VDA ISA**: asks for an inventory of IT assets, patch and vulnerability management, and hardening of
  clients [A: controls in chapters 1, 5]. `silik evidence` gathers the technical part; the organisational part
  (who is responsible, how often, what happens on a finding) is the company's.

## 5. `silik sbom`

```bash
silik sbom export                                   # SPDX 2.3 JSON on the standard output
silik sbom export --format cyclonedx -o bom.cdx.json
silik sbom export --stamp -o bom.spdx.json          # with the time of the run
silik sbom diff before.spdx.json after.cdx.json     # + added, - removed, ~ another version; exit 1 when they differ
```

One `rpm -qa --qf ...` (printed on stderr, so that the standard output is the bill alone); 0.16-0.18 s for 291
packages. For each package:

| Field | From rpm | SPDX 2.3 | CycloneDX 1.6 |
|---|---|---|---|
| name, version | NAME, [EPOCH:]VERSION-RELEASE | `name`, `versionInfo` | `name`, `version` |
| supplier | VENDOR (SilikVolt for our own) | `supplier: "Organization: ..."` | `supplier.name` |
| licence | LICENSE, as written | `licenseDeclared: LicenseRef-rpm-<hash>` with the text under `hasExtractedLicensingInfos`; `licenseConcluded: NOASSERTION` | `licenses[].license.name` |
| source | SOURCERPM | `sourceInfo` | property `silikos:rpm:sourcerpm` |
| upstream | URL | `homepage` | `externalReferences[type=website]` |
| identity | name, epoch, version, release, arch | external reference `purl`; `rpm-nevra` | `purl`, `bom-ref`; `silikos:rpm:nevra`, `:arch`, `:epoch` |
| digests | SHA256HEADER, PAYLOADDIGEST | external references `rpm-header-sha256`, `rpm-payload-sha256` | properties `silikos:rpm:header-sha256`, `:payload-sha256` |
| signature | the key id of RSAHEADER | `rpm-signing-key-id` | `silikos:rpm:signing-key-id` |
| origin | (below) | `comment: "origin: ..."` | property `silikos:origin` |

- **Licences are not translated.** EL 9's packages mostly state their licence in Fedora's older notation (`GPLv3+`,
  `ASL 2.0`), which is not an SPDX expression. Turning one into the other is a judgement; the bill carries rpm's own
  text and says so.
- **The digests are rpm's records, not the sha256 of an `.rpm` file.** No `.rpm` file is on an installed system. The
  header digest identifies the package's metadata as built, the payload digest its contents as packed; both are in
  the signed header. They are therefore not written as SPDX `checksums` or CycloneDX `hashes`, which would say
  "the file's".
- **purl**, as the purl specification defines the `rpm` type (`types/rpm-definition.json` of package-url/purl-spec,
  read 13/11/2026: "The namespace is the vendor such as Fedora or OpenSUSE. It is not case sensitive and shall be
  lowercased"; "The version is the combined version and release of an RPM"; qualifiers `epoch`, `arch`; the
  repository "should be implied either from the distro qualifiers key or using a repository base URL"):
  `pkg:rpm/almalinux/openssl-libs@3.5.8-2.el9_8?arch=x86_64&distro=almalinux-9.8&epoch=1`. The namespace comes from
  rpm's Vendor: `almalinux`, `fedora` for EPEL (its packages' Vendor is "Fedora Project" [A: not seen here, no EPEL
  package was installed]), `silikos` for our own, another vendor's name as a word. **A package without a Vendor that
  is not ours gets no purl** and origin `unknown`: a purl would be a guess about where it came from. Those are the
  packages to look at (a vendor's hand-made RPM).
- **SilikOS's own packages** are those built from the recipes of this repository (the list `OWN` in the plugin: a
  test holds it to `packages/`, `eda/`, `dev/`, `wine/`) for which rpm names no other vendor; plus SilikStudio.
  Our packages carry no Vendor tag today; when they get one ("SilikVolt"), the rule already takes it.
- **Deterministic.** Sorted; the document ids (SPDX `documentNamespace`, CycloneDX `serialNumber`) are a UUID made
  from the package list; no time of the run. SPDX requires a creation time: it is the time of the last package
  change, since when the bill is true (said in the document's `creationInfo.comment`). `--stamp` writes the time of
  the run instead, and CycloneDX then gets its `timestamp` (`SOURCE_DATE_EPOCH` is honoured).
- **The described system** is one SPDX package / CycloneDX `metadata.component` of kind operating system, named as
  `os-release` names it (SilikOS 9.8) with the base's CPE; every package is "contained" by it. There is no
  package-to-package dependency graph.
- **Valid by the official schemas**: SPDX 2.3's `spdx-schema.json` and CycloneDX 1.6's `bom-1.6.schema.json`
  (`tests/data/sbom`, with their licences: CC-BY-3.0 and Apache-2.0), checked in the tests by a validator of our own
  (`tests/schema_min.py`, standard library, draft-07: it stops at a keyword it does not know) and, once, in the
  container with python3-jsonschema 3.2.0 from AppStream: 0 errors each (`docs/STATUS.md`). A schema checks the shape,
  not the meaning.

## 6. `silik cve`

```bash
silik cve                # the report; exit 0 all ok, 1 warn or unknown, 2 bad
silik cve --json         # for a program (the standard output is the JSON alone)
silik cve --offline      # dnf's cache only
```

Reads `dnf -q updateinfo list --security --with-cve` (asks the repositories), then from dnf's cache `dnf -q -C
updateinfo info --security` (titles, dates, severities, CVE ids) and, only when a newer kernel is installed than the
one running, `dnf -q -C updateinfo list --security --installed --with-cve`. Each command is printed on stderr.

| Row | ok | warn | bad | unknown |
|---|---|---|---|---|
| advisories | none waits | some wait, the worst Moderate or Low | the worst is Critical or Important | dnf gives no list |
| running kernel | it is the newest installed, or no security advisory lies between it and the newest | CVEs lie between, worst Moderate or Low | worst Critical or Important | the running kernel is not a package of the system (a container, another kernel), or dnf does not say |
| automatic updates | the row of `silik doctor` | | | |

Every advisory listed is fixed by an update that is available: that is what an advisory is. The kernel row compares
versions as rpm does (the comparison was checked once against 17 200 answers of rpm 4.16.1.3's own `labelCompare`,
0 differences; the tests hold 24 of them) and counts the CVE ids of the advisories for kernel versions after the running one, up to the newest installed.

Printed every time, with what is on this system, under "not covered (this command cannot know)":
SilikOS's own packages (how many are installed: no advisories are published for them), packages without a vendor,
folders in /opt that no package owns, programs in /usr/local, Python packages installed outside rpm, containers,
Wine prefixes and virtual machines, flaws without a fix, programs still running an old library, firmware.

Severities are the base's (AlmaLinux's advisories: Critical, Important, Moderate, Low), not CVSS scores.

## 7. `silik audit`

```bash
silik audit profiles                                   # what the base's content has; ● the default
silik audit                                            # CIS Workstation Level 1, reports in ~/.local/state/silikos/audit/cis_workstation_l1
silik audit --profile anssi_bp28_minimal --report ./audit-2026-11
```

The scanner is the base's `oscap` (openscap-scanner 1.3.14), the content the base's SCAP Security Guide
(scap-security-guide 0.1.82: `/usr/share/xml/scap/ssg/content/ssg-almalinux9-ds.xml`). The 20 profiles of that data
stream (`oscap info --profiles`, 13/11/2026): ANSSI-BP-028 minimal / intermediary / enhanced / high; BSI SYS.1.1 and
SYS.1.3; CCN-STIC basic / intermediate / advanced; CIS Level 1 and 2 for Server and for Workstation
(`cis_server_l1`, `cis`, `cis_workstation_l1`, `cis_workstation_l2`); NIST 800-171 (`cui`, draft); ACSC Essential
Eight (`e8`) and ISM Official (`ism_o`); HIPAA; OSPP; PCI-DSS v4.0.1; DISA STIG and STIG with GUI. The default is
`cis_workstation_l1`: the one written for a desktop.

It runs `oscap xccdf eval --profile ... --results DIR/results.xml --results-arf DIR/arf.xml --report DIR/report.html`
as root (through `sudo` for a user: many rules read what only root may; the reports are then given back to the
user), keeps oscap's per-rule lines off the terminal and prints the counts, the score oscap computed and the ten
most severe failed rules with their titles. Exit 0 when no rule failed, 1 when some did.

**It never remediates, and there is no switch that does.** A profile's remediation rewrites the base's
configuration: PAM, sshd, the crypto policy, mount options, audit rules, umask. SilikOS's rule is that the base is
not changed, and which of a benchmark's rules are right for a workstation that runs EDA tools and Wine is a decision
to take rule by rule (several CIS rules would break vendor installers or licence daemons [A]). The base's own tool
writes the script for whoever wants to read it:

```bash
oscap xccdf generate fix --fix-type bash --result-id "" --output fix.sh DIR/results.xml   # the failed rules only
```

(run on 13/11/2026: 398 lines for the 7 failures of the container; not applied). Read it; apply what you chose.

`results.xml` and `arf.xml` carry the machine's host name, IP and MAC addresses; `arf.xml` also what the checks read
(accounts, mounts, services). The rule that asks whether security patches are up to date refers to a file on
`security.almalinux.org` that the scanner fetches only with `--fetch-remote-resources`, which `silik audit` does not
pass: `silik cve` answers that question.

In a container most rules are not applicable (no kernel, no boot loader, no services): the numbers of the test are
in `docs/STATUS.md` as what they are, not as a result about SilikOS.

## 8. `silik evidence`

```bash
silik evidence                       # ./silikos-evidence-YYYYMMDD/ and ./silikos-evidence-YYYYMMDD.tar.gz
silik evidence -o ~/audits --no-audit
silik evidence --with-host           # keeps the machine's and the user's names; adds the scanner's full documents
silik --dry-run evidence             # the commands it is made of; writes nothing
```

| File | What |
|---|---|
| `sbom.spdx.json`, `sbom.cdx.json` | `silik sbom export`, both formats |
| `cve.json`, `cve.txt` | `silik cve` |
| `audit/report.html`, `audit/testresult.xml`, `audit/summary.json` | `silik audit` (left out, and said, when the scanner is not installed or with `--no-audit`) |
| `status.json`, `secure-status.json`, `doctor.json` | `silik status`, `silik secure status`, `silik doctor`, as JSON |
| `repositories.json` | the enabled repositories as their files say, the fingerprints of the keys their packages are checked against (`gpg --show-keys`), the keys the rpm database trusts |
| `kernel-cmdline.txt`, `secure-boot.txt` | `/proc/cmdline`; enabled / disabled / bios / unknown |
| `evidence.json` | the date, what ran, the counts, what was left out and why, which files are the same bytes for the same system |
| `README.txt` | what each file is and what it does not show, in English, Catalan and Spanish |
| `MANIFEST` | sha256 of every other file: `sha256sum -c MANIFEST` |

- **Nothing personal** unless `--with-host`: the user's name (`<user>`) and home folder (`~`), the host name
  (`<host>`), MAC addresses (`<mac>`), the IP addresses of the audit's target (`<address>`), the disk identifiers of
  the kernel command line (`<uuid>`) are replaced, as whole words; the ARF document is left out; the audit's HTML
  report is written again by `oscap xccdf generate report` from the results without those names. Names of EDA boxes
  and Wine prefixes stay (they name tools, not people).
- **Reproducible**: the same system on the same day gives byte-identical `sbom.*`, `repositories.json`,
  `kernel-cmdline.txt`, `secure-boot.txt`, `status.json`. The others carry times (the scan's start and end, "last
  run 5 h ago") and are marked so in `evidence.json`. The archive is made the same way every time (sorted, owner 0,
  the day's date, no gzip time): the same files give the same archive.
- The folder of a day is replaced by a second run that day; a folder of that name that is not an evidence folder is
  not touched.
- It exits 0 when the folder was written: the findings are in the folder (and in its last lines), not in the exit code.

## 9. Packages

`openscap-scanner` and `scap-security-guide` (AppStream) are weak dependencies (`Recommends`) of `silikos-security`.
Measured with `dnf` on AlmaLinux 9.8, 13/11/2026, in a minimal container: 3.8 MB to download, 114 MB installed, 8
packages (scap-security-guide 48.1 MB, openscap 68.9 MB, openscap-scanner 0.1 MB, and libxslt, xmlsec1,
xmlsec1-openssl, xml-common, procps-ng, which a desktop has already [A]). Without them `silik audit` says what to
install and `silik evidence` writes everything else. `silik sbom` and `silik cve` need only rpm and dnf.

## 10. Not verified

`docs/STATUS.md` has the rows. In short: run in an `almalinux:9` container as root and as a user, never on an
installed SilikOS; the kernel row with a real restart pending (the container's rpm database held two kernel records
and the running kernel was named by a variable); `sudo` for `silik audit`; EPEL's and other vendors' packages in the
bill; the quotations against EUR-Lex itself; the bills in a customer's own SBOM tool.
