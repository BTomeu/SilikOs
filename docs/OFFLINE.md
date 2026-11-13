# SilikOS sense xarxa

**Resum (català).** Les cases de disseny de xips, defensa i automoció tenen les xarxes d'enginyeria sense Internet.
SilikOS ja s'hi pot instal·lar i actualitzar:

- `silik mirror` fa una còpia local d'exactament el que necessita una instal·lació i les seves actualitzacions
  (1572 paquets, 2688 MB, mesurat el 13/11/2026), comprovant la signatura de cada paquet en entrar; es porta a dins
  amb un USB (`pack` / `unpack`, amb deltes setmanals petits), se serveix amb `serve` i cada màquina s'hi apunta amb
  `silik mirror use`. `use off` ho deixa tot com era, byte per byte.
- `tools/build_offline_iso.sh` fa una ISO que porta el mirall a dins i instal·la sense cap xarxa. Abans d'instal·lar
  res, el mateix mitjà es comprova (sha256 de cada fitxer i signatura de cada paquet).
- **Provat de veritat aquí**: tot el cicle en contenidors `almalinux:9` sense sortida a Internet (crear, verificar,
  servir, instal·lar 201 paquets, manipulacions rebutjades, actualitzar, tornar enrere), i una instal·lació completa
  d'una ISO reduïda en una màquina emulada sense targeta de xarxa. **No provat**: la ISO completa instal·lada en una
  màquina (cal KVM: el workflow `Offline ISO` està escrit i no s'ha executat), ni cap maquinari real.
- **Els paquets propis de SilikOS encara no van signats**: dins del mirall només els protegeix el sha256 del manifest.

---

## The weekly routine, in five commands

One machine outside (EL 9 or SilikOS, with Internet) holds the mirror; one machine inside the lab serves it.

| | Where | Command |
|---|---|---|
| 1 | outside | `sudo silik mirror update /srv/mirror --yes` — the newer versions, each one's signature checked on the way in |
| 2 | outside | `silik mirror pack /srv/mirror -o /run/media/$USER/USB/week.tar --since 2026-11-06` — what is new since last week's stick |
| 3 | inside, the mirror's host | `silik mirror unpack /run/media/$USER/USB/week.tar /srv/mirror` — unpacked, then every sha256 and signature again |
| 4 | inside, the mirror's host | `silik mirror serve /srv/mirror --bind 10.0.0.5` — only if it is not running already |
| 5 | inside, each workstation | `sudo dnf upgrade` — or nothing: SilikOS's daily update timer does it |

Once, before the first week:

```bash
# outside: the mirror (SilikOS's own packages come from build/repo, or from the folder /silikos of a SilikOS ISO)
sudo silik mirror create /srv/mirror --silikos build/repo        # dnf prints the size and asks; --yes to not be asked
silik mirror pack /srv/mirror -o /run/media/$USER/USB/silikos-mirror.tar
bash tools/build_offline_iso.sh /srv/mirror                      # the installer for the lab's machines

# inside: the mirror's host, then each workstation (installed from the offline ISO)
silik mirror unpack /run/media/$USER/USB/silikos-mirror.tar /srv/mirror
silik mirror serve /srv/mirror --bind 10.0.0.5 --port 8080
sudo silik mirror use http://10.0.0.5:8080                       # on each workstation; `silik mirror use off` undoes it
```

`rsync -a --exclude=.root /srv/mirror/ /run/media/$USER/USB/mirror/` is as good as `pack` when the stick's file
system keeps long file names; `silik mirror verify` on the other side is what matters either way.

## The commands

| Command | What it does |
|---|---|
| `silik mirror create DIR --silikos FOLDER [--arch x86_64\|aarch64] [--keep N] [--add NAME]... [--sign KEYID] [--yes]` | A new mirror of the SilikOS set: what `kickstart/silikos.ks` installs, plus what the installer adds by itself (boot loader for BIOS and UEFI, kernel, the three languages, LVM / encryption / RAID tools: `INSTALLER` in the plugin), resolved by `dnf install --downloadonly` in an empty root, as the installer resolves it. Run as root (dnf resolves an installation as root only) |
| `... create DIR --only-installed` | Instead of the SilikOS set: the packages installed on this machine. What no source offers any more is listed |
| `... create DIR --ks FILE [--bare]` | Another kickstart's sources and packages (`--bare`: without the installer's additions) |
| `silik mirror update DIR [--silikos FOLDER] [--add NAME] [--keep N] [--yes]` | The set resolved again; only what the mirror lacks is downloaded. The last N versions of each package stay (default 3), so `dnf downgrade` and `silik` rollbacks still find the one before |
| `silik mirror verify DIR [--json] [--key FILE]` | Every file's sha256 against the manifest, every package of the base against the base's key **of this machine** (`/etc/pki/rpm-gpg`), files the manifest does not list. Exit 0 only when everything holds; what cannot be checked (a key that is not here) is `?`, not ok |
| `silik mirror serve DIR --bind ADDRESS [--port 8080]` | Python's standard HTTP server, GET and HEAD only, no listings, dnf's working folder hidden. **No TLS, no authentication**: anyone who reaches the address reads the mirror (it holds nothing secret: public packages). What protects the content is each package's signature, checked by the machine that installs it |
| `sudo silik mirror use URL\|DIR [--key FILE]` | Writes `/etc/yum.repos.d/silikos-mirror.repo` (one section per repository of the mirror, `gpgcheck=1` against this machine's keys) and disables every other enabled repository with `dnf config-manager --set-disabled` (printed). Nothing is deleted; the files as they were are kept in `/etc/silikos/mirror/backup` |
| `sudo silik mirror use off` | `dnf config-manager --set-enabled` for what was disabled, the mirror's file removed, and each repository file compared with its copy of before: byte for byte the same, or put back from the copy (a file somebody edited meanwhile is left alone, and said) |
| `silik mirror status [URL\|DIR] [--json]` | Is a mirror in use; its generation, date, packages; whether what it serves is what its manifest says |
| `silik mirror pack DIR -o FILE [--since DATE \| --since-gen N]` / `unpack FILE DIR` | One tar (and its sha256 beside it). With `--since`, only the packages added since: it unpacks over a mirror that holds the rest, and is refused over one that does not |

Every command prints the commands it runs; `--dry-run` runs none of them.

A machine that is not SilikOS (a plain EL 9) first needs dnf's `config-manager`:
`dnf --disablerepo='*' --repofrompath=boot,http://10.0.0.5:8080/BaseOS --setopt=boot.gpgcheck=1 --setopt=boot.gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-AlmaLinux-9 install dnf-plugins-core`.

## Sizes (measured 13/11/2026, x86_64, AlmaLinux 9.8 + EPEL 9)

| What | Packages | Size | Time here |
|---|---|---|---|
| The mirror of the whole SilikOS set | 1572 (AppStream 979, BaseOS 543, epel 39, CRB 1, silikos 10) | 2688 MB of packages; 2.6 GB on disk without dnf's working folder | created in 122 with the machine to itself, 161 to 234 with an emulator running beside it s (download included, a data-centre connection) |
| Verifying it (sha256 + signatures) | | | 11.4 to 13.1 s |
| An update with nothing new upstream | 0 downloaded | | 8 to 9 s |
| `dnf install silik-tools silik-dev` from it, on a plain almalinux:9 | 201 | 431 MB | 25 to 28 s over HTTP, 22 to 23 s from a folder |
| The network installer ISO (for comparison) | | 1.5 GB | |
| The offline ISO, reduced set (`@core` + the installer's additions) | 400 | 2.5 GB (2 612 461 568 bytes) | built in 32 s |
| The offline ISO, whole set | 1572 | 4.0 GB (4 224 057 344 bytes) | built in 53 s (the network installer and the mirror's verification included); its media check passes and the mirror read back from it verifies; **not installed** |

A weekly delta is the packages the base and EPEL changed that week; it was not measured over a real week (the
mirror is one day old). The mechanism was measured on three versions of `tzdata` (below).

## What is checked, and when

| When | What | By |
|---|---|---|
| A package enters the mirror (`create`, `update`) | Its signature, with `rpmkeys --checksig` against a key ring that holds **only its own source's key** (AlmaLinux 9's for BaseOS / AppStream / CRB / extras, EPEL 9's for epel). The keys are this machine's (`/etc/pki/rpm-gpg`), and their fingerprints must be the two written in the plugin. An unsigned package says `digests OK` to rpmkeys: here it is refused (the word `signatures` must be there). One bad package refuses the whole generation and is deleted | `silik mirror` |
| Any time, and after every `unpack` | Every file's sha256 and size against the manifest; every base package's signature again; strangers | `silik mirror verify` |
| A machine starts using a mirror | The mirror's `repomd.xml` files are the ones its manifest lists (a stale or half-copied mirror is refused, exit 3) | `silik mirror use`, `status` |
| A package is installed from the mirror | Its checksum against the repository metadata, then its signature against the keys **on that machine** (`gpgcheck=1`), never against a key the mirror brings. The one exception, said when it happens: a base key the machine lacks (EPEL's, before `epel-release` is installed) is taken from the mirror **only if its fingerprint is the one written in the plugin** | dnf |
| The metadata (optional) | `create --sign KEYID` signs each `repomd.xml` and the manifest with the lab's own gpg key; `use URL --key FILE` then makes dnf check it (`repo_gpgcheck=1`). Without it, somebody who can write to the mirror can serve an older but validly signed set of packages (a freeze); they still cannot make a machine install a package the base did not sign | gpg, dnf |
| The offline ISO is built | The whole mirror is verified first; a mirror that fails makes no ISO. The base's boot ISO is checked by `tools/build_iso.sh` as before (AlmaLinux's signed CHECKSUM) | `tools/build_offline_iso.sh` |
| The offline ISO installs | The kickstart's `%pre --erroronfail` runs the same verification on the medium (`/run/install/repo/silik-mirror.py verify`) before any package is installed, with the installer image's own AlmaLinux key and the medium's EPEL key if it has the known fingerprint. This is needed: **anaconda 34 does not check package signatures** (its dnf runs with `gpgcheck = False`; `pyanaconda/modules/payloads/payload/dnf/dnf_manager.py`, read 13/11/2026 in anaconda-core-34.25.7.14). The network installer has the same property and no such check | the kickstart |

What is **not** protected:

- **SilikOS's own packages are not signed.** In the mirror and on the ISO they are held by the manifest's sha256 only
  (`gpgcheck=0` for the repository `silikos`). Whoever can rewrite the manifest can replace them. Signing them is a
  decision about a key and where it lives: the owner's.
- **The ISO's root of trust is the ISO.** The verification on the medium is run by a script that is on the medium:
  it catches a damaged or partly changed stick, not somebody who rewrites the whole image. Publish the ISO's sha256
  (`build/SilikOS-*-offline.iso.sha256`) by another way and compare, as for any installation medium.
- The metadata the mirror takes from the sources (`comps`, modules, advisories) is not signed upstream either: it is
  as trustworthy as the HTTPS connection it came over.
- `serve` has no TLS and no authentication (above). In a lab that needs either, any web server can serve the folder.

## How it is made

A mirror is a folder:

```
silik-mirror.json          the manifest: every file's sha256 and size, each package's generation and date,
                           the set, the sources, the keys' fingerprints, the history of generations
keys/                      the base's keys as the machine that made the mirror had them
BaseOS/ AppStream/ CRB/ epel/      Packages/*.rpm, repodata/ (createrepo_c's; the source's own groups, modules and
                                   advisories added: the installer's environments and `dnf upgrade --security` work)
silikos/                   SilikOS's own packages
.root/                     dnf's working folder (an empty installation root and its cache); not served, not packed
```

The closure is not computed by the plugin: `dnf install --downloadonly --installroot=DIR/.root` with only the
mirror's sources is asked for the set, as the installer asks its own dnf, and its cache is where the packages are
taken from. What the mirror already holds is linked into that cache first, so an update downloads only what is new.
An environment is `@^name` in a kickstart and `@name` on dnf's command line (EL 9.8's dnf refuses the first).

A machine that has packages the SilikOS set does not (seen here: the container image's `glibc-minimal-langpack`)
cannot upgrade past them from the mirror; `silik mirror update DIR --add NAME` puts them in the set.

## The offline ISO

`bash tools/build_offline_iso.sh [MIRROR_DIR [boot.iso]]` first runs `tools/build_iso.sh` (the network installer:
nothing of it is changed), then writes `build/SilikOS-VERSION-ARCH-offline.iso`: the same image with the mirror as
`/mirror`, the plugin as `/silik-mirror.py`, and the kickstart's sources rewritten:

```
url --url=file:///run/install/repo/mirror/BaseOS
repo --name=AppStream --baseurl=file:///run/install/repo/mirror/AppStream      (and CRB, epel, silikos)
```

(`/run/install/repo` is where the installer mounts the medium it booted from, `inst.stage2=hd:LABEL=...`; a URL that
is a repository and not an installation tree is taken as it is: anaconda 34's `payload/dnf/payload.py`.) The
`network` line is left out, a `%pre` verifies the medium, and a source the set takes nothing from (`extras`) is not
named. The disk is still the person's choice in the installer's screen: the script stops if its kickstart names one.
A package of the kickstart that the mirror lacks (SilikStudio from `build/extra`, say) stops the build with the
command that adds it.

The installed system's dnf still names the Internet's repositories. In the lab: `sudo silik mirror use URL`.

## What was run (13/11/2026)

In `almalinux:9` containers, with the real dnf 4.14, rpm 4.16 and createrepo_c 0.20 (`tests/offline/container_run.sh`;
its whole output: `tests/offline/run-2026-11-13.log`):

1. **The mirror of the whole set**: 1572 packages, 2688.2 MB, each signature checked on the way in (1523 against
   AlmaLinux 9's key, 39 against EPEL 9's; SilikOS's 10 are not signed), the sources' groups, modules and advisories
   carried. `verify` in a container with no network device: 1627 files, all as the manifest and the keys say.
2. **A server and a client on an internal docker network** (`docker network create --internal`; the client cannot
   resolve `repo.almalinux.org` nor reach 1.1.1.1). The mirror answers: manifest 200, dnf's working folder 404, a
   listing 404, a PUT 501. The client is a plain `almalinux:9`: `silik mirror use URL` disabled its three enabled
   repositories and took EPEL's key from the mirror (fingerprint as written); `dnf install silik-tools silik-dev`
   installed **201 packages** (126 AppStream, 57 BaseOS, 16 EPEL, 2 SilikOS), 431 MB, in 25 to 28 s. `use off`: the
   11 repository files byte for byte as before (`sha256sum -c`).
3. **From a folder, in a container started with `--network none`** (its only device: `lo`): the same 201 packages,
   22 to 23 s.
4. **Tampering, each refused.** One byte of a package: `verify` exit 1 (its sha256 and its signature), dnf "checksum
   doesn't match", not installed. The same with `createrepo_c` run again and the manifest rewritten, so that the
   mirror agrees with itself: `verify` still exit 1 (the signature), dnf **"GPG check FAILED"**, not installed. One
   byte of `repomd.xml`: `verify` exit 1, `status` says so, `use` exit 3, dnf pointed at it by hand exit 1.
5. **An update.** A newer `silik-tools` (release 2, built in a copy): `update` in 8 to 9 s, nothing of the base
   downloaded again. The client's `dnf upgrade` first failed: the container image has `glibc-minimal-langpack`,
   which the SilikOS set does not (above); after `update --add glibc-minimal-langpack` it upgraded 6 packages. The
   installed `silik` (the package now carries the plugin) answers `silik mirror status`; `dnf updateinfo` sees the
   mirror's advisories; `dnf downgrade silik-tools` went back to release 1 (the older version stays in the mirror).
6. **With `--network none` throughout**, a mirror of three real, signed versions of `tzdata` from a stand-in source:
   `update` twice with `--keep 2` (the oldest removed at the third), metadata signed with a gpg key made there;
   `pack` of generation 2 (1 085 440 bytes), unpacked and verified; the delta since generation 2 (573 440 bytes,
   1 of 2 packages), unpacked over it and verified; the delta over nothing: exit 3. A client with `use DIR --key`
   (`repo_gpgcheck=1`) saw both versions and downgraded. The newest version removed and the mirror made to agree
   with itself (a freeze): `verify --key` fails on the metadata signature and dnf refuses the repository. A source
   with an unsigned package: `create` exit 3, the package nowhere in the mirror.

The log's first line names the commit the tree was based on (bdb1eee): it ran before this work was committed.

In an emulated machine (QEMU without KVM, **no network device**: `-nic none`), the offline ISO of the reduced set:

(running when this was written: see the next commit)

## Not verified

- **The whole-set offline ISO installed in a machine.** It needs KVM. `.github/workflows/offline.yml` (started by
  hand) builds the mirror and the ISO on `ubuntu-24.04` and installs it with the CI's own `tests/install/run.sh` in a
  machine without a network device (`tests/install/offline.sh`): written, not run.
- Real hardware, a real USB stick, a real lab. The installer's screens with this ISO (graphical mode: the emulated
  test was in text mode).
- The list of what the installer adds by itself (`INSTALLER`) beyond the boot loader, which was read in anaconda's
  source [A]: a disk layout or a language that asks for a package the mirror lacks would stop the installation at
  its dependency check, before anything is written. `--add NAME` is the remedy.
- aarch64: `--arch aarch64` passes `--forcearch` to dnf and the ARM sources; not run.
- `--only-installed` on a real SilikOS workstation (run with stand-ins only).
- A weekly delta's real size, and `metadata_expire=1h` on machines that stay on for weeks.
