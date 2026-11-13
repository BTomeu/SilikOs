# Reporting a vulnerability in SilikOS

Report it privately through GitHub: this repository's **Security** tab, **Report a vulnerability**
([`security/advisories/new`](../../security/advisories/new)). Please do not put the details in a public issue or
pull request. If that button is not shown, open an issue that says only that you have a report to make.

- **What to report here:** SilikOS's own code: the packages of `packages/`, the kickstart, the installer's files,
  the build scripts and recipes (`tools/`, `eda/`, `dev/`, `wine/`) and the workflows.
- **What to report elsewhere:** the base's packages (AlmaLinux OS) and the tools SilikOS builds from their authors'
  unmodified sources (Wine, KLayout, OpenOCD...) have their own security contacts; tell us too if a recipe of ours
  makes it worse or pins a version with a known hole.
- **Versions:** only the current `main` is looked after. SilikOS is a prototype with one maintainer; no response
  time is promised.

What the system sets, what it does not protect against, and how it was checked: `docs/SECURITY.md`.
