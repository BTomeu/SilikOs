# SilikOS: compliance and business model (12/11/2026)

A technical audit of the repository and a read of public sources, done by an agent and reviewed. **It is not legal
advice**: the points marked ⚖️ have to be looked at by a lawyer before anything is sold. [A] means assumption. The
policies of AlmaLinux and Red Hat were read from the search engine's fragments (the session's network did not reach
them): they have to be read in full before deciding.

## State of the repository

- There is no `LICENSE` or `COPYING`.
- Our own packages declare `License: LicenseRef-SilikVolt`, which is defined nowhere.
- No script makes SRPMs (`rpmbuild -bb` only). **Now they do** (12/11/2026): all the build scripts make the SRPM
  (`build/srpm/`), see section 2.
- The repository is private.
- The workflows delete the old versions of the releases. **Not any more** (12/11/2026): they move them to the release
  `sources-archive` with their SRPM (`tools/release_keep.sh`).
- `build_iso.sh` redistributes AlmaLinux's boot ISO, modified.

While everything is private nothing is distributed to third parties [A]. Everything that follows blocks the first
public ISO, and the first sale even more.

## 1. Blockers before distributing or selling

### B1. Our own licence

Without a `LICENSE`, nobody has the right to redistribute SilikOS.
- The shell extension is loaded inside gnome-shell (GPL-2.0+): it must have a licence compatible with the GPL [A].
- `installer/installer-base.css` probably comes from anaconda (GPL-2.0+) [A]: it has to be attributed or rewritten.

### B2. Corresponding source (GPL/LGPL/MPL)

Building from pinned upstream tags is not enough:
- **GPLv2 §3** (openocd, dfu-util, stm32flash, klayout, xschem, qucs-s…): a commercial distribution has to come with
  the source or with a written offer valid for 3 years.
- **Our specs and scripts** are part of the corresponding source.
- **Wine Mono/Gecko** (MPL-2.0 §3.2): it has to be said where the source is.
- **The modified boot ISO:** it is also ours to offer the source of the GPL packages it carries (kernel, grub2,
  anaconda…).

### B3. The AlmaLinux and Red Hat trademarks

- **AlmaLinux:** we can use the name (not the logos) to describe the origin truthfully. Our branding has to be more
  prominent.
- **AlmaLinux's logos:** what is still seen of `almalinux-logos` and of Initial Setup has to be reviewed [A].
- **"Binary for binary" is false:** since 2023, AlmaLinux aims for **ABI compatibility** with RHEL, not a 1:1 copy.
- **Red Hat:** the name can be used to describe the compatibility truthfully, without logos and with an attribution
  note.
- **Safe sentence:** *"SilikOS is built on AlmaLinux OS 9, which aims for ABI compatibility with Red Hat® Enterprise
  Linux® 9. SilikOS is not affiliated with or endorsed by Red Hat or the AlmaLinux OS Foundation."*

### B4. Selling in the EU ⚖️

- **Product liability (Directive 2024/2853):**
  - It applies to products placed on the market from 9/12/2026 on, and software is included.
  - Free software is left out only if it is not a commercial activity.
- **Cyber Resilience Act (Regulation 2024/2847):**
  - The reporting of exploited vulnerabilities applies from 11/9/2026.
  - Full application is on 11/12/2027.
  - Monetising SilikOS itself can make SilikVolt a "manufacturer" [A ⚖️].
- **Sales to private individuals:** the consumer's legal guarantees apply all the same (Directive 2019/770).

### B5. SilikStudio in the ISO

It is aggregation, and that is correct. But it is proprietary: it needs its own EULA, visible and separate from the
GPL notices.

## 2. List of work in the repository (for when the owner decides the licence)

