#!/usr/bin/env bash
# tests/install/sealed.sh ISO [OUT_DIR]: an encrypted installation started with Secure Boot and a TPM, and `silik
# disk` on it (docs/DISK.md), in a virtual machine, with the SilikOS ISO as a person would use it. As
# tests/install/rollback.sh, whose ways it follows (the ISO's own kickstart + CI-only lines on a separate disk image,
# the checks reported on the serial port as SILIKOS-CI|name|verdict|detail, the SILIK_CI_* settings):
#   1. an unattended installation under UEFI (Secure Boot off: the installer's kernel is handed to the firmware by
#      QEMU, not through the signed boot loader) with `autopart --encrypted` and nothing else named (sealed.ks.in):
#      what the installer's Automatic partitioning with "Encrypt my data" makes on this ISO. A small package set.
#   2. the installed system starts seven times; before each start the firmware's variables and the TPM are chosen,
#      and what the start asks on the console is typed by sealed-console.py, as a person would:
#        first   Secure Boot on (the firmware's variables with Microsoft's keys enrolled: the base's shim is signed
#                by Microsoft's CA for other systems), an empty software TPM; the passphrase is typed. Inside
#                (sealed-check.sh): `silik disk`, `silik disk tpm enroll` with a PIN, `silik disk recovery`
#        pin     the same machine: the PIN is asked and typed; the passphrase must not be asked
#        sboff   the firmware's variables without Secure Boot, the same TPM: the PIN must not open the disk; the
#                passphrase does
#        moved   Secure Boot on, another TPM (empty): the disk in another machine. The same
#        back    the first machine again: the PIN opens it again
#        skip    an empty PIN, then a wrong one: how the passphrase is reached (what is seen is reported; it costs
#                the TPM's lockout one count). Inside: `silik disk tpm remove`
#        plain   the passphrase is asked, no PIN
#   OUT_DIR (default build/sealed-test): sealed-install.log, sealed-<start>.log (the consoles), sealed.ks,
#   report.txt;  exit 0 when no check failed and every start finished.
#   SILIK_CI_APPEND, SILIK_CI_MEM, SILIK_CI_CPUS, SILIK_CI_TCG: as tests/install/run.sh.
#   SILIK_CI_SEALED_DISK (GB, default 40; the image is sparse), SILIK_CI_INSTALL_MIN (default 60),
#   SILIK_CI_BOOT_MIN (default 12; the first start has twice that)
#   SILIK_CI_OVMF_CODE, SILIK_CI_OVMF_VARS_SB, SILIK_CI_OVMF_VARS: the firmware (default: Ubuntu's package ovmf,
#   /usr/share/OVMF/OVMF_CODE_4M.secboot.fd, OVMF_VARS_4M.ms.fd, OVMF_VARS_4M.fd; then EL's edk2-ovmf)
# Needs qemu-system-x86_64, qemu-img, xorriso, mtools, python3, swtpm, the OVMF firmware.
# The TPM's state and its socket are kept under /tmp: Ubuntu's AppArmor profile of swtpm lets it write there and in
# the user's home, nowhere else (read in swtpm 0.7.3-0ubuntu5.24.04.1).
# Written 13/11/2026 on a machine without KVM: it has not run yet (docs/STATUS.md). What ran there: the flow of this
# script against stand-ins of QEMU and swtpm (tests/test_sealed.py); and, emulated, with the QEMU options below, this
# firmware (ovmf 2024.02-2ubuntu0.10) and swtpm 0.7.3: the firmware with Secure Boot on starts the base's shim from
# the fall-back path, the shim writes its boot entry and restarts the machine, the entry starts shim and GRUB; a
# changed shim is refused; the kernel given with -kernel starts as an EFI system (docs/DISK.md).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../.." && pwd)
iso=${1:?usage: tests/install/sealed.sh ISO [OUT_DIR]}
out=${2:-$root/build/sealed-test}
mem=${SILIK_CI_MEM:-4096}; cpus=${SILIK_CI_CPUS:-$(nproc)}; disk_gb=${SILIK_CI_SEALED_DISK:-40}
t_install=${SILIK_CI_INSTALL_MIN:-60}; t_boot=${SILIK_CI_BOOT_MIN:-12}
# the test's own secrets: they protect a disk image that is deleted at the end
PASSPHRASE=silikos-ci-sealed-disk; PIN=271828; WRONG_PIN=0
mkdir -p "$out"; out=$(cd "$out" && pwd); iso=$(cd "$(dirname "$iso")" && pwd)/$(basename "$iso")
work=$(mktemp -d /tmp/silik-sealed.XXXXXX)
qpid=""; tpid=""
cleanup() {
  [ -z "$qpid" ] || kill "$qpid" 2> /dev/null || true
  [ -z "$tpid" ] || kill "$tpid" 2> /dev/null || true
  rm -rf "$work"
}
trap cleanup EXIT

