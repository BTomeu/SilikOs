# silik plugins

A group of commands of `silik` can live in a file of its own. `silik` reads the file's head as text and imports the
file only when its group is typed, so a plugin costs the other commands nothing (13/11/2026).

## The file

`packages/silik-tools/files/plugins/NAME.py` (installed as `/usr/share/silikos/python/plugins/NAME.py`):

```python
# silik-plugin: NAME
# help: one line for `silik --help`
# words: export show            (the group's commands: the shell's completion reads this line)
"""what the group does"""


def export(ctx, a):
    ctx.run(["rpm", "-qa"])     # every action through ctx: printed as `$ ...`, not run under --dry-run


def register(group, silik):
    """GROUP: this group's parser. SILIK: the silik module (Ctx, die, the helpers every command uses)"""
    sub = group.add_subparsers(dest="cmd")
    x = sub.add_parser("export", help="...")
    x.add_argument("--json", action="store_true")
    x.set_defaults(fn=export)
```

- NAME is the file's name and the group's: lower case letters, digits and `-`.
- A plugin never replaces a command of silik's own (`status`, `eda`...): such a file is ignored.
- Only files owned by root or by the owner of `silik` itself, and not writable by everybody, are taken.
- The rules of every `silik` command hold: each action prints the command it runs, `--dry-run` runs nothing, `--json`
  where a program may read the answer, texts a person reads in EN + CA + ES, Python 3.9 standard library only.
- Imports that cost (xml, tempfile, urllib...) go inside the function that needs them, as in `silik` itself.

## The COMMAND bar

`plugins/NAME.cmd.json`, a list of the group's addresses:

```json
[{"address": "NAME/export", "argv": ["NAME", "export"], "en": "...", "ca": "...", "es": "...", "terminal": true}]
```

`argv` is what follows `silik`: an entry runs `silik`, nothing else. `terminal` (default true): in a terminal, so that
what it prints is seen.

## Tests

`tests/test_plugins.py` holds every plugin of the repository to this (its head, its words, the three languages of its
addresses, `silik NAME --help`). A plugin's own tests load `silik` as `tests/test_silik.py` does and call
`silik.main(["NAME", ...])`.
