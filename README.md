# SilikOS (by SilikVolt)

An engineering workstation system on an Enterprise Linux 9 base (AlmaLinux's packages and kernel, unchanged, so that
EDA tools install and run), with the SilikVolt desktop on top, boxes for older EDA releases, and a layer for Windows
programs. It carries the base's version (SilikOS 9.8) and says SilikOS wherever a person looks; programs still read
an EL9 system. It is a try: `docs/STATUS.md` says what has been run and what has not.

| Part | What it is | Where |
|---|---|---|
| Base | AlmaLinux 9 packages and kernel, from its own repositories | `kickstart/silikos.ks` |
| Desktop | GNOME Shell on X11 laid out as the Silik interface (command line, text rail, status bar; one ink on paper); the **COMMAND** bar on Super+Space | `packages/silikos-desktop`, `packages/silik-command` |
| `silik` | one command behind every action; prints what it runs; `--dry-run` | `packages/silik-tools` |
| EDA | what Cadence / Synopsys tools ask of EL9, and EL6 / EL7 / EL8 boxes (`silik eda`) | `packages/silik-eda-compat`, `docs/EDA.md` |
| Windows | Wine prefixes; a Windows virtual machine whose programs open as windows here (`silik win`) | `packages/silik-win`, `docs/WINDOWS.md` |
| Name and look | os-release display names, boot menu, boot splash, login logo, backgrounds; the installer's screens | `packages/silikos-branding`, `installer/`, `brand/` |

![The SilikOS desktop](docs/img/desktop.png)

![Start](docs/img/start.png)

The desktop as run on 10/11/2026 (GNOME Shell 40.10 in an AlmaLinux 9.8 container, software rendering; see
`docs/STATUS.md` for what has and has not been run). The installer: `docs/img/installer.png`.

```bash
bash tools/build_rpms.sh          # the six packages + repository metadata in build/repo (rpmbuild, createrepo_c)
python3 -m unittest discover -s tests
bash tools/build_iso.sh           # the network installer ISO (needs repo.almalinux.org)
```

Read `docs/PLAN.md` (decisions and phases), `docs/STATUS.md` (verified / not verified), `docs/HARDWARE.md`
(Ryzen 7 5800HS + RTX 3050, Snapdragon X), `docs/BUILD.md`.

No vendor software is in this repository or in the system: EDA tools, Windows and Windows programs are the user's own
licences.
