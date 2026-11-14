#!/usr/bin/bash
# silikos-ci-rollback: the rollback test inside the virtual machine the CI installed (tests/install/rollback.sh;
# the plan of docs/ROLLBACK.md section 5, steps 1-6, 8 and 10). It runs at every start, one stage each, and says
# what it saw on the serial port like tests/install/check.sh:
#   SILIKOS-CI|<step>.<name>|ok or FAIL or info|<what was seen>      and SILIKOS-CI|DONE at the end.
# The stage is kept in /boot, which is not in the snapshot of / and so outlives the rollback:
#   1  normal start     the thin layout the installer made; silik snapshot create; the prune; packages downgraded on
#                       purpose, then the real update service, which must take its snapshot first; a kernel installed
#                       after it; the next start is that snapshot's own boot entry
#   2  the snapshot     / is the snapshot, nothing is updated there; `silik rollback` from it; next: the Revert entry
#   3  the Revert entry / is as before the update; `silik rollback finish` has run by itself; the default kernel
#   4  normal start     the default kernel runs with its modules; the updates wait; `silik update` ends the wait
# On the second installation (plain partitions, /etc/silikos-ci-plain): `silik snapshot` says "not available" and
# `silik rollback --packages` is the way back.
# Only in the CI's test installations. Written 13/11/2026, where nothing of LVM or a boot could be run: this script
# has not run yet (docs/STATUS.md).
out=/dev/ttyS0
# (each line starts on a line of its own: the kernel and systemd write to the same port)
# every line is also kept for this start (/run), and said once more at its end, numbered, when nothing else writes
# to the port, with their count: a line that one of the kernel's cut on the way is whole the second time, and the
# host knows how many there were (tests/install/rows.py). again: before every end and every restart.
rows=/run/silikci-rows; touch $rows
say() { local l; l=$(printf '%s|%s|%s' "$1" "$2" "$(echo "$3" | tr '\n|' ' /' | cut -c1-300)"); printf '%s\n' "$l" >> $rows; printf '\r\nSILIKOS-CI|%s\r\n' "$l" > $out; }
again() { local n=0 l; sleep 2; while IFS= read -r l; do n=$((n + 1)); printf '\r\nSILIKOS-CI-AGAIN|%s|%s\r\n' "$n" "$l" > $out; done < $rows; printf '\r\nSILIKOS-CI-ROWS|%s\r\n' "$n" > $out; : > $rows; }
is() { if [ "$2" = "$3" ]; then say "$1" ok "$2"; else say "$1" FAIL "saw '$2', wanted '$3'"; fi; }
has() { case "$2" in *"$3"*) say "$1" ok "$3";; *) say "$1" FAIL "no '$3' in: $2";; esac; }
finish() { say "$1" info "the test ends here"; again; printf '\r\nSILIKOS-CI|DONE\r\n' > $out; sync; sleep 3; systemctl poweroff; exit 0; }

