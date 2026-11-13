# silik env — the tools of a project, pinned (13/11/2026)

## Resum (català)

"Al meu ordinador compila" és el cost diari de qualsevol equip de firmware o de xips, i les normes de seguretat
funcional (ISO 26262-8 clàusula 11, IEC 61508-3 [A: citades per la seva estructura, no pel text]) demanen saber
exactament quines versions de les eines han construït una release. `silik env` ho dona amb **un fitxer i una ordre**,
fet amb el que la base ja porta (podman, dnf, els repositoris signats), sense cap gestor de paquets nou:

- `silik.env` (INI, a l'arrel del projecte) diu quines eines vol el projecte.
- `silik env lock` el resol a `silik.env.lock` (JSON ordenat): la imatge base **per digest**, cada paquet com a NEVRA
  complet amb el seu repositori i el **sha256** que en dona la metadada del repositori, els paquets de Python només si
  el fitxer ho demana (i llavors amb hash), les variables d'entorn i el sha256 del mateix `silik.env`.
- `silik env build` fa la imatge exactament del lock (comprova el sha256 de cada paquet **abans** d'instal·lar res i
  verifica les signatures); `silik env run -- ORDRE` hi executa una ordre amb el projecte al mateix camí i **sense
  xarxa**; `silik env check` diu si la imatge és la del lock (surt amb 1 si no); `silik env export --ci github|gitlab`
  escriu un job de CI que construeix amb el mateix lock, amb ordres normals de docker.

Executat de veritat el 13/11/2026 (amb docker fent de podman: en aquesta màquina no hi ha podman): un projecte CMake
per a Cortex-M4 resolt, construït **dues vegades i en cinc llocs** (dues execucions, un altre camí, un altre usuari,
les ordres del job de GitHub i el guió del job de GitLab) amb el **mateix hash de l'ELF**; sense `SOURCE_DATE_EPOCH`
el hash canvia a cada construcció. Un lock contra un arbre congelat d'EPEL de fa dos anys es resol igual dues vegades;
el mateix paquet ja no és al repositori viu i la construcció falla dient-ho.

Límits, dits clars: fixa les eines d'espai d'usuari, **no el kernel**, ni les eines de fabricant instal·lades fora de
rpm (es munten només de lectura i se'n registra la versió amb una ordre de l'usuari); els repositoris vius perden les
versions antigues (cal un arbre congelat: el vault d'AlmaLinux, l'arxiu d'EPEL, o un mirall propi); podman de veritat,
el vault (bloquejat des d'aquesta sessió), els dispositius USB/sèrie/CAN i ARM **no s'han pogut executar aquí**.

## What it is

One file at the project's root, one command, and every person and every CI job of the project builds with the same
tool binaries. Nothing new is installed for it: the image is made by `podman`, the versions are chosen by `dnf`'s own
resolver, the packages come from the signed repositories of the base (AlmaLinux 9, EPEL 9) and are checked against
the hashes those repositories publish.

```
silik env init                     a starter silik.env for the project found here
silik env lock [--pull] [--json]   silik.env -> silik.env.lock (exact versions, hashes, the base image by digest)
silik env build [--force]          the image of the lock (once: an image with the lock's hash is not built again)
silik env run [--net] -- CMD...    CMD in the environment: the project at the same path, your uid, no network
silik env enter [--net]            a shell there
silik env check [--all] [--json]   is the image the lock's? are the tools inside at the lock's versions? exit 1 on drift
silik env export --ci github|gitlab | --containerfile
silik env list [--json]            the projects locked on this machine
```

Every command takes `-C DIR` (the project's folder; default: here, or the nearest folder above that holds
`silik.env`), prints the commands it runs and runs nothing under `--dry-run`, like the rest of `silik`. It is a
plugin of `silik` (`plugins/env.py`, `docs/PLUGINS.md`): it costs the other commands nothing. In the COMMAND bar:
`env/list` and `env/check` (every project locked on this machine; the bar does not know which project you are in).

## silik.env

An INI file (Python 3.9, the base's, has no TOML reader). Only `[packages]` is needed.

```ini
[env]
# the image's name (default: the folder's); the base image (the lock pins its digest); the command of the CI job
name = fw
base = docker.io/library/almalinux:9
build = cmake -B build && cmake --build build

[repos]
# a frozen AlmaLinux tree (BaseOS, AppStream, CRB, extras under it); without it: the live repositories
snapshot = https://vault.almalinux.org/9.6
# EPEL: a frozen tree, or yes (live), or no (the default). CRB is on when EPEL is, unless `crb = no`
epel = https://dl.fedoraproject.org/pub/archive/epel/9.6
# any other repository: NAME = URL, or a folder of this machine (with repodata/); its signing key, if it has one
# (without one, the lock's sha256 is all that holds its packages)
silikos = rpms
silikos.gpgkey = https://example.org/KEY

[packages]
# a name: the newest the repositories have on the day of the lock
cmake
# NAME = VERSION (any release), NAME = VERSION-RELEASE; both take * as a glob
make = 4.3
gcc = 11.5.0-5.el9_5

[silikos]
# SilikOS's own tool packages (OpenOCD, dfu-util, Yosys, KiCad...): from the repository named `silikos`, and only it
openocd = 0.12.0

[pip]
# only if the project needs Python packages that are not rpm (python3-pip must be in [packages])
requirements = requirements.txt

[environment]
# given to every command; LANG, TZ and SOURCE_DATE_EPOCH are set by the lock
CFLAGS = -O2

[devices]
# debug probes and DFU; /dev/ttyUSB* and /dev/ttyACM*; X11 (a waveform viewer)
usb = yes
serial = yes
display = yes

[mounts]
# a vendor's tools, installed outside rpm: mounted read-only
/opt/vendor = ro

[versions]
# how its version is read: recorded in the lock, compared by `silik env check`
vendor-tool = cat /opt/vendor/tool/VERSION
```

A section or key it does not know stops it (a misspelt `[package]` is not skipped silently). Comments are whole lines.
A base that is not AlmaLinux names its own repositories: `snapshot = none`, then `NAME = URL` for each (not run).

`silik env init` writes a starter by what it finds in the folder (two levels deep): CMake files that name
`arm-none-eabi` (firmware), `west.yml` / `.west` / `find_package(Zephyr` (a Zephyr workspace), Verilog / VHDL sources
with a Makefile, a `.kicad_pro` file, or just a Makefile / CMakeLists.txt. **It never guesses a version**: each tool of
that kind of project that `rpm` finds on this system is listed at its installed version; the others are comment
lines to uncomment (without a version: the lock then takes what the repositories have).

## The lock

`silik env lock` asks dnf's own resolver (python3-dnf, the library `dnf install` is) in a **throw-away container of the
base image**: `podman run --rm -i --network host BASE@sha256:... python3 - REQUEST`. The command is printed, with the
hosts it will contact before it does. Weak dependencies are off; nothing is installed and no package is downloaded:
the answer is what a transaction would install, read from the repositories' metadata. `silik.env.lock` then holds:

| Key | What |
|---|---|
| `base.ref` | the base image **by digest** (`docker.io/library/almalinux@sha256:...`): the local image's, or after `podman pull` (`--pull` asks the registry again) |
| `base.packages` | the packages the base image already has (so the lock is the whole list of what is in the image) |
| `packages[]` | every package to install, dependencies included: `nevra`, `repo`, `sha256` (as the repository's metadata gives it), `size`, `location`, `license`, `sourcerpm` |
| `repos[]` | each repository's `baseurl`, whether it is a frozen tree, its signing key and **the key's sha256** |
| `pip[]` | only with `[pip]`: each file pip would install, `name`, `version`, `sha256` |
| `environment` | `LANG=C.UTF-8`, `TZ=UTC`, `SOURCE_DATE_EPOCH` (below), then the file's own |
| `versions` | each `[versions]` command and what it printed (run in the base image with the mounts) |
| `inputs` | the sha256 of `silik.env` (and of the requirements file): `check` says when they changed after the lock |
| `image` | the sha256 of what the image is made of (base, repositories, packages, pip): the image's tag and label |

It is sorted JSON with no date in it: **locking twice against the same trees writes the same bytes** (run: below).
A lock is of one architecture (its packages are): on an aarch64 machine `silik env lock` writes an aarch64 lock, and a
lock of another architecture is refused with that reason.

`[pip]`: Python packages come from the system's rpm unless the file asks. Then pip itself resolves the requirements
file in the image of the lock's rpm part (its Python, its pip; that image is built for it), every file is hashed, and
the image installs them with `pip install --no-deps --require-hashes`: pip refuses a file whose hash is not the lock's.

### Old versions vanish: frozen trees

What was measured on 13/11/2026, with dnf in an `almalinux:9` container:

- **AlmaLinux keeps the older builds of a minor release while it is the current one**: in `9.8/BaseOS` 523 of 1190
  package names had more than one version (kernel-core: 46). When the next minor is out the tree moves: the file
  `README.txt` left at `repo.almalinux.org/almalinux/9.7/` says "go to https://vault.almalinux.org/9.7/ for packages",
  and `repo.almalinux.org/vault/9.6/BaseOS/x86_64/os/repodata/repomd.xml` answers 301 to
  `https://vault.almalinux.org/9.6/BaseOS/x86_64/os/repodata/repomd.xml`. So the vault's layout is the live one's:
  `https://vault.almalinux.org/<minor>/<BaseOS|AppStream|CRB|extras>/<arch>/os/`.
- **EPEL keeps one build of each package**: 0 of 26722 names had two versions. Its archives
  (`dl.fedoraproject.org/pub/archive/epel/9.1` … `9.8`, and dated ones such as `9.4-2024-11-12`) are EPEL as it was at
  the end of a minor [A: the meaning of the folders' names]. Of the 22499 names in the `9.4-2024-11-12` archive, 8841
  are at another version in live EPEL and 1845 are gone from it; of the 26637 in the `9.8` archive, three days old,
  533 already are.

So a lock made against live repositories builds today and stops building some day: at the next minor release for
AlmaLinux's packages, at the next update of the package for EPEL's. `silik env lock` says so each time it locks
against a live repository, with the frozen trees of the base's own minor release. For a lock that stays buildable:

```ini
[env]
base = docker.io/library/almalinux:9.6      # the image of that minor (a 9.6 tree on a 9.8 image would mix them)
[repos]
snapshot = https://vault.almalinux.org/9.6
epel = https://dl.fedoraproject.org/pub/archive/epel/9.6
```

An intermediate EPEL build (one that was replaced before the minor ended) is in no archive: for those, and for a
vault that could go away, the answer is a mirror of your own (`snapshot` and `epel` take any URL of the same layout).
When a package of the lock is gone, `silik env build` fails, repeats dnf's own line that names it, and names the
frozen trees to lock against.

## The image

`silik env build` writes one Containerfile from the lock alone (`~/.cache/silikos/env/<hash>/Containerfile`;
`silik env export --containerfile` prints it) and runs `podman build --network host` on it. Inside:

1. `FROM` the base **by digest**.
2. The lock's repositories go into a repo file of their own (`--setopt=reposdir=`): the image's own
   `/etc/yum.repos.d` is not touched.
3. Each signing key is compared with the sha256 the lock holds, then imported (AlmaLinux's is in the base image;
   EPEL's is fetched).
4. `dnf install --downloadonly` of the exact NEVRAs, `--setopt=install_weak_deps=False`.
5. `sha256sum -c` of every downloaded file against the lock, and the count of files: **before anything is installed**
   (no scriptlet of a file that is not the lock's ever runs).
6. `dnf install` of those files with `localpkg_gpgcheck=1`: rpm verifies each signature against the imported keys.
   (Run on 13/11/2026: without EPEL's key dnf refuses an EPEL package, "Public key ... is not installed, GPG check
   FAILED"; with one byte changed, "GPG check FAILED".) Packages of a repository without a key are installed on the
   lock's sha256 alone, and the build says how many.
7. With `[pip]`: `pip install --no-deps --require-hashes`.

The image carries the label `silik.env.image=<hash>`; an image with that label is not built again. The environment
variables, mounts and devices are not in the image: they are given when a command runs, so changing them builds
nothing.

## Running in it

`silik env run -- CMD` (and `enter`) is `podman run --rm` with:

| | |
|---|---|
| the project | mounted at **the same path** as outside, the working folder the same (paths in build outputs and error messages match) |
| your uid | rootless podman: `--userns keep-id`; where the runtime is docker or runs as root: `--user UID:GID`. What the build writes is yours |
| **no network** | `--network none`. A build that cannot reach the network is a build whose inputs are all in the lock. `--net` gives the host's network |
| the environment | the lock's (`SOURCE_DATE_EPOCH`, `LANG`, `TZ`, the file's own), `HOME=/tmp`, the host name `silik-env` |
| your home folder | **not** mounted (the EDA boxes of `silik eda` mount it; here a build must not depend on what is in it) |
| `[mounts]` | read-only, at the same paths |
| USB (`usb = yes`) | `/dev/bus/usb` (debug probes, DFU: libusb opens the devices there), with your own rights on the nodes: SilikOS's udev rules give the person at the screen the probes. A device plugged in later appears there [A] |
| serial (`serial = yes`) | the `/dev/ttyUSB*` and `/dev/ttyACM*` there are **when the command starts** (a port plugged in later is not inside) |
| CAN | a CAN interface is a network interface: it is inside only with `--net` (the host's network), like in the boxes |
| `display = yes` | `DISPLAY`, the X11 socket and `XAUTHORITY`, as the boxes |
| not passed | the session bus, sound, the GPU, `/dev` otherwise, other folders of the machine |

Without `[devices]` nothing of the bench is passed.

## SOURCE_DATE_EPOCH and bit-for-bit builds

Same tools do not make the same bytes if the build writes down when or where it ran. `SOURCE_DATE_EPOCH` is the
convention (reproducible-builds.org) by which tools that embed a date take a given instant instead of the clock: GCC
(7 and later) for `__DATE__` and `__TIME__`, CMake's `string(TIMESTAMP)`, and others. The lock sets it to **the newest
build date among the packages of the image**: nothing in the image is newer, and it is a function of the lock alone
(the same lock, the same date). `[environment] SOURCE_DATE_EPOCH = ...` sets another (a release's commit date).

The rest is the project's own job: no absolute paths in the outputs (`-ffile-prefix-map`), no unordered file lists,
no random names. The example below has `__DATE__` in it on purpose.

## A worked example (run on 13/11/2026)

The machine: 4 CPUs, Ubuntu 24.04 host, Docker 29.9.2 with BuildKit **standing in for podman** (the `podman` of this
machine is a name of docker; `silik env` sees that and uses docker's flags), behind a proxy (below).

The project: SilikOS's own Cortex-M4F trial program (`packages/silik-dev/files`: `main.c`, `startup.c`, `cortex-m.ld`:
flash at 0x08000000, RAM at 0x20000000, an STM32's map; no C library) as a CMake project, plus a file with
`"built " __DATE__ " " __TIME__`. Its compiler here is EPEL's `gcc-arm-linux-gnu` used freestanding
(`-mcpu=cortex-m4 -mthumb -ffreestanding -nostdlib`), **not** `arm-none-eabi-gcc-cs` with newlib: those are 1.4 GB
installed (measured from the repositories' metadata) and the machine had about 3 GB free. The arm-none-eabi starter
was locked (11 packages, 248.8 MB to download) and **not built**. The project is in the repository: `tests/env/fw`
(`CMakeLists.txt`, `build_info.c`, `b.sh`, `silik.env`, the lock of that day) plus those three files of `silik-dev`.

```ini
[env]
name = fw
build = cmake --fresh -S . -B build && cmake --build build --clean-first && sha256sum build/fw.elf
[repos]
snapshot = https://repo.almalinux.org/almalinux/9.8
epel = https://dl.fedoraproject.org/pub/archive/epel/9.8
[packages]
cmake
make
gcc-arm-linux-gnu
```

| Step | Result |
|---|---|
| `silik env lock` | 34 to 43 s over the runs (the repositories' metadata is downloaded each time). 13 packages on the base's 158: cmake 3.31.8-3.el9, make 4.3-8.el9, gcc-arm-linux-gnu 12.1.1-1.el9 and their dependencies, 53.8 MB. The lock: 14 kB |
| `silik env lock` again | the file is byte for byte the same |
| `silik env build` | 58 s; `silik env build` again: "already built" |
| `silik env run -- ./b.sh`, twice | `231731f08f2d6bd10b39b8b255022932e860d7bb965f355119fede7a1a13c4d7  build/fw.elf` both times; the ELF says "built Oct 26 2026 11:13:51" (the lock's `SOURCE_DATE_EPOCH=1793013231`) |
| the same with `env -u SOURCE_DATE_EPOCH`, twice | two other hashes (`09f98368…`, `c9336bf1…`): the compiler's clock is in the file |
| the project copied to another folder | `231731f0…` (the CMake file has `-ffile-prefix-map`) |
| as uid 1000 (`--user 1000:1000`) | `231731f0…`; `build/fw.elf` belongs to 1000 |
| inside | uid of the caller, only `lo` as network, `curl` cannot resolve a host, the image's `/etc/yum.repos.d` as the base's |
| `silik env check` | 6 rows ok (the three tools at the lock's versions, 171 of 171 packages), exit 0 |
| `silik env export --ci github`: its commands run here in order (the image built again with `--no-cache`) | `231731f0…` |
| `silik env export --ci gitlab`: its script run in the base image, the project at `/builds/group/fw` | `231731f0…` |

The same ELF from five places. What that does **not** show: another machine, another kernel, podman.

Other real runs of that day:

- **A frozen tree two years old.** `epel = https://dl.fedoraproject.org/pub/archive/epel/9.4-2024-11-12` with
  `[packages] tio`: locks `tio-3.7-1.el9` (sha256 `1d30f9b0…`), twice the same file; builds; `tio --version` inside
  says 3.7. The same `silik.env` with `epel = yes` locks `tio-3.9-1.el9`. The 3.7 lock pointed at live EPEL does not
  build: `No match for argument: tio-3.7-1.el9.x86_64`, then the line that names the frozen trees; exit 1.
- **A hash that is not the file's**: the build stops at step 5 ("tio-3.7-1.el9.x86_64.rpm: FAILED … what dnf
  downloaded is not what the lock says"), nothing installed. A lock edited by hand is refused before anything runs.
- **A folder as a repository, pip, a vendor's tool**: `silikos = rpms` (two of our own unsigned RPMs with repodata),
  `silik-tools = 0.6.14`, `python3-pip`, `requirements.txt` with `intelhex==2.3.0`, a folder mounted read-only with a
  `VERSION` file. Locked (the wheel's sha256 in the lock), built (the build says "packages from a repository without
  a key: 1"), `silik --version` and `import intelhex` work inside, the mount refuses a write, `check` is 7 rows ok;
  after the vendor's `VERSION` file is changed, `check` says drift on that row and exits 1.
- `silik env init` on an EL 9 system that has cmake and make, in a tree whose CMake names `arm-none-eabi`: lists
  `cmake = 3.31.8` and `make = 4.3`, the rest as comments.
- `tests/test_env.py`'s `Real` class (`SILIK_ENV_REAL=1`): lock, lock again, build, run without network, check, against
  the live repositories: passes in 106 s.

### The base's vault itself was not reached

`vault.almalinux.org` is refused by this session's proxy (403), so no lock was resolved against the vault of a
released minor here. What stands in for it in the runs above: the tree of the current minor by its number
(`repo.almalinux.org/almalinux/9.8`: the same layout, and where 9.8 is served until 9.9 is out) and EPEL's archives.
Where to run it (any machine with podman and a route to the vault):

```bash
mkdir t && cd t && printf '[env]\nbase = docker.io/library/almalinux:9.6\n[repos]\nsnapshot = https://vault.almalinux.org/9.6\n[packages]\nmake\n' > silik.env
silik env lock && cp silik.env.lock a && silik env lock && cmp silik.env.lock a && silik env build && silik env check
```

## Behind a proxy

A site whose proxy re-signs TLS: `SILIK_ENV_CA=/path/to/ca.pem` and the usual `https_proxy`. They reach the
containers that lock and build (the proxy variables by name: their values are not printed; the CA as a read-only
mount or a build secret, used through `dnf --setopt=sslcacert=`), and **never the lock or the image**. All the real
runs above went that way.

## CI

`silik env export --ci github` prints a workflow with plain commands, no action or tool of ours: it checks that
`silik.env.lock` is the one the job was made from (`sha256sum -c`), `docker build`s the Containerfile it carries, and
runs `[env] build` with `docker run --network none`. `--ci gitlab` prints a job whose own container is the base image
by digest and whose `before_script` is the same install script (a shared GitLab runner gives no container inside a
container). After `silik env lock`, export again. Both were run here command by command; neither on a real runner.

## What the lock is for other tools

`silik.env.lock` is the list of everything in the image: `base.packages` and `packages[]` with name, version,
licence, source package and sha256. A software bill of materials can be made from it without asking the image; no
command of `silik env` does it (the hook is the file).

## How it differs from the alternatives, honestly

| | What it pins | Where it is better than `silik env` | Where `silik env` fits better |
|---|---|---|---|
| **Nix** (nix-eda, LibreLane's flake) | the *sources* of every tool and of everything they are built from | it can rebuild from source when a binary is gone, so it does not depend on a repository keeping old builds; many versions of a tool side by side; finer than a package set; also macOS | no second package manager and store to learn and maintain; the binaries are the ones EL 9 ships and vendors test against; an rpm from a vendor or from SilikOS goes in as it is |
| **IIC-OSIC-TOOLS** | one large container, by its tag | everything is already built and tried together, PDKs included; x86_64 and ARM images; nothing to resolve | per project, small (the base plus what the project names), EL 9 not Ubuntu, each package's hash in a file that diffs |
| **a Dockerfile with `dnf install`** | nothing: the tag moves, the packages are the day's | simpler | the base by digest, every package by hash, a check for drift, no network in the build |
| **toolbox / distrobox** | nothing (a convenience) | the whole desktop inside | pinned, and nothing of the home folder inside |

`silik env` pins **binaries of signed repositories**. It cannot rebuild a tool, it is one architecture per lock, and
its long-term reproducibility is that of the trees it names (the vault, EPEL's archives, your mirror).

## Limits

- It pins the user-space tools. **Not the kernel** (a container runs on the host's), not the CPU, not firmware of a
  probe.
- Tools installed outside rpm (a vendor's IDE or compiler, a licence server) are not in the lock: `[mounts]` shows
  them read-only and `[versions]` records what a command of yours says about them. Their bytes are pinned only if
  that command hashes them (`sha256sum /opt/vendor/bin/tool`).
- The registry must keep the base image's digest; Docker Hub keeps old digests of `almalinux` [A].
- Trust: the metadata of AlmaLinux's and EPEL's repositories is not signed (their packages are). At lock time the
  resolver trusts HTTPS to the repository's host; at build time every package must match the lock's sha256 **and**
  carry a valid signature of a key whose hash is in the lock. The lock is a file of the project: review its diff.
- Bit-for-bit builds also need the project's own build to be deterministic (above).
- `silik.env` is the project's file: it names folders of the machine to mount (read-only), devices to pass and
  commands to run in the container (`[versions]`). Read it before `silik env` in a project you do not know; every
  mount is in the `$ podman run ...` line each command prints. The container has no network unless you give `--net`.
- The resolver downloads the repositories' metadata at every lock (about 120 MB with EPEL): 40 s here.

## Not verified here

- **podman itself**: rootless `--userns keep-id`, `podman build` with `--secret` and `--build-context`, its proxy
  handling, the digest it reports for an image (`.Digest` against `RepoDigests`). Everything above ran on Docker 29.9.2.
  `SILIK_ENV_REAL=1 python3 -m unittest discover -s tests -p test_env.py` on a SilikOS installation runs it.
- **The vault of a released minor** (the host is refused from this session): the command above.
- **Devices**: no probe, serial adapter or CAN interface here; nothing was flashed from inside. The flags are in the
  tests; whether rootless podman opens an ST-LINK through `/dev/bus/usb` needs a board [A].
- **ARM (aarch64)**: not run. The same code; EPEL 9 has the compilers for aarch64 (`docs/HARDWARE.md`).
- SELinux enforcing on the host (`--security-opt label=disable` is passed, as the boxes do), X11 from inside.
- The exported jobs on GitHub's and GitLab's runners.
- An `arm-none-eabi-gcc` + newlib build (locked, not built: disk).
