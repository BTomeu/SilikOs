# SilikOS — instructions for Claude

Read `docs/PLAN.md` and `docs/STATUS.md` first.

- The user is Tomeu (SilikVolt). Write to them in informal Catalan, short; they/them if a pronoun is needed.
- **Do not change the base system** (kernel, glibc, `/etc/os-release`, `/etc/redhat-release`): EDA compatibility
  depends on being binary identical to RHEL 9. SilikOS is packages on top.
- **Never claim something works that was not run.** `docs/STATUS.md` has two tables, verified and not verified: keep
  them true. Assumptions are marked [A].
- No vendor software, licences, keys or the user's files in the repository.
- The kickstart never selects or erases a disk.
- Every action of the desktop goes through `silik` and prints the commands it runs; the COMMAND bar shows the same
  line. New features keep that.
- UI: one ink on paper (softer than SilikStudio: off-white paper, small radii), Cascadia Mono, EN + CA + ES strings.
- Tools are Python 3.9 standard library (the base's Python) and bash; the COMMAND bar is GTK 3 through python3-gobject.
- Tests: `python3 -m unittest discover -s tests`; build: `bash tools/build_rpms.sh`.
