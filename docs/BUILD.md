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

To try the packages on an existing AlmaLinux / Rocky / RHEL 9 without the ISO:

```bash
sudo dnf install epel-release && sudo dnf config-manager --set-enabled crb
sudo dnf install ./build/repo/*.rpm
```

Layout: `packages/<name>/<name>.spec` and its `files/` (the spec installs straight from there), `kickstart/`,
`tools/`, `tests/`, `docs/`.
