# el10/: the EL 10 track

SilikOS 9 (AlmaLinux 9) is the product. This folder is what was tried on AlmaLinux 10: scripts that run in containers,
the port of the shell extension to GNOME Shell 49 (`shell-ext/`, made by `port_shell.py` from the EL 9 extension; do
not edit it by hand), the outputs of the runs (`results/`), and the **SilikOS 10 lab**: the product's packages and
kickstart with only what EL 10 forces changed (`port_system.py`, `build_rpms.sh`), an installer ISO made from
AlmaLinux 10's boot ISO (`build_iso.sh`, `remake_iso.sh`, `installer/`) and its unattended installation test in a
virtual machine (`lab/`, the workflow `.github/workflows/el10.yml`, on the branch `el10-lab` only). Nothing here is
installed by any package of the product or built into the product's ISO, and nothing of the product is written. What
works, what does not, how to run each script and the plan: `docs/EL10.md`.
