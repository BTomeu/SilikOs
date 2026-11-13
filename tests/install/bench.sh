#!/usr/bin/env bash
# tests/install/bench.sh DISK KS_IMG OUT_DIR STEP...: the measurement starts of an installed test system (a disk made
# by tests/install/run.sh or compare.sh, whose kickstart carried bench.ks.in). Each STEP is one start of the virtual
# machine, the same machine as the installation test's; the system reads the step from the test's own disk (KS_IMG,
# a file "phase"), does it and powers off (bench-guest.sh):
#   settle           a start that only waits and shuts down cleanly (the first boot was cut off by the test)
#   measure:LABEL    two minutes after the desktop is up: `silik bench system` -> OUT_DIR/bench-LABEL.json, .txt and
#                    -raw.txt (the base's own commands as they print: systemd-analyze, blame, critical-chain, free, ps)
#   undo             `silik speed undo` on the installed system -> OUT_DIR/bench-undo.txt
# Then OUT_DIR/bench.txt: the captures side by side (`silik bench compare`) and each one's text. One start is one
# sample: two measures of the same state show the noise. Exit 0 when every measure gave a capture.
# In GitHub Actions the numbers of each capture are also a notice of the run.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../.." && pwd)
disk=${1:?usage: tests/install/bench.sh DISK KS_IMG OUT_DIR STEP...}; ks=${2:?}; out=${3:?}; shift 3
mem=${SILIK_CI_MEM:-4096}; cpus=${SILIK_CI_CPUS:-$(nproc)}; t_start=${SILIK_CI_BENCH_MIN:-10}
mkdir -p "$out"; out=$(cd "$out" && pwd)
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
if [ -w /dev/kvm ]; then accel=(-enable-kvm -cpu host); how=KVM
elif [ "${SILIK_CI_TCG:-0}" = 1 ]; then accel=(-accel tcg,thread=multi -cpu max); how="emulated: its times say nothing"; echo "no /dev/kvm: emulating (times measured this way say nothing)"
else echo "error: /dev/kvm is not usable" >&2; exit 2; fi

labels=()
for step in "$@"; do          # (every step is read before the first start: a capture that is asked for and not taken is said)
  phase=${step%%:*}; label=; [ "$step" = "$phase" ] || label=${step#*:}
  case $phase in settle|undo) ;; measure) [ -n "$label" ] || { echo "error: measure:LABEL" >&2; exit 2; }; labels+=("$label") ;;
    *) echo "error: step $step (settle, measure:LABEL, undo)" >&2; exit 2 ;; esac
