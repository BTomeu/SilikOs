#!/usr/bin/env bash
# shell_check.sh: the mechanical check of the ported extension, in the image "silikos-el10-shell" (el10/shell_image.sh):
#   1. el10/shell-ext is what el10/port_shell.py makes from today's EL 9 extension (port_shell.py --check)
#   2. every ported module parses as an ES module with EL 10's own gjs (SpiderMonkey's Reflect.parse, target "module":
#      `gjs -m FILE` would run it, and the shell's own modules it imports exist only inside the shell)
#   3. with SILIK_SHELL_RUN=1: the three looks, each in a headless GNOME Shell (el10/shell_run.sh), glass on, the
#      COMMAND bar started; the extension must be active, with no error, before and after being turned off and on
# Prints one line per check and ends with CHECK-OK or CHECK-FAILED.
set -u
here=$(cd "$(dirname "$0")" && pwd); root=$here/..
bad=0
python3 "$here/port_shell.py" --check && echo "ok   el10/shell-ext is the port of today's EL 9 extension" || bad=1
docker run --rm --network none -v "$root:/src:ro" silikos-el10-shell bash -c '
  rpm -q gjs gnome-shell | tr "\n" " "; echo
  for f in /src/el10/shell-ext/*.js; do
    gjs -c "const t = new TextDecoder().decode(imports.gi.GLib.file_get_contents(\"$f\")[1]); Reflect.parse(t, {target: \"module\"}); print(\"ok   $(basename $f) parses as an ES module (\" + t.split(\"\\n\").length + \" lines)\")" || exit 1
  done' || bad=1
if [ "${SILIK_SHELL_RUN:-0}" = 1 ]; then
  mkdir -p "$root/build/el10/out"
  for look in island bar silik; do
    out=$(SILIK_LOOK=$look SILIK_COMMAND=1 "$here/shell_run.sh" host 12 2>&1 | grep '^##\|^   \|VERDICT\|^[0-9]*[:-]')
    printf '%s\n' "$out" | sed "s/^/[$look] /"
    n=$(printf '%s\n' "$out" | grep -c '"state":1,"error":""\|state 1, error none')
    errs=$(printf '%s\n' "$out" | grep -c 'JS ERROR\|ERROR ')
    if [ "$n" = 2 ] && [ "$errs" = 0 ]; then echo "ok   look $look: active before and after off/on, no JS error"; else echo "FAIL look $look"; bad=1; fi
  done
fi
[ $bad = 0 ] && echo CHECK-OK || { echo CHECK-FAILED; exit 1; }
