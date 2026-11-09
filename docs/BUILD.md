# Building

| Step | Command | Needs |
|---|---|---|
| Packages + repository | `bash tools/build_rpms.sh` | `rpmbuild`, `createrepo_c` (any Linux; nothing is compiled) |
| Tests | `python3 -m unittest discover -s tests` | Python >= 3.9 |
| Dependency names | `bash tools/check_deps.sh` | an EL9 system with its repositories and EPEL |
| Installer ISO | `bash tools/build_iso.sh [AlmaLinux-9-…-boot.iso]` | `xorriso`, `mtools`, `curl`, repo.almalinux.org |

The ISO is the AlmaLinux 9 boot image with `kickstart/silikos.ks`, the repository `build/repo` as `/silikos`, and
`inst.ks=` added to the boot entries. The installation downloads the base system from the AlmaLinux and EPEL
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