PKGS="tzdata expat libxml2 sqlite-libs"     # small, with older versions in the base's repositories (seen 13/11/2026)
ver() { rpm -q --qf '%{NAME}-%{VERSION}-%{RELEASE} ' $PKGS 2>&1; }
downgrade() { local done_=""; for p in $PKGS; do dnf -y -q downgrade "$p" > /dev/null 2>&1 && done_="$done_ $p"; done; echo "$done_"; }
sets() { snapm snapset list --noheadings -o name,uuid,status 2> /dev/null; }             # "NAME UUID STATUS" a line
uuid_of() { sets | awk -v n="$1" '$1 == n { print $2 }'; }
newest_auto() { sets | awk '$1 ~ /^silikos-update\.[0-9]+$/ { print $1 }' | sort -t. -k2 -n | tail -1; }
# the boot menu's entry (its file's name without .conf: grub2's and grubby's id) that has ARG=UUID on its kernel line
entry_of() { grep -l -- "$1=$2" /boot/loader/entries/*.conf 2> /dev/null | head -1 | sed 's#.*/##; s#\.conf$##'; }
cond() { systemctl show -p ConditionResult --value "$1" 2>&1; }

# ---------------------------------------------------------------- the disk without LVM thin (plan step 10)
if [ -e /etc/silikos-ci-plain ]; then
  o=$(silik -q snapshot 2>&1); rc=$?
  has plain.snapshot-says "$o" "not available"
  is plain.snapshot-exit "exit $rc" "exit 1"
  o=$(silik -q snapshot create 2>&1); rc=$?
  has plain.create-refused "exit $rc: $o" "not on an LVM thin volume"
  has plain.create-alternative "$o" "silik rollback --packages"
  is plain.doctor "$(silik doctor system --json 2> /dev/null | python3 -c 'import json, sys; print(next(c["state"] for c in json.load(sys.stdin)["checks"] if c["id"] == "rollback"))' 2>&1)" warn
  did=$(downgrade)
  if [ -n "$did" ]; then say plain.downgraded ok "$did"; else say plain.downgraded FAIL "none of $PKGS could be downgraded"; fi
  old=$(ver)
  systemctl start silikos-update.service; rc=$?
  is plain.update "exit $rc $(systemctl show -p Result --value silikos-update.service)" "exit 0 success"
  new=$(ver)
  if [ "$new" != "$old" ]; then say plain.updated ok "$new"; else say plain.updated FAIL "still $old"; fi
  if [ -e /run/silikos/no-snapshot ]; then say plain.no-note FAIL "$(cat /run/silikos/no-snapshot)"; else say plain.no-note ok "no snapshot was due: nothing noted"; fi
  o=$(silik rollback --packages --yes 2>&1); rc=$?
  is plain.rollback-packages "exit $rc" "exit 0"
  is plain.packages-back "$(ver)" "$old"
  say plain.rollback-output info "$(echo "$o" | tail -3)"
  finish plain.end
fi

# ---------------------------------------------------------------- the thin disk
mountpoint -q /boot || mount /boot
S=/boot/silikos-ci
mkdir -p $S
stage=$(cat $S/stage 2> /dev/null || echo 1)

case $stage in
1)
  # step 1: what the installer's Automatic partitioning made (the test's kickstart names no scheme)
  root_src=$(findmnt -n -o SOURCE /)
  say layout.lvs info "$(lvs -a --noheadings -o lv_name,lv_attr,pool_lv,lv_size,lv_profile 2>&1 | tr -s ' ' | tr '\n' ';')"
  root_attr=$(lvs --noheadings -o lv_attr "$root_src" 2>&1 | tr -d ' ')
  pool=$(lvs --noheadings -o pool_lv "$root_src" 2> /dev/null | tr -d ' ')
  vg=$(lvs --noheadings -o vg_name "$root_src" 2> /dev/null | tr -d ' ')
  case "$root_attr" in
    V*) say layout.root-thin ok "$root_src is a thin volume ($root_attr) of the pool $vg/$pool";;
    *) say layout.root-thin FAIL "$root_src: lv_attr '$root_attr' is not a thin volume's: the installer's default scheme is not LVM thin";;
  esac
  if findmnt -n /home > /dev/null; then
    home_attr=$(lvs --noheadings -o lv_attr "$(findmnt -n -o SOURCE /home)" 2>&1 | tr -d ' ')
    case "$home_attr" in V*) say layout.home-thin ok "/home is a thin volume ($home_attr)";; *) say layout.home-thin FAIL "/home: lv_attr '$home_attr'";; esac
  else
    say layout.home-thin info "no /home volume on this disk (the installer makes one when 50 GiB are free)"
  fi
  swap_attr=$(lvs --noheadings -o lv_name,lv_attr "$vg" 2> /dev/null | awk '$1 == "swap" { print $2 }')     # (the installer names it swap)
  case "$swap_attr" in
    -*) say layout.swap ok "swap is a normal volume ($swap_attr), outside the pool";;
    "") say layout.swap info "no volume named swap in $vg: $(swapon --noheadings --show=NAME 2>&1 | tr '\n' ' ')";;
    *) say layout.swap FAIL "swap: lv_attr '$swap_attr'";;
  esac
  read -r vg_size vg_free <<< "$(vgs --noheadings --units b --nosuffix -o vg_size,vg_free "$vg" 2> /dev/null)"
  if [ -n "${vg_size:-}" ] && [ "$vg_size" -gt 0 ] 2> /dev/null; then
    pct=$((vg_free * 100 / vg_size))
    if [ "$pct" -ge 5 ]; then say layout.reserve ok "$pct % of the volume group $vg is free for the pool to grow (the installer's reserve)"
    else say layout.reserve FAIL "only $pct % of the volume group $vg is free: the pool cannot grow"; fi
  else
    say layout.reserve FAIL "vgs did not say the size of '$vg'"
  fi
  is layout.pool-profile "$(lvs --noheadings -o lv_profile "$vg/$pool" 2>&1 | tr -d ' ')" silikos-thin      # (the kickstart's %post)
  for p in snapm boom-boot; do if v=$(rpm -q $p 2>&1); then say layout.package-$p ok "$v"; else say layout.package-$p FAIL "$v"; fi; done
  is layout.trim "$(systemctl is-enabled fstrim.timer 2>&1)" enabled
  s=$(silik -q snapshot status 2>&1); rc=$?
  is layout.snapshot-status "exit $rc" "exit 0"
  echo "$s" | grep -E '^(▼|◆|\?)' | while read -r line; do say layout.status-row info "$line"; done
  is layout.doctor "$(silik doctor system --json 2> /dev/null | python3 -c 'import json, sys; print(next(c["state"] for c in json.load(sys.stdin)["checks"] if c["id"] == "rollback"))' 2>&1)" ok

  # step 2: a snapshot by hand
  t0=$(date +%s.%N)
  o=$(silik -q snapshot create ci-manual 2>&1); rc=$?
  t1=$(date +%s.%N)
  is snapshot.create "exit $rc" "exit 0"
  say snapshot.create-said info "$(echo "$o" | tail -2)"
  say snapshot.create-seconds info "$(echo "$t1 $t0" | awk '{ printf "%.1f", $1 - $2 }') s (a virtual machine of the CI: not a measure of a real disk)"
  has snapshot.snapm-list "$(sets | tr '\n' ';')" "ci-manual"
  has snapshot.lvs "$(lvs --noheadings -o lv_name,origin,lv_role 2>&1 | tr -s ' ' | tr '\n' ';')" "thinsnapshot"
  u=$(uuid_of ci-manual)
  if [ -n "$(entry_of snapm.snapset "$u")" ] && [ -n "$(entry_of snapm.revert "$u")" ]; then say snapshot.boot-entries ok "Snapshot $(entry_of snapm.snapset "$u"), Revert $(entry_of snapm.revert "$u")"
  else say snapshot.boot-entries FAIL "no entry with snapm.snapset=$u and snapm.revert=$u in /boot/loader/entries: $(ls /boot/loader/entries | tr '\n' ' ')"; fi
  has snapshot.boom-list "$(boom list 2>&1 | tr '\n' ';')" "$(uname -r)"
  # (boom's OS profile, which silik makes before the first snapshot: snapm's own way fails for the name "SilikOS")
  has snapshot.boom-profile "$(grep -h '^BOOM_OS_UNAME_PATTERN\|^BOOM_OS_NAME' /boot/boom/profiles/*.profile 2>&1 | tr '\n' ' ')" 'BOOM_OS_UNAME_PATTERN="el9"'
  say snapshot.boot-space info "$(df -h /boot | tail -1 | awk '{ print $4 " free of " $2 }'); the snapshots' kernel copies: $(du -sch /boot/boom/cache /boot/*.boom[0-9]* 2> /dev/null | tail -1 | cut -f1)"

  # step 8: the prune (seven more automatic snapshots, five are kept)
  for i in 1 2 3 4 5 6 7; do silik -q snapshot auto > /dev/null 2>&1; done
  is prune.kept "$(sets | grep -c '^silikos-update\.')" 5
  is prune.boot-entries "$(grep -l 'snapm\.snapset=' /boot/loader/entries/*.conf 2> /dev/null | wc -l) $(grep -l 'snapm\.revert=' /boot/loader/entries/*.conf 2> /dev/null | wc -l)" "6 6"   # five and ci-manual
  is prune.kernel-copies "$(ls /boot/boom/cache/*.img 2> /dev/null | wc -l)" 2      # one kernel and one initramfs, whatever the number of snapshots
  if [ -e /run/silikos/no-snapshot ]; then say prune.no-note FAIL "$(cat /run/silikos/no-snapshot)"; else say prune.no-note ok "every snapshot was made"; fi

  # step 3: packages downgraded on purpose, then the real update service: its snapshot comes first
  did=$(downgrade)
  if [ -n "$did" ]; then say update.downgraded ok "$did"; else say update.downgraded FAIL "none of $PKGS could be downgraded (no older version in the repositories?)"; fi
  ver > $S/old-versions                       # what the rollback must bring back
  last=$(newest_auto)
  systemctl start silikos-update.service; rc=$?
  is update.service "exit $rc $(systemctl show -p Result --value silikos-update.service)" "exit 0 success"
  j=$(journalctl -b -u silikos-update.service -o cat --no-pager 2>&1)
  ls_=$(echo "$j" | grep -n 'of / made before the update' | tail -1 | cut -d: -f1)
  lu=$(echo "$j" | grep -n -i 'updates have been applied\|Updates completed' | tail -1 | cut -d: -f1)
  if [ -n "$ls_" ] && [ -n "$lu" ] && [ "$ls_" -lt "$lu" ]; then say update.snapshot-first ok "the journal has the snapshot (line $ls_) before the update (line $lu)"
  else say update.snapshot-first FAIL "snapshot line '$ls_', update line '$lu': $(echo "$j" | tail -4)"; fi
  new=$(newest_auto)
  if [ -n "$new" ] && [ "$new" != "$last" ]; then say update.snapshot ok "$new"; else say update.snapshot FAIL "the newest is still '$last'"; fi
  if [ "$(ver)" != "$(cat $S/old-versions)" ]; then say update.updated ok "$(ver)"; else say update.updated FAIL "still $(ver)"; fi
  ver > $S/new-versions
  echo "$new" > $S/snapshot
  if [ -e /run/silikos/no-snapshot ]; then say update.no-note FAIL "$(cat /run/silikos/no-snapshot)"; else say update.no-note ok "the update has its snapshot"; fi
  # a kernel installed after the snapshot: the reverted package database will not know it, and installing it made
  # it the default boot entry. After the rollback it has no modules on /: `silik rollback finish` must take it out
  k=$(dnf -q repoquery --available --qf '%{version}-%{release}.%{arch}' kernel-core 2> /dev/null | grep -v "^$(uname -r)\$" | sort -V | head -1)
  if [ -n "$k" ] && dnf -y -q install "kernel-core-$k" > /dev/null 2>&1; then
    echo "$k" > $S/extra-kernel
    say update.another-kernel ok "kernel $k installed after the snapshot; the default is now $(grubby --default-kernel 2>&1)"
  else
    say update.another-kernel info "no other kernel version in the repositories (or it did not install): the finish step has no unknown kernel to remove"
  fi
  # the next start: the snapshot's own entry
  u=$(uuid_of "$new"); e=$(entry_of snapm.snapset "$u")
  if [ -z "$e" ]; then say update.snapshot-entry FAIL "no boot entry of the snapshot '$new' ($u)"; finish update.end; fi
  say update.snapshot-entry ok "$e"
  grub2-reboot "$e"
  echo 2 > $S/stage; sync
  again; systemctl reboot
  ;;