if [ -w /dev/kvm ]; then accel=(-enable-kvm -cpu host)
elif [ "${SILIK_CI_TCG:-0}" = 1 ]; then accel=(-accel tcg,thread=multi -cpu max); echo "no /dev/kvm: emulating (very slow)"
else echo "error: /dev/kvm is not usable (SILIK_CI_TCG=1 to emulate, many hours)" >&2; exit 2; fi
for tool in qemu-system-x86_64 qemu-img xorriso mformat mcopy python3 swtpm; do
  command -v "$tool" > /dev/null || { echo "error: $tool is not installed" >&2; exit 2; }
done
first_of() { local f; for f in "$@"; do [ -n "$f" ] && [ -f "$f" ] && { echo "$f"; return 0; }; done; return 1; }
code=$(first_of "${SILIK_CI_OVMF_CODE:-}" /usr/share/OVMF/OVMF_CODE_4M.secboot.fd /usr/share/OVMF/OVMF_CODE.secboot.fd /usr/share/edk2/ovmf/OVMF_CODE.secboot.fd) \
  && vars_sb=$(first_of "${SILIK_CI_OVMF_VARS_SB:-}" /usr/share/OVMF/OVMF_VARS_4M.ms.fd /usr/share/OVMF/OVMF_VARS.ms.fd /usr/share/edk2/ovmf/OVMF_VARS.secboot.fd) \
  && vars_plain=$(first_of "${SILIK_CI_OVMF_VARS:-}" /usr/share/OVMF/OVMF_VARS_4M.fd /usr/share/OVMF/OVMF_VARS.fd /usr/share/edk2/ovmf/OVMF_VARS.fd) \
  || { echo "error: no OVMF firmware with Secure Boot found (the package ovmf, or edk2-ovmf); here: $(ls /usr/share/OVMF /usr/share/edk2/ovmf 2> /dev/null | tr '\n' ' ')" >&2; exit 2; }
echo "firmware: $code; Secure Boot on: $vars_sb; off: $vars_plain"
# (the firmware with Secure Boot keeps its variables in flash that only its system management mode may write)
machine=(-machine q35,smm=on -global driver=cfi.pflash01,property=secure,value=on -global ICH9-LPC.disable_s3=1)

label=$(xorriso -indev "$iso" -pvd_info 2>/dev/null | sed -n 's/^Volume Id *: *//p')
[ -n "$label" ] || { echo "error: cannot read the label of $iso" >&2; exit 2; }
xorriso -indev "$iso" -osirrox on -extract /silikos.ks "$work/shipped.ks" -extract /images/pxeboot/vmlinuz "$work/vmlinuz" \
  -extract /images/pxeboot/initrd.img "$work/initrd.img" > /dev/null 2>&1
