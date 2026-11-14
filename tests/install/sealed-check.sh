#!/usr/bin/bash
# silikos-ci-sealed: `silik disk` inside the virtual machine the CI installed with an encrypted disk, started with
# Secure Boot and a TPM (tests/install/sealed.sh; docs/DISK.md). It runs at every start, one stage each (the stage's
# name is in the file `stage` of the small disk labelled SILIKCI that sealed.sh attaches), and says what it saw on
# the serial port like tests/install/check.sh:
#   SILIKOS-CI|sealed.<stage>.<name>|ok or FAIL or info|<what was seen>      and SILIKOS-CI|END|<stage> at its end.
# What was typed to open the disk at each start (the passphrase, the PIN) is seen from outside, by sealed.sh.
#   first   Secure Boot on, an empty TPM, opened with the passphrase: what `silik disk` says of the installation;
#           `silik disk tpm enroll` with a PIN; a recovery key
#   pin     the same machine: the PIN must have opened it, and cost the TPM's lockout nothing
#   sboff   Secure Boot off: the PIN must not have opened it, and cost nothing; enrolling is refused there
#   moved   Secure Boot on, another (empty) TPM: the disk in another machine. The PIN must not have opened it
#   skip    the first machine, an empty and then a wrong PIN typed: the passphrase was reached; what it cost is said.
#           Then failed authorisations until the TPM locks itself
#   locked  that TPM, locked: the PIN must not have opened it; the lockout is cleared
#   cleared that TPM: the PIN opens it again
#   back    the first machine again: the PIN opens it; `silik disk tpm remove`
#   plain   the passphrase again, no PIN asked; the end
# Only in the CI's test installations. Its first run: sealed.sh's head (the stages locked and cleared have not run).
out=/dev/ttyS0
say() { printf '\r\nSILIKOS-CI|sealed.%s|%s|%s\r\n' "$1" "$2" "$(echo "$3" | tr '\n|' ' /' | cut -c1-300)" > $out; }
is() { if [ "$2" = "$3" ]; then say "$1" ok "$2"; else say "$1" FAIL "saw '$2', wanted '$3'"; fi; }
has() { case "$2" in *"$3"*) say "$1" ok "$3";; *) say "$1" FAIL "no '$3' in: $2";; esac; }
hasnot() { case "$2" in *"$3"*) say "$1" FAIL "'$3' in: $2";; *) say "$1" ok "no '$3'";; esac; }
S=/var/lib/silikos-ci
mkdir -p $S /run/silikci
mount -o ro LABEL=SILIKCI /run/silikci 2> /dev/null
stage=$(cat /run/silikci/stage 2> /dev/null); umount /run/silikci 2> /dev/null
# the end of a stage: said, and the machine powers off (sealed.sh chooses the firmware and the TPM of the next start)
end() { sync; printf '\r\nSILIKOS-CI|END|%s\r\n' "$stage" > $out; [ "$stage" != plain ] || printf '\r\nSILIKOS-CI|DONE\r\n' > $out; sync; sleep 3; systemctl poweroff; exit 0; }
[ -n "$stage" ] || { stage=none; say none.stage FAIL "no stage on the disk labelled SILIKCI"; end; }