2)
  # step 4: started from the snapshot
  new=$(cat $S/snapshot)
  has snapshot-boot.kernel-line "$(cat /proc/cmdline)" "snapm.snapset="
  has snapshot-boot.root "$(findmnt -n -o SOURCE /)" "snapset"
  if findmnt -n /home > /dev/null; then
    case "$(findmnt -n -o SOURCE /home)" in *snapset*) say snapshot-boot.home FAIL "/home is a snapshot: $(findmnt -n -o SOURCE /home)";; *) say snapshot-boot.home ok "/home is the original: $(findmnt -n -o SOURCE /home)";; esac
  fi
  is snapshot-boot.packages "$(ver)" "$(cat $S/old-versions)"        # / as it was before the update
  systemctl start silikos-update.service 2> /dev/null
  is snapshot-boot.nothing-updated "$(cond silikos-update.service)" no
  is snapshot-boot.packages-after "$(ver)" "$(cat $S/old-versions)"
  o=$(silik -q snapshot create 2>&1); rc=$?
  has snapshot-boot.no-snapshot-of-a-snapshot "exit $rc: $o" "exit 1: silik: no snapshot of a snapshot"
  say snapshot-boot.desktop info "gdm is $(systemctl is-active gdm 2>&1)"
  # step 5: the rollback, asked from the snapshot's own start (what a person does when the system no longer starts)
  o=$(silik rollback --yes 2>&1); rc=$?
  is rollback.command "exit $rc" "exit 0"
  say rollback.said info "$(echo "$o" | grep '^silik:' | tail -2)"
  u=$(uuid_of "$new"); e=$(entry_of snapm.revert "$u")
  echo "$u" > $S/uuid
  if [ "$rc" != 0 ] || [ -z "$e" ]; then say rollback.revert-entry FAIL "exit $rc; the Revert entry of '$new' ($u): '$e'"; finish rollback.end; fi
  has rollback.next-start "$(grub2-editenv list 2>&1 | tr '\n' ' ')" "next_entry=$e"
  say rollback.set-status info "$(sets | awk -v n="$new" '$1 == n')"
  case "$(systemctl is-system-running 2>&1)" in
    stopping) say rollback.never-restarts FAIL "the system is stopping after silik rollback";;
    *) say rollback.never-restarts ok "silik rollback returned and nothing restarts by itself (the test restarts now)";;
  esac
  echo 3 > $S/stage; sync
  again; systemctl reboot
  ;;
