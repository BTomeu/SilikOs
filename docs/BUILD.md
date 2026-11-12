# Building

| Step | Command | Needs |
|---|---|---|
| Packages + repository | `bash tools/build_rpms.sh` (and their source packages in `build/srpm/`) | `rpmbuild`, `createrepo_c` (any Linux; nothing is compiled) |
| Tests | `python3 -m unittest discover -s tests` | Python >= 3.9 |
| Dependency names | `bash tools/check_deps.sh` | an EL9 system with its repositories and EPEL |
| Installer ISO | `bash tools/build_iso.sh [AlmaLinux-9-…-boot.iso]` (the base ISO is checked first: its sha256 against AlmaLinux's signed `CHECKSUM`) | `xorriso`, `mtools`, `cpio`, `curl`, `gpg`, `implantisomd5` (isomd5sum), repo.almalinux.org |
| Installer ISO for ARM | `SILIK_ARCH=aarch64 bash tools/build_iso.sh` (AlmaLinux's aarch64 boot ISO: UEFI only) | the same |
| The base's sources | `bash tools/fetch_base_sources.sh [--list] [--limit N]`: the source packages of the boot ISO's installer image, from vault.almalinux.org, each checked by AlmaLinux's signature | `xorriso`, `unsquashfs`, `rpm`, `gpg`; several GB |
| Brand rasters (committed) | `bash tools/gen_brand.sh` | `rsvg-convert`, the Cascadia Mono font |

The ISO is the base's boot image relabelled `SilikOS-9-x-x86_64` (`SilikOS-9-x-aarch64`: its kickstart copy takes the
aarch64 package sources and leaves out the x86_64 kernel argument `vsyscall=xonly`), with `kickstart/silikos.ks`, the repository
`build/repo` as `/silikos`, `inst.ks=` added to the boot entries, the menus renamed, and `images/product.img`
(`installer/product/` + `.buildstamp`): the installer unpacks it over its own root, which gives it the SilikOS name,
its configuration (`etc/anaconda/product.d/silikos.conf`, based on the base product's) and the sidebar / top bar. The installation downloads the base system from the AlmaLinux and EPEL
repositories, so the machine needs a network (cable or a phone's USB tether if the Wi-Fi card is not recognised).

## Installing

With the ISO (write it to a USB stick): language, keyboard and time zone, then **Installation Destination** (choose the
disk and how to use it: nothing is preselected or erased), **User Creation**, Begin Installation. A cable or a phone's
USB tether connects by itself; with Wi-Fi only, join the network in **Network & Host Name** and then open
**Installation Source** once more. About 750 packages (1.2 GB) are downloaded.

Without the ISO, on an installed AlmaLinux / Rocky / RHEL 9 Workstation:

```bash
git clone https://github.com/BTomeu/silikos && bash silikos/tools/install_on_alma.sh
```

Layout: `packages/<name>/<name>.spec` and its `files/` (the spec installs straight from there), `kickstart/`,
`tools/`, `tests/`, `docs/`.

## Sources

Every source a build downloads is checked before it is used, and the build stops on anything else: a release
archive by the sha256 written beside it (`eda/versions`, `dev/versions`, `wine/sources`, a recipe's `# archive:`
lines, `dev/pylab-requirements.txt`), a git tree by the commit its tag must name (`eda/versions`, `dev/versions`, a
recipe's `# source:` lines), Wine's archive also by Alexandre Julliard's signature, the base's boot ISO by AlmaLinux's
signed `CHECKSUM` file (the two keys' fingerprints are written in `tools/build_wine.sh` and `tools/build_iso.sh`).
Every build also makes the source package of what it built (`build/srpm/`: upstream's sources as they were checked,
the recipe with its version written in, `eda/common.inc`); it rebuilds by itself with `rpmbuild --rebuild`. The
workflows keep it in the same release as the binary; a package a newer build replaces moves, with its source package,
to the release `sources-archive` (`tools/release_keep.sh`), from which nothing is deleted.