pass=/root/sealed-pass                       # the passphrase the test's kickstart gave the installer (no newline)
pin=$(cat /root/sealed-pin)
root_src=$(findmnt -n -o SOURCE /)
# the LUKS volume / is on, as the base's own tools name it (not through silik: this is what silik is held to)
luks=$(lsblk -s -n -l -p -o NAME,FSTYPE "$root_src" | awk '$2 == "crypto_LUKS" { print $1; exit }')
slots() { cryptsetup luksDump --dump-json-metadata "$luks" 2> /dev/null | python3 -c '
import json, sys
d = json.load(sys.stdin)
tok = {s: t for t in d.get("tokens", {}).values() for s in t.get("keyslots", [])}
print(" ".join("%s:%s%s" % (s, tok[s]["type"].replace("systemd-", "") if s in tok else "passphrase",
      "+pin" if tok.get(s, {}).get("tpm2-pin") else "") for s in sorted(d["keyslots"], key=int)))' 2>&1; }
field() { python3 -c 'import json, sys
d = json.load(sys.stdin)
for k in sys.argv[1].split("."):
    d = d[int(k)] if isinstance(d, list) else d[k]
print(json.dumps(d) if isinstance(d, (dict, list)) else d)' "$1" 2>&1; }
row() { python3 -c 'import json, sys
print(next((c["state"] + ": " + c["value"] for c in json.load(sys.stdin)["checks"] if c["id"] == sys.argv[1]), "no such row"))' "$1" 2>&1; }
# what systemd-cryptsetup said of this start's unlocking (in the initramfs: its journal is kept)
journal() { journalctl -b -o cat --no-pager -t systemd-cryptsetup 2> /dev/null | tail -6 | tr '\n' ';'; }
# the TPM's own count of failed tries (a setting of the chip: here the software TPM's)
lockout() { tpm2_getcap properties-variable 2>&1 | grep -i 'LOCKOUT_COUNTER\|MAX_AUTH_FAIL\|LOCKOUT_INTERVAL\|LOCKOUT_RECOVERY\|inLockout' | tr -s ' \n' ' '; }
count() { tpm2_getcap properties-variable 2> /dev/null | sed -n 's/^TPM2_PT_LOCKOUT_COUNTER:[[:space:]]*//p'; }
sb() { mokutil --sb-state 2>&1 | head -1; }

say "$stage.start" info "stage $stage; kernel $(uname -r); $(sb); lockdown $(cat /sys/kernel/security/lockdown 2>&1); $(efibootmgr 2> /dev/null | grep -i '^BootCurrent' || echo 'no efibootmgr')"

case $stage in
first)
  # A start through the firmware's fall-back path (BOOTX64.EFI, when the firmware's variables have no entry for
  # this system yet) may measure other things into PCR 7 than a normal start: enrol only in a normal one.
  cur=$(efibootmgr 2> /dev/null | sed -n 's/^BootCurrent: *//p')
  label=$(efibootmgr 2> /dev/null | sed -n "s/^Boot$cur\*\? *//p" | head -1)
  case "$label" in
    *[Aa]lma[Ll]inux*|*SilikOS*) say first.boot-entry ok "$label";;
    *) if [ ! -e $S/restarted ]; then
         touch $S/restarted; say first.boot-entry info "started through '$label': restarting once, to start through the system's own entry"
         sync; systemctl reboot; exit 0
       fi
       say first.boot-entry info "still started through '$label' after a restart";;
  esac
  # ---- what the installation is
  is first.uefi "$([ -d /sys/firmware/efi ] && echo uefi || echo bios)" uefi
  has first.secure-boot "$(sb)" "SecureBoot enabled"
  is first.tpm "$(cat /sys/class/tpm/tpm0/tpm_version_major 2>&1)" 2
  p7=$(cat /sys/class/tpm/tpm0/pcr-sha256/7 2>&1)
  case "$p7" in ""|*[!0-9A-Fa-f]*) say first.pcr7 FAIL "not readable: $p7";; *[1-9A-Ea-e]*) say first.pcr7 ok "measured: $p7";; *) say first.pcr7 FAIL "never written: $p7";; esac
  say first.layout info "$(lsblk -n -o NAME,TYPE,FSTYPE,FSVER,MOUNTPOINTS | tr -s ' ' | tr '\n' ';')"
  if [ -n "$luks" ]; then say first.luks-device ok "$luks"; else say first.luks-device FAIL "/ ($root_src) is on no LUKS volume"; fi
  # (what the installer's "Encrypt my data" makes: its defaults, nothing named by the test's kickstart)
  is first.luks-version "$(cryptsetup luksDump "$luks" 2>&1 | sed -n 's/^Version:[[:space:]]*//p')" 2
  is first.pbkdf "$(cryptsetup luksDump "$luks" 2>&1 | sed -n 's/^[[:space:]]*PBKDF: *//p' | sort -u | tr '\n' ' ')" "argon2id "
  say first.cipher info "$(cryptsetup luksDump "$luks" 2>&1 | grep -m2 -i 'cipher\b' | tr -s ' \t' ' ' | tr '\n' ';')"
  is first.slots-before "$(slots)" "0:passphrase"
  say first.crypttab-before info "$(cat /etc/crypttab)"
  # ---- what silik says of it
  j=$(silik disk --json 2> /dev/null); rc=$?
  is first.disk-exit "exit $rc" "exit 0"
  is first.disk-root "$(echo "$j" | field state.mounts./.encrypted) $(echo "$j" | field state.mounts./.luks.0)" "True $luks"
  has first.disk-home "$(echo "$j" | row /home)" "ok: "
  has first.disk-swap "$(echo "$j" | row swap)" "ok: "
  is first.disk-luks "$(echo "$j" | field state.luks.0.version) $(echo "$j" | field state.luks.0.slots)" '2 [{"slot": 0, "kind": "passphrase", "kdf": "argon2id"}]'
  is first.disk-secure-boot "$(echo "$j" | field state.secure_boot)" enabled
  is first.disk-tpm "$(echo "$j" | field state.tpm)" '{"present": true, "version": "2", "pcr7": "measured"}'
  has first.disk-unlock "$(echo "$j" | row unlock)" "ok: the passphrase, typed at every start"
  is first.disk-summary "$(echo "$j" | field summary)" "$(echo "$j" | python3 -c 'import json, sys; d = json.load(sys.stdin); print(json.dumps({"ok": len(d["checks"]), "warn": 0, "bad": 0, "unknown": 0}))')"
  # without root the key slots are unknown, never ok
  u=$(runuser -u tester -- silik disk 2>&1)
  has first.disk-user-root "$u" "ok       /  "
  has first.disk-user-slots "$(echo "$u" | grep 'LUKS /')" "unknown"
  has first.disk-user-fix "$u" "sudo silik disk"
  s=$(silik secure status --json 2> /dev/null)
  has first.secure-disk "$(echo "$s" | row disk)" "ok: "
  has first.secure-secureboot "$(echo "$s" | row secureboot)" "ok: "
  c=$(silik disk check 2>&1)
  has first.check-header "$c" "sudo cryptsetup luksHeaderBackup $luks --header-backup-file"
  has first.check-enroll "$c" "silik disk tpm enroll"
  is first.notice "$(runuser -u tester -- env DISPLAY= silik -q disk notice 2>&1)" ""
  # ---- the enrolment
  before=$(cryptsetup luksDump --dump-json-metadata "$luks" | sha256sum)
  d=$(silik --dry-run disk tpm enroll 2>&1)
  has first.dry-run-says "$d" "systemd-cryptenroll --tpm2-device=auto --tpm2-pcrs=7 --tpm2-with-pin=yes $luks"
  o=$(silik disk tpm enroll < /dev/null 2>&1); rc=$?
  has first.not-asked-not-done "exit $rc: $o" "exit 2: "
  is first.header-untouched "$(cryptsetup luksDump --dump-json-metadata "$luks" | sha256sum)" "$before"
  had_tools=$(command -v tpm2 > /dev/null && echo yes || echo no)
  o=$(printf '%s\n' "$pin" | silik disk tpm enroll --yes --unlock-key-file $pass 2>&1); rc=$?
  is first.enroll "exit $rc" "exit 0"
  say first.enroll-output info "$(echo "$o" | grep -v '^   ' | tail -12 | tr '\n' ';')"
  hasnot first.enroll-pin-not-shown "$o" "$pin"
  # (the shipped package set has tpm2-tools: the enrolment needs no network on a new installation)
  is first.tpm2-tools "the program tpm2 was there before the enrolment: $had_tools" "the program tpm2 was there before the enrolment: yes"
  say first.lockout info "$(lockout)"
  is first.slots-after "$(slots)" "0:passphrase 1:tpm2+pin"
  has first.crypttab "$(cat /etc/crypttab)" "tpm2-device=auto"
  has first.crypttab-copy "$(ls /etc/crypttab.before-silik-disk 2>&1)" "/etc/crypttab.before-silik-disk"
  has first.initramfs-module "$(lsinitrd -m 2>&1 | tr '\n' ' ')" "tpm2-tss"
  has first.initramfs-crypttab "$(lsinitrd -f etc/crypttab 2>&1)" "tpm2-device=auto"
  cryptsetup open --test-passphrase --key-file $pass "$luks" > /dev/null 2>&1; is first.passphrase-still-opens "exit $?" "exit 0"
  # ---- a recovery key (shown once: taken from what was printed, never said here)
  o=$(silik disk recovery --yes --unlock-key-file $pass 2>&1); rc=$?
  is first.recovery "exit $rc" "exit 0"
  key=$(echo "$o" | grep -o '[a-z]\{8\}\(-[a-z]\{8\}\)\{7\}' | head -1)
  is first.recovery-key-shown "${#key} characters" "71 characters"
  printf '%s' "$key" > /run/sealed-recovery; chmod 600 /run/sealed-recovery
  cryptsetup open --test-passphrase --key-file /run/sealed-recovery "$luks" > /dev/null 2>&1; is first.recovery-key-opens "exit $?" "exit 0"
  rm -f /run/sealed-recovery
  is first.slots-recovery "$(slots)" "0:passphrase 1:tpm2+pin 2:recovery"
  j=$(silik disk --json 2> /dev/null); rc=$?
  is first.disk-after "exit $rc; $(echo "$j" | row unlock)" "exit 0; ok: TPM2 + PIN while the Secure Boot state is the one it was enrolled in, or the passphrase or the recovery key"
  hasnot first.check-after "$(silik disk check 2>&1)" "silik disk recovery"
  # ---- HARDENED LEVEL: the place for `silik secure level hardened` (the lead chains it here when that command
  # ---- exists: its kernel arguments are not measured into PCR 7, so the PIN of the next start must still open)
  end;;
