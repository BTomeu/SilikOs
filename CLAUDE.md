# SilikOS — instructions for Claude

Read `docs/PLAN.md` and `docs/STATUS.md` first.

- The user is Tomeu (SilikVolt). Write to them in informal Catalan, short; they/them if a pronoun is needed.
- **Do not change the base system** (kernel, glibc, package set, `/etc/redhat-release`, `/etc/system-release`, and the
  fields of `os-release` that programs read: ID, ID_LIKE, VERSION_ID, PLATFORM_ID, CPE_NAME): EDA compatibility depends
  on being binary identical to RHEL 9. SilikOS is packages on top.
- **It must not look like AlmaLinux** (owner, 10/11/2026): everything a person sees says SilikOS (installer, boot
  menu, boot splash, login, About, `PRETTY_NAME`). Display names only; `silik identity base` is the way back for an
  installer that insists on the base's name. SilikOS carries the base's version number (SilikOS 9.8 on EL 9.8).
- **Never claim something works that was not run.** `docs/STATUS.md` has two tables, verified and not verified: keep
  them true. Assumptions are marked [A].
- No vendor software, licences, keys or the user's files in the repository.
- The kickstart never selects or erases a disk.
- Every action of the desktop goes through `silik` and prints the commands it runs; the COMMAND bar shows the same
  line. New features keep that.
- UI: one ink on paper (softer than SilikStudio: off-white paper, small radii), Cascadia Mono, EN + CA + ES strings.
- **It must look like the Silik interface** (owner, 10/11/2026), not like a themed GNOME: the three parts of
  SilikStudio's window are the desktop's: title bar = the command line, a text rail of keys (digit first, inverse
  video on the focused one), a status bar (the one message channel, then "key value" fields). They are the shell
  extension `silik-shell` (`packages/silikos-desktop/files/shell-ext`); the GTK and shell themes are made on the
  system from the installed stylesheets (`gtk-theme`, `shell-theme`), never by shipping modified copies.
- Tools are Python 3.9 standard library (the base's Python) and bash; the COMMAND bar is GTK 3 through python3-gobject;
  the shell extension is GJS for GNOME Shell 40 (the shell's own language, no other choice).
- Tests: `python3 -m unittest discover -s tests`; build: `bash tools/build_rpms.sh`.