3)
  # step 5, after the restart: started from the Revert entry
  new=$(cat $S/snapshot); u=$(cat $S/uuid)
  has revert-boot.kernel-line "$(cat /proc/cmdline)" "snapm.revert=$u"
  case "$(findmnt -n -o SOURCE /)" in *snapset*) say revert-boot.root FAIL "/ is still a snapshot: $(findmnt -n -o SOURCE /)";; *) say revert-boot.root ok "/ is $(findmnt -n -o SOURCE /)";; esac
  is revert-boot.packages "$(ver)" "$(cat $S/old-versions)"          # rpm -q says the old versions
  for i in $(seq 1 30); do sets | awk '{ print $1 }' | grep -qx "$new" || break; sleep 10; done
  if sets | awk '{ print $1 }' | grep -qx "$new"; then say revert-boot.merge FAIL "the snapshot set is still there: $(sets | awk -v n="$new" '$1 == n')"
  else say revert-boot.merge ok "the snapshot set $new is merged into / and gone"; fi
  is finish.service-ran "$(cond silikos-rollback-finish.service)" yes                 # by itself, because of this start's kernel line
  is finish.service "$(systemctl show -p Result --value silikos-rollback-finish.service) $(systemctl show -p ExecMainStatus --value silikos-rollback-finish.service)" "success 0"
  say finish.said info "$(journalctl -b -u silikos-rollback-finish.service -o cat --no-pager 2>&1 | grep -v '^\$' | tail -6 | tr '\n' ';')"
  if grep -ql "snapm\.\(revert\|snapset\)=$u" /boot/loader/entries/*.conf 2> /dev/null; then
    # (the service ran while the merge was still going on and left the entries: once more, by hand)
    say finish.second-run info "the entries of the merged snapshot were still there after the service: silik rollback finish again"
    silik -q rollback finish > /dev/null 2>&1
  fi
  is finish.entries-of-the-merged-snapshot "$(grep -l "snapm\.\(revert\|snapset\)=$u" /boot/loader/entries/*.conf 2> /dev/null | wc -l)" 0
  k=$(cat $S/extra-kernel 2> /dev/null)
  if [ -n "$k" ]; then
    if rpm -q "kernel-core-$k" > /dev/null 2>&1; then say finish.unknown-kernel FAIL "the reverted package database knows kernel-core-$k: / was not reverted"
    elif ls /boot/loader/entries/*-"$k".conf > /dev/null 2>&1 || [ -e "/boot/vmlinuz-$k" ]; then say finish.unknown-kernel FAIL "kernel $k is not installed any more and is still in /boot: $(ls /boot | grep -F "$k" | tr '\n' ' ')"
    else say finish.unknown-kernel ok "kernel $k, which the reverted packages do not know, left the boot menu and /boot"; fi
  fi
  dk=$(grubby --default-kernel 2>&1); kv=${dk##*/vmlinuz-}
  if rpm -q "kernel-core-$kv" > /dev/null 2>&1 && [ -d "/lib/modules/$kv/kernel" ]; then say finish.default-kernel ok "the default kernel $kv is installed and has its modules"
  else say finish.default-kernel FAIL "the default is '$dk': installed: $(rpm -q "kernel-core-$kv" 2>&1); /lib/modules/$kv/kernel: $([ -d "/lib/modules/$kv/kernel" ] && echo there || echo missing)"; fi
  miss=0; for f in /boot/loader/entries/*.conf; do l=$(awk '$1 == "linux" { print $2; exit }' "$f"); [ -e "/boot$l" ] || miss=$((miss + 1)); done
  is finish.entries-without-a-kernel "$miss" 0
  if [ -e /etc/silikos/update.hold ]; then say finish.updates-wait ok "/etc/silikos/update.hold: $(cat /etc/silikos/update.hold)"; else say finish.updates-wait FAIL "no /etc/silikos/update.hold: the automatic update would undo the rollback"; fi
  echo 4 > $S/stage; sync
  again; systemctl reboot
  ;;
4)
  # step 6: the start after the rollback, from the default entry
  kv=$(uname -r)
  case "$(cat /proc/cmdline)" in *snapm.*) say after.kernel-line FAIL "$(cat /proc/cmdline)";; *) say after.kernel-line ok "a normal start";; esac
  n=$(lsmod | wc -l)
  if rpm -q "kernel-core-$kv" > /dev/null 2>&1 && [ -d "/lib/modules/$kv/kernel" ] && [ "$n" -gt 5 ]; then say after.kernel ok "kernel $kv runs, installed, with its modules ($n loaded)"
  else say after.kernel FAIL "kernel $kv: installed: $(rpm -q "kernel-core-$kv" 2>&1); modules loaded: $n"; fi
  is after.packages "$(ver)" "$(cat $S/old-versions)"
  is after.entries-of-snapshots "$(grep -l 'snapm\.revert=' /boot/loader/entries/*.conf 2> /dev/null | wc -l)" "$(sets | wc -l)"   # one Revert entry for each snapshot that exists, none orphaned
  systemctl start silikos-update.service 2> /dev/null
  is after.updates-wait "$(cond silikos-update.service)" no
  has after.status-says "$(silik -q snapshot status 2>&1 | tr '\n' ';')" "wait since the rollback"
  # an update by hand ends the wait, and takes its snapshot first
  last=$(newest_auto)
  o=$(silik update 2>&1); rc=$?
  is after.update-by-hand "exit $rc" "exit 0"
  if [ -e /etc/silikos/update.hold ]; then say after.wait-ended FAIL "/etc/silikos/update.hold is still there"; else say after.wait-ended ok "the automatic updates go on"; fi
  is after.updated-again "$(ver)" "$(cat $S/new-versions)"
  new=$(newest_auto)
  if [ -n "$new" ] && [ "$new" != "$last" ]; then say after.snapshot-first ok "$new"; else say after.snapshot-first FAIL "no new snapshot before the update by hand (newest: '$last'): $(echo "$o" | grep -i snapshot | tail -2)"; fi
  finish after.end
  ;;
*)
  say stage FAIL "unknown stage '$stage'"
  finish stage.end
  ;;
esac