pin)
  say pin.journal info "$(journal)"
  is pin.slots "$(slots)" "0:passphrase 1:tpm2+pin 2:recovery"
  is pin.lockout-counter "$(count)" 0x0                      # the right PIN costs nothing
  silik disk > /dev/null 2>&1; is pin.disk "exit $?" "exit 0"
  end;;
sboff)
  has sboff.secure-boot "$(sb)" "SecureBoot disabled"
  say sboff.journal info "$(journal)"
  # (a start whose Secure Boot state is not the enrolment's: the TPM refuses on its policy, before it looks at
  # the PIN; no try is counted. Seen with tpm2-tools on a software TPM; here with the start itself)
  is sboff.lockout-counter "$(count)" 0x0
  j=$(silik disk --json 2> /dev/null); rc=$?
  has sboff.disk-secure-boot "$(echo "$j" | row secureboot)" "warn: off"
  has sboff.disk-unlock "$(echo "$j" | row unlock)" "warn: TPM2 + PIN, or the passphrase or the recovery key; but Secure Boot is not on"
  before=$(cryptsetup luksDump --dump-json-metadata "$luks" | sha256sum)
  o=$(printf '%s\n' "$pin" | silik disk tpm enroll --yes --unlock-key-file $pass 2>&1); rc=$?
  has sboff.enroll-refused "exit $rc: $o" "exit 1: silik: Secure Boot is off"
  is sboff.header-untouched "$(cryptsetup luksDump --dump-json-metadata "$luks" | sha256sum)" "$before"
  end;;