**Licences and brand**
1. A `LICENSE` at the root (proposal: GPL-3.0-or-later for SilikOS's code).
2. For the brand:
   - `brand/LICENSE` and `TRADEMARKS.md`: all rights reserved.
   - Redistributing the unmodified ISO is allowed; whoever modifies it has to remove the brand.
   - Proposal to register SilikOS and SilikVolt at the EUIPO ⚖️.
3. `LicenseRef-SilikVolt` → the chosen SPDX, with `%license LICENSE` in each spec, and SPDX headers in the code files.

**Metadata of the upstream packages**
4. `LicenseRef-Upstream` (magic, netgen, ngspice, yosys) → the real SPDX of each tag. **Done** (12/11/2026, read in the
   licence files of each pinned version): magic `HPND-UC-export-US` + two notices that are not in the SPDX list
   (`LicenseRef-`, with the text in the package), netgen `GPL-1.0-or-later`, ngspice and yosys by parts (see the specs).
5. `%licences` (`eda/common.inc`): it has to gather more names and make the build fail if it finds none. **Done**:
   LICENSE*, LICENCE*, COPYING*, COPYRIGHT* in upper or lower case (netgen's is `Copying` and was not copied before), plus the
   files passed to it; if it finds none, the build stops.
6. Licences that are missing: **done**.
   - the parts of sigrok (the four COPYING);
   - the subpackages of Wine Mono/Gecko (`%license`, SPDX: Mono's is Fedora's reading [A], Gecko MPL-2.0);
   - the Python packages of silik-pylab (the licence files of each dist-info, or of the source archive; if a package
     has none, the build stops);
   - the OFL of Cascadia Mono in `installer/product/` (the `LICENSE` of microsoft/cascadia-code at tag v2102.03, the
     font's version).

**Corresponding source**
7. SRPMs in all the build scripts, published in the same release. **Done** in the scripts (`build_rpms.sh`,
   `build_eda.sh`, `build_dev.sh`, `build_wine.sh`, `build_wine_addons.sh`) and in the workflows; the workflows have
   not been run (GitHub starts no jobs).
8. Stop deleting the old versions: move them to an archive release and keep them for 3 years. **Done**:
   `tools/release_keep.sh` moves them to `sources-archive` and never deletes anything from it. The binaries published
   before today have no SRPM: the first new build publishes their source.
9. `tools/fetch_base_sources.sh`: the SRPMs of the boot ISO's packages (from vault.almalinux.org), and the source of
   Wine Mono/Gecko. **Done**: the script (tried with test ISOs; vault.almalinux.org could not be tried from here),
   and the sources of Wine Mono and Wine Gecko go inside the SRPM of `silik-wine-addons`.
10. `/LEGAL.txt` in the ISO, with:
    - the components and their licences;
    - where the source and the written offer are;
    - the trademarks and the disclaimer of warranty.
11. The source has to be public: the repository, or a mirror of the specs and the sources.

**Texts, privacy and tests**
12. Correct "binary for binary" in the texts.
13. `docs/PRIVACY.md`: which servers are contacted (the mirrors of AlmaLinux and EPEL, docker.io and vault.centos.org
    for `silik eda`, NVIDIA if it is chosen, and the future SilikOS repository). `silik` sends no telemetry.
14. Tests: `test_licences.py` (valid SPDX, a licence in each RPM, an SRPM for each RPM). **In part**:
    `tests/test_sources.py` checks the form of the expressions, the macro that stops the build without a licence, and
    that each script makes the SRPM. It does not validate the identifiers against the SPDX list.
**Supply chain** (audit of 12/11/2026): **done**. Each downloaded source is checked: archives by sha256
(`eda/versions`, `dev/versions`, `wine/sources`), git trees by the commit, Wine by Julliard's signature, the boot ISO
by AlmaLinux's signed CHECKSUM (fingerprints pinned in the scripts).
15. With the vendors (Cadence, Vector, Altium, ST…), nominative use only: "can run X with your licence". Never
    "supported" or "certified", and no logo.

## 3. Business model

| Company | Model | Public price |
|---|---|---|
| Red Hat | RHEL Workstation, self-support | 197 $/year per system (reseller MSRP) |
| Canonical | Ubuntu Pro Desktop | 25 $/year (self-support), 300 $/year (24/7); free for up to 5 personal machines |
| CIQ | Rocky Linux from CIQ Pro | 350 / 600 / 825 $ per node and year |
| TuxCare | AlmaLinux support | By quote, or packs of hours |
| Slimbook, System76 | Hardware | KDE Slimbook VI: 1099 € at launch |
| Bluefin | Donations | — |
| IIC-OSIC-TOOLS (JKU) | Free EDA image, funded by the university | — |

Efabless closed in March 2025 for lack of funding: a service-only model, without recurring income, is
fragile.

**O1. EDA/bench set-up (service).**
- What it includes:
  - migrating a customer's flow to SilikOS: EDA boxes and FlexLM licences;
  - a Windows VM with USB passthrough;
  - a CAN bench.
- Infrastructure: little.
- Risks: it does not scale and depends on one person.
- Regulation: less exposed to the PLD and the CRA [A ⚖️].

**O2. SilikOS free as a channel for SilikStudio.**
- What is sold: the SilikStudio licence.
- What is needed: the signed public repository and SilikStudio's EULA.
- Effort: 2–4 weeks [A].

**O3. SilikOS Teams/Edu, a subscription per seat.**
- What it includes: a signed Pro channel with staged updates, a local mirror for the laboratory, fleet
  configuration and support with an SLA.
- Price: to be decided [A], taking Ubuntu Pro's prices as the reference.
- What is needed:
  - a signed repository, a mirror of the sources and a support process;
  - the CRA process: a point of contact, and notifying ENISA within 24 h if there is an exploited vulnerability.
- Effort: 2–3 months [A].

**O4. A certified laptop with a partner** (for example Slimbook, in València [A]).
- What is needed: a hardware test matrix, consumer warranty and logistics.
- Effort: very high; capital is needed.

**The agent's recommendation:**
1. Start with **O1 + O2**: SilikOS free and redistributable, with a trademark policy.
2. Build the signed and public repository, which serves O2 and O3.
3. Move to O3 when there are 2–3 customers of O1 and the CRA process is written.
4. O4 only after a verified real installation.

## 4. Questions for the owner

1. Licence of our own code: GPL-3.0-or-later or Apache-2.0? And the brand: all rights reserved, with unmodified
   redistribution?
2. A public repository, or a public mirror of the specs and the sources?
3. Where to host the package repository and the ISO, and who operates the servers (GDPR)?
4. Private customers, or only companies and universities?
5. Monetise SilikOS itself, or only the services and SilikStudio?
6. Is there a lawyer available (through UPC or the professional association)?
7. Does SilikStudio contact any server (licences, updates)?
8. Register the trademarks at the EUIPO?

Sources:
- https://www.gnu.org/licenses/gpl-2.0.html
- https://www.gnu.org/licenses/gpl-3.0.html
- https://www.gnu.org/licenses/gpl-faq.html
- https://www.mozilla.org/en-US/MPL/2.0/
- https://openfontlicense.org/
- https://almalinux.org/p/the-almalinux-os-trademark-usage-policy/
- https://almalinux.org/p/the-almalinux-os-licensing-policy/
- https://almalinux.org/blog/future-of-almalinux/
- https://www.redhat.com/en/about/trademark-guidelines-and-policies
- https://gjs.guide/extensions/review-guidelines/review-guidelines.html
- https://eur-lex.europa.eu/eli/dir/2024/2853
- https://eur-lex.europa.eu/eli/reg/2024/2847/oj
- https://eur-lex.europa.eu/eli/reg/2021/821/oj
- https://eur-lex.europa.eu/eli/dir/2019/770/oj
- https://www.enisa.europa.eu/sites/default/files/2026-07/ENISA_CRA_SRP_Factsheet_v1.0_0.pdf
- https://ubuntu.com/pricing/pro
- https://ciq.com/pricing
- https://tuxcare.com/almalinux-commercial-support/
- https://github.com/iic-jku/IIC-OSIC-TOOLS
- https://tinytapeout.com/news/efabless-shutsdown/
- https://docs.projectbluefin.io/donations
- https://www.linuxpromagazine.com/index.php/Online/News/New-KDE-Slimbook-Plasma-Available-for-Preorder
