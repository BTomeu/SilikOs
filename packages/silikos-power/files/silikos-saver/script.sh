#!/usr/bin/bash
# silikos-saver: what the base's powersave leaves out on a laptop. tuned runs this with `start` when the profile is
# set and `stop` when it is left; stop puts back exactly what start changed (the list in /run/tuned).
#
# - PCI devices: power/control auto (the kernel may power an idle device down; the kernel's default is on), except
#   the devices of the drivers mei_me, nouveau and radeon (TLP 1.5.0's default list, RUNTIME_PM_DRIVER_DENYLIST).
# - USB devices: power/control auto (the kernel's default is on for everything but hubs), except input devices,
#   audio devices and printers (interface classes 03, 01, 07: TLP 1.5.0's defaults), and except a disk the running
#   system is using (a mounted file system, swap, a volume made on it): with the system itself on an external disk,
#   a bridge that wakes badly would take the system with it.
# - Wi-Fi: power save on, through iw, where it was off.
# A device plugged in later keeps the kernel's default until the profile is set again.
# SILIK_SYSFS, SILIK_PROCFS, SILIK_SAVER_STATE and TUNED_FUNCTIONS are for the tests (a made-up /sys and /proc).

. "${TUNED_FUNCTIONS:-/usr/lib/tuned/functions}"

SYS=${SILIK_SYSFS:-/sys}
PROC=${SILIK_PROCFS:-/proc}
STATE=${SILIK_SAVER_STATE:-/run/tuned/silikos-saver}

# allow FILE: `auto` where the file says `on`; the file is noted, to put `on` back
allow() {
    [ -w "$1" ] || return 0
    [ "$(cat "$1" 2>/dev/null)" = on ] || return 0
    echo auto > "$1" 2>/dev/null && echo "$1" >> "$STATE.control"
    return 0
}

# usb_kept DEVICE: it has an audio, input or printer interface
usb_kept() {
    local c
    for c in "$1"/*:*/bInterfaceClass; do
        [ -r "$c" ] || continue
        case "$(cat "$c")" in 01|03|07) return 0 ;; esac
    done
    return 1
}

# usb_disk_in_use DEVICE: a disk on it (usb-storage or uas: DEVICE/INTERFACE/hostN/targetN:.../N:.../block/NAME) or
# one of its partitions is mounted, is swap, or has a volume made on it (LVM, LUKS: its holders)
usb_disk_in_use() {
    local b p n
    for b in "$1"/*:*/host*/target*/*/block/*; do
        [ -d "$b" ] || continue
        for p in "$b" "$b"/*; do
            [ -e "$p/dev" ] || continue          # the disk itself and its partitions
            n=$(basename "$p")
            [ -z "$(ls -A "$p/holders" 2>/dev/null)" ] || return 0
            grep -qs "^/dev/$n " "$PROC/self/mounts" "$PROC/swaps" && return 0
        done
    done
    return 1
}

wifi_interfaces() {
    local d
    for d in "$SYS"/class/net/*; do
        [ -e "$d/wireless" ] || [ -e "$d/phy80211" ] || continue
        basename "$d"
    done
}

start() {
    local d i
    mkdir -p "$(dirname "$STATE")"
    : > "$STATE.control"
    : > "$STATE.wifi"
    for d in "$SYS"/bus/pci/devices/*; do
        [ -e "$d/power/control" ] || continue
        case "$(basename "$(readlink -f "$d/driver" 2>/dev/null)")" in mei_me|nouveau|radeon) continue ;; esac
        allow "$d/power/control"
    done
    for d in "$SYS"/bus/usb/devices/*; do
        [ -e "$d/idVendor" ] || continue        # a device, not one of its interfaces
        usb_kept "$d" && continue
        usb_disk_in_use "$d" && continue
        allow "$d/power/control"
    done
    if command -v iw >/dev/null 2>&1; then
        for i in $(wifi_interfaces); do
            case "$(iw dev "$i" get power_save 2>/dev/null)" in
                *off) iw dev "$i" set power_save on 2>/dev/null && echo "$i" >> "$STATE.wifi" ;;
            esac
        done
    fi
    return 0
}

stop() {
    local f i
    if [ -r "$STATE.control" ]; then
        while read -r f; do
            [ -w "$f" ] && echo on > "$f" 2>/dev/null
        done < "$STATE.control"
    fi
    if [ -r "$STATE.wifi" ]; then
        while read -r i; do
            iw dev "$i" set power_save off 2>/dev/null
        done < "$STATE.wifi"
    fi
    rm -f "$STATE.control" "$STATE.wifi"
    return 0
}

process $@