done
n=0; stuck=0
for step in "$@"; do
  n=$((n + 1)); phase=${step%%:*}; label=; [ "$step" = "$phase" ] || label=${step#*:}
  printf '%s %s\n' "$phase" "$label" > "$work/phase"
  mcopy -o -i "$ks" "$work/phase" ::/phase
  ser="$out/bench-start$n-$phase${label:+-$label}"
  : > "$ser.log"; : > "$ser.out"
  echo "start $n: $phase $label (console: $ser.log)"
  rc=0
  timeout "${t_start}m" qemu-system-x86_64 "${accel[@]}" -machine q35 -m "$mem" -smp "$cpus" -display none -vga std \
    -drive "file=$disk,if=virtio,format=qcow2" -drive "file=$ks,if=virtio,format=raw,readonly=on" \
    -nic user,model=virtio-net-pci -serial "file:$ser.log" -serial "file:$ser.out" -monitor none || rc=$?
  if [ $rc != 0 ]; then
    echo "  the system did not power off by itself (exit $rc; 124 = the limit of $t_start min)"
    stuck=$((stuck + 1))
    # (two starts that do not end: the others would not either, and each waits for its limit)
    [ $stuck -lt 2 ] || { echo "  two starts did not end: the remaining steps are left out"; break; }
  fi
  tr -d '\r' < "$ser.out" | grep -a '^SILIKOS-BENCH|' | sed 's/^SILIKOS-BENCH|/  /; s/|/: /' || true
done
mdel -i "$ks" ::/phase 2> /dev/null || true

# the captures out of the second serial port's files; the table
python3 - "$out" "${labels[@]}" <<'EOF'
import glob, json, os, re, sys
out, labels = sys.argv[1], sys.argv[2:]
texts = {}
for f in sorted(glob.glob(os.path.join(out, "bench-start*.out"))):
    t = open(f, errors="replace").read().replace("\r", "")
    for kind, label, body in re.findall(r"SILIKOS-BENCH-BEGIN (\w+) ?(\S*)\n(.*?)\nSILIKOS-BENCH-END \1", t, re.S):
        texts[(kind, label)] = body.strip("\n") + "\n"
missing = []
for label in labels:
    try:
        cap = json.loads(texts[("json", label)])
        assert isinstance(cap, dict) and "boot" in cap and "memory" in cap
    except (KeyError, ValueError, AssertionError):
        missing.append(label)
        continue
    with open(os.path.join(out, "bench-%s.json" % label), "w") as fh:
        json.dump(cap, fh, indent=1)
    for kind, suffix in (("text", ".txt"), ("raw", "-raw.txt"), ("session", "-session.txt")):
        if (kind, label) in texts:
            with open(os.path.join(out, "bench-%s%s" % (label, suffix)), "w") as fh:
                fh.write(texts[(kind, label)])
for (kind, label), body in texts.items():
    if kind == "undo":
        with open(os.path.join(out, "bench-undo.txt"), "w") as fh:
            fh.write(body)
with open(os.path.join(out, "bench-missing"), "w") as fh:
    fh.write(" ".join(missing))
EOF
missing=$(cat "$out/bench-missing"); rm -f "$out/bench-missing"
files=(); for l in "${labels[@]}"; do [ -f "$out/bench-$l.json" ] && files+=("$out/bench-$l.json"); done
{ echo "SilikOS bench: $(date -u +%Y-%m-%dT%H:%MZ), a virtual machine of $cpus CPUs and $mem MB ($how); each column is one start, measured two minutes after the desktop was up"
  if [ ${#files[@]} -gt 0 ]; then
    python3 "$root/packages/silik-tools/files/silik" bench compare "${files[@]}"
    for l in "${labels[@]}"; do [ -f "$out/bench-$l.txt" ] && { echo; echo "== $l"; cat "$out/bench-$l.txt"; }; done
    # how each session came up: the user's units by the time they took, and the journal's lines of the display
    # server, the session and the shell (where the seconds between gdm and the desktop go)
    for l in "${labels[@]}"; do [ -f "$out/bench-$l-session.txt" ] && { echo; echo "== $l: the session's start"; cat "$out/bench-$l-session.txt"; }; done
  fi
  [ -z "$missing" ] || echo "no capture of: $missing (the console and the second serial port of that start: bench-start*.log, .out)"
} > "$out/bench.txt"
cat "$out/bench.txt"
if [ -n "${GITHUB_ACTIONS:-}" ]; then
  for f in "${files[@]}"; do
    python3 - "$f" <<'EOF'
import json, sys
c = json.load(open(sys.argv[1]))
b, m, p, u = c["boot"], c["memory"], c["processes"], c["units"]
s = lambda v: "?" if v is None else ("%.1f s" % v)
parts = " + ".join("%s %s" % (k, s(b.get(k + "_s"))) for k in ("firmware", "loader", "kernel", "initrd", "userspace") if b.get(k + "_s") is not None)
print("::notice title=SilikOS bench %s::start %s = %s; login screen at %s, desktop at %s; memory %s MB used, %s available of %s; %s processes, %s units running; speed profile %s"
      % (c["label"], parts or "?", s(b.get("total_s")), s(b.get("login_screen_s")), s(b.get("desktop_s")), m.get("used_mb"), m.get("available_mb"), m.get("total_mb"),
         p.get("count"), u.get("running"), "applied" if c["speed"]["applied"] else "not applied"))
EOF
  done
  [ -z "$missing" ] || echo "::warning title=SilikOS bench::no capture of: $missing"
fi
[ -z "$missing" ]