moved)
  has moved.secure-boot "$(sb)" "SecureBoot enabled"
  say moved.journal info "$(journal)"
  say moved.lockout info "$(lockout)"
  is moved.slots "$(slots)" "0:passphrase 1:tpm2+pin 2:recovery"
  end;;
skip)
  # (an empty PIN, then a wrong one, were typed: what the start did with them is in its journal, and outside)
  say skip.journal info "$(journal)"
  say skip.lockout info "$(lockout)"
  # (what Enter alone and one wrong PIN cost is the row above; one such start must not lock the TPM)
  hasnot skip.not-locked-by-one-start "$(lockout)" "inLockout: 1"
  # failed authorisations of an object of the test's own, until the TPM locks itself (what wrong PINs at several
  # starts, or starts cut by force, end in)
  d=$(mktemp -d /run/sealed-lock.XXXXXX)
  tpm2_createprimary -Q -C o -c $d/p.ctx && echo x | tpm2_create -Q -C $d/p.ctx -i - -p right -u $d/k.pub -r $d/k.priv \
    && tpm2_load -Q -C $d/p.ctx -u $d/k.pub -r $d/k.priv -c $d/k.ctx
  is skip.lock-object "exit $?" "exit 0"
  for i in 1 2 3 4 5 6 7 8; do
    case "$(lockout)" in *"inLockout: 1"*) break;; esac
    tpm2_unseal -c $d/k.ctx -p wrong > /dev/null 2>&1
  done
  rm -rf $d
  has skip.locked-out "$(lockout)" "inLockout: 1"
  cryptsetup open --test-passphrase --key-file $pass "$luks" > /dev/null 2>&1; is skip.passphrase-still-opens "exit $?" "exit 0"
  end;;
locked)
  # (the PIN was typed and the TPM was locked: outside it is seen that the passphrase was needed)
  say locked.journal info "$(journal)"
  has locked.in-lockout "$(lockout)" "inLockout: 1"
  say locked.disk info "$(silik disk 2>&1 | grep 'opens with')"          # (silik does not read the TPM's lockout)
  tpm2_dictionarylockout --clear-lockout > /dev/null 2>&1; is locked.clear "exit $?" "exit 0"
  is locked.lockout-counter-after "$(count)" 0x0
  hasnot locked.out-of-lockout "$(lockout)" "inLockout: 1"
  end;;
cleared)
  say cleared.journal info "$(journal)"
  is cleared.lockout-counter "$(count)" 0x0
  end;;
back)
  say back.journal info "$(journal)"
  has back.secure-boot "$(sb)" "SecureBoot enabled"
  is back.lockout-counter "$(count)" 0x0
  o=$(silik disk tpm remove --yes 2>&1); rc=$?
  is back.remove "exit $rc" "exit 0"
  say back.remove-output info "$(echo "$o" | tail -8 | tr '\n' ';')"
  is back.slots "$(slots)" "0:passphrase 2:recovery"
  hasnot back.crypttab "$(cat /etc/crypttab)" "tpm2-device"
  hasnot back.initramfs-crypttab "$(lsinitrd -f etc/crypttab 2>&1)" "tpm2-device"
  cryptsetup open --test-passphrase --key-file $pass "$luks" > /dev/null 2>&1; is back.passphrase-still-opens "exit $?" "exit 0"
  end;;
plain)
  say plain.journal info "$(journal)"
  j=$(silik disk --json 2> /dev/null); rc=$?
  is plain.disk "exit $rc; $(echo "$j" | row unlock)" "exit 0; ok: the passphrase or the recovery key, typed at every start"
  end;;
*)
  say "$stage.unknown" FAIL "no such stage"
  end;;
esac