chmod u+w "$work"/*
clean() { tr -d '\r' < "$1" | sed 's/\x1b\[[0-9;?]*[A-Za-z]//g; s/\x1b[()][A-Z0-9]//g' | grep -v '^[[:space:]]*$'; }

# the kickstart of the test: the ISO's own (its screen-mode lines, its boot loader line and its desktop taken out:
# the base's core, silik-tools and silikos-security are what this test is about) + the CI-only lines of sealed.ks.in
python3 - "$work/shipped.ks" "$here/sealed.ks.in" "$here/sealed-check.sh" "$PASSPHRASE" "$PIN" > "$work/sealed.ks" <<'EOF'
import re, sys
shipped, extra, check, passphrase, pin = sys.argv[1:6]
ks = "\n".join(l for l in open(shipped).read().splitlines() if l not in ("graphical", "firstboot --enable")) + "\n"
ks = re.sub(r"(?ms)^%packages.*?^%end\n", "%packages\n@core\nsilik-tools\nsilikos-security\ncryptsetup\nmokutil\nefibootmgr\n%end\n", ks, count=1)
ks = "\n".join(l for l in ks.splitlines() if not l.startswith(("services ", "xconfig ", "bootloader "))) + "\n"
print(ks + open(extra).read().replace("@PASSPHRASE@", passphrase).replace("@PIN@", pin).replace("@CHECK@", open(check).read().rstrip("\n")))
EOF
cp "$work/sealed.ks" "$out/sealed.ks"
dd if=/dev/zero of="$work/ks.img" bs=1M count=8 status=none
mformat -i "$work/ks.img" -v SILIKCI ::
mcopy -i "$work/ks.img" "$work/sealed.ks" ::/ci.ks

: > "$out/report.txt"
row() { printf '%-5s %-44s %s\n' "$1" "$2" "$3" >> "$out/report.txt"; }

# ---------------------------------------------------------------------------------------------- 1. the installation
install() {
  local rc=0 n=0
  qemu-img create -q -f qcow2 "$out/sealed.qcow2" "${disk_gb}G"
  cp "$vars_plain" "$work/vars-install.fd"
  echo "[sealed] installing from $(basename "$iso") under UEFI, $cpus CPUs, $mem MB, a ${disk_gb} GB disk; the installer's console: $out/sealed-install.log"
  : > "$out/sealed-install.log"
  timeout "${t_install}m" qemu-system-x86_64 "${accel[@]}" "${machine[@]}" -m "$mem" -smp "$cpus" -display none -no-reboot \
    -drive "if=pflash,format=raw,unit=0,readonly=on,file=$code" -drive "if=pflash,format=raw,unit=1,file=$work/vars-install.fd" \
    -kernel "$work/vmlinuz" -initrd "$work/initrd.img" \
    -append "inst.stage2=hd:LABEL=$label inst.ks=hd:LABEL=SILIKCI:/ci.ks inst.text console=ttyS0,115200 ${SILIK_CI_APPEND:-}" \
    -drive "file=$out/sealed.qcow2,if=virtio,format=qcow2,discard=unmap" -drive "file=$work/ks.img,if=virtio,format=raw,readonly=on" \
    -cdrom "$iso" -nic user,model=virtio-net-pci -serial "file:$out/sealed-install.log" -monitor none &
  qpid=$!
  ( while kill -0 $qpid 2> /dev/null; do
      sleep 20; n=$((n + 1))
      if grep -q "Please make a selection from the above" "$out/sealed-install.log"; then    # it asks: it will never go on
        echo "error: [sealed] the installer stopped at its summary and waits for an answer:" >&2
        clean "$out/sealed-install.log" | grep -B14 "Please make a selection" | tail -16 >&2
        pkill -P $qpid qemu-system-x86 2> /dev/null; kill $qpid 2> /dev/null
        break
      fi
      [ $((n % 6)) = 0 ] && echo "  ... $(clean "$out/sealed-install.log" | tail -1 | cut -c1-150)"
    done ) &
  local watch=$!
  wait $qpid || rc=$?
  qpid=""
  pkill -P $watch 2> /dev/null || true; kill $watch 2> /dev/null || true; wait $watch 2> /dev/null || true
  if [ $rc -ne 0 ]; then
    echo "error: [sealed] the installation did not finish (exit $rc; 124 = time limit of $t_install min). Last lines of its console:" >&2
    clean "$out/sealed-install.log" | tail -40 >&2
    return 1
  fi
  echo "[sealed] installed: the disk image holds $(du -h "$out/sealed.qcow2" | cut -f1)"
}

# ---------------------------------------------------------------------------------------------- 2. the starts
# start NAME VARS_FILE TPM_DIR MINUTES EXPECT [PIN_ANSWER...]: the installed system starts once with these firmware
# variables and this TPM; sealed-check.sh runs its stage NAME there and powers off. What the console asked is judged:
#   EXPECT  passphrase   only the passphrase was asked
#           pin          only the PIN was asked, once
#           refused      the PIN was typed (or not even asked) and the passphrase was needed
#           any          reported, not judged
start() {
  local name=$1 vars=$2 tpm=$3 limit=$4 expect=$5 pins=() a i; shift 5
  for a in "$@"; do pins+=(--pin "$a"); done
  dd if=/dev/zero of="$work/stage.img" bs=1M count=4 status=none
  mformat -i "$work/stage.img" -v SILIKCI ::
  echo "$name" > "$work/stage"; mcopy -i "$work/stage.img" "$work/stage" ::/stage
  mkdir -p "$tpm"; rm -f "$tpm/sock" "$work/ser.sock"
  swtpm socket --tpm2 --tpmstate "dir=$tpm" --ctrl "type=unixio,path=$tpm/sock" --terminate --log "file=$work/swtpm.log" &
  tpid=$!
  for i in $(seq 1 50); do [ -S "$tpm/sock" ] && break; sleep 0.2; done
  [ -S "$tpm/sock" ] || { row FAIL "sealed.$name.finished" "the software TPM did not start: $(tail -3 "$work/swtpm.log" 2> /dev/null | tr '\n' ' ')"; kill $tpid 2> /dev/null || true; tpid=""; return 1; }
  : > "$out/sealed-$name.log"
  echo "[sealed] start '$name': $(basename "$vars"), TPM $(basename "$tpm"); the console: $out/sealed-$name.log"
  qemu-system-x86_64 "${accel[@]}" "${machine[@]}" -m "$mem" -smp "$cpus" -display none \
    -drive "if=pflash,format=raw,unit=0,readonly=on,file=$code" -drive "if=pflash,format=raw,unit=1,file=$vars" \
    -chardev "socket,id=chrtpm,path=$tpm/sock" -tpmdev emulator,id=tpm0,chardev=chrtpm -device tpm-tis,tpmdev=tpm0 \
    -drive "file=$out/sealed.qcow2,if=virtio,format=qcow2,discard=unmap" -drive "file=$work/stage.img,if=virtio,format=raw,readonly=on" \
    -nic user,model=virtio-net-pci -monitor none \
    -chardev "socket,id=ser,path=$work/ser.sock,server=on,wait=off,logfile=$out/sealed-$name.log" -serial chardev:ser &
  qpid=$!
  python3 "$here/sealed-console.py" "$work/ser.sock" --passphrase "$PASSPHRASE" "${pins[@]}" --limit $((limit * 60)) > "$work/$name.json" || true
  for i in $(seq 1 30); do kill -0 $qpid 2> /dev/null || break; sleep 2; done      # (it powers itself off after its stage)
  kill $qpid 2> /dev/null || true; wait $qpid 2> /dev/null || true; qpid=""
  for i in $(seq 1 25); do kill -0 $tpid 2> /dev/null || break; sleep 0.2; done    # (the TPM writes its state and ends)
  kill $tpid 2> /dev/null || true; wait $tpid 2> /dev/null || true; tpid=""
  # the checks the system said on its console, then what the console asked
  tr -d '\r' < "$out/sealed-$name.log" | grep '^SILIKOS-CI|sealed\.' | while IFS='|' read -r _ check verdict detail; do
    row "$verdict" "$check" "$detail"
  done || true
  python3 - "$work/$name.json" "$name" "$expect" >> "$out/report.txt" <<'EOF'
import json, sys
path, name, expect = sys.argv[1:4]
try:
    r = json.load(open(path))
except (OSError, ValueError):
    r = {"asked": [], "end": "no result", "why": "sealed-console.py gave nothing", "marks": []}
asked, said = r["asked"], ", ".join(r["asked"]) or "nothing"
def row(verdict, check, detail):
    print("%-5s %-44s %s" % (verdict, "sealed.%s.%s" % (name, check), detail))
if expect == "passphrase":
    ok = "passphrase" in asked and "pin" not in asked
    row("ok" if ok else "FAIL", "console", "asked: %s%s" % (said, "" if ok else " (wanted: the passphrase and no PIN)"))
elif expect == "pin":
    ok = asked == ["pin"]
    row("ok" if ok else "FAIL", "console", "asked: %s%s" % (said, ": the PIN opened the disk" if ok else " (wanted: the PIN once, and no passphrase)"))
elif expect == "refused":
    ok = "passphrase" in asked
    row("ok" if ok else "FAIL", "console", "asked: %s: %s" % (said, "the PIN did not open the disk, the passphrase did" if ok else "the disk opened WITHOUT the passphrase"))
else:
    row("info", "console", "asked: %s" % said)
done = r["end"] == "closed" and name in r["marks"]
row("ok" if done else "FAIL", "finished", "the stage ran and the machine powered off" if done else
    "the stage did not finish: the console ended with '%s'%s; stages finished in this start: %s" % (r["end"], " (%s)" % r["why"] if r.get("why") else "", ", ".join(r["marks"]) or "none"))
EOF
  grep -q "^ok    sealed\.$name\.finished " "$out/report.txt"
}

status=0
if install; then
  row ok sealed.installation "an encrypted installation under UEFI finished"
  cp "$vars_sb" "$work/vars-sb.fd"; cp "$vars_plain" "$work/vars-off.fd"
  # (after `first` nothing can be judged without its enrolment; the later starts are each on their own)
  if start first "$work/vars-sb.fd" "$work/tpm-a" $((t_boot * 2)) passphrase; then
    start pin "$work/vars-sb.fd" "$work/tpm-a" "$t_boot" pin "$PIN" || status=1
    start sboff "$work/vars-off.fd" "$work/tpm-a" "$t_boot" refused "$PIN" || status=1
    start moved "$work/vars-sb.fd" "$work/tpm-b" "$t_boot" refused "$PIN" || status=1
    start back "$work/vars-sb.fd" "$work/tpm-a" "$t_boot" pin "$PIN" || status=1
    start skip "$work/vars-sb.fd" "$work/tpm-a" "$t_boot" any "" "$WRONG_PIN" || status=1
    start plain "$work/vars-sb.fd" "$work/tpm-a" "$t_boot" passphrase || status=1
  else
    status=1
    echo "error: [sealed] the first start did not finish. Last lines of its console:" >&2
    clean "$out/sealed-first.log" | tail -40 >&2
  fi
else
  row FAIL sealed.installation "did not finish: $(clean "$out/sealed-install.log" | grep -i "error\|\[!\]" | tail -2 | tr '\n' ' ' | cut -c1-200)"
  status=1
fi
rm -f "$out/sealed.qcow2"
cp "$work/swtpm.log" "$out/swtpm.log" 2> /dev/null || true

echo "SilikOS sealed test: $(basename "$iso"), $(date -u +%Y-%m-%dT%H:%MZ)"
cat "$out/report.txt"
grep -q '^FAIL' "$out/report.txt" && status=1
echo "$(grep -c '^ok' "$out/report.txt" || true) ok, $(grep -c '^FAIL' "$out/report.txt" || true) failed"

# one line for each start: what its checks said (an annotation of the run in GitHub Actions)
step() {   # step NAME TITLE
  local rx ok fail first
  rx="^(ok|FAIL|info) +sealed\.$1(\.| )"
  ok=$(grep -E "$rx" "$out/report.txt" | grep -c '^ok' || true)
  fail=$(grep -E "$rx" "$out/report.txt" | grep -c '^FAIL' || true)
  first=$(grep -E "$rx" "$out/report.txt" | grep '^FAIL' | head -1 | cut -c7- | tr -s ' ' | cut -c1-240 || true)
  if [ "$fail" -gt 0 ]; then echo "::error title=sealed $1: $2::$fail of $((ok + fail)) checks failed; the first: $first"
  elif [ "$ok" -gt 0 ]; then echo "::notice title=sealed $1: $2::$ok checks ok"
  else echo "::error title=sealed $1: $2::it did not run (see report.txt and the consoles in the artifact sealed-test)"; fi
}
step installation "an encrypted installation under UEFI"
step first "Secure Boot on, the passphrase; silik disk; TPM2 + PIN enrolled; a recovery key"
step pin "the PIN opens the disk"
step sboff "Secure Boot off: the PIN does not open it, the passphrase does"
step moved "another TPM: the PIN does not open it, the passphrase does"
step back "the first machine again: the PIN opens it"
step skip "an empty and a wrong PIN; silik disk tpm remove"
step plain "the passphrase again, no PIN"
exit $status
