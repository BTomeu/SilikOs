#!/usr/bin/env bash
# w_compress.sh SYSTEM install|measure: the system's xz and zstd, one thread, default levels, on gen.py's CAN log
# (/data/blob.txt), to /dev/null; then the decompression of what each made. The input is read from the page cache
# (the warm-up run), so this is the compressor, not the disk.
. "$(dirname "$0")/lib.sh"
if [ "$phase" = install ]; then
  case "$pm" in
    apt) need xz xz-utils; need zstd zstd ;;
    *) need xz xz; need zstd zstd ;;
  esac
  exit 0
fi
mb=$(( $(stat -c %s /data/blob.txt) / 1000000 ))
mkdir -p /work/z
if have xz xz xz-compress xz-decompress; then
  ver=$(xz --version | head -1 | awk '{print $NF}')
  timed xz-compress "$system" --tool xz --version "$ver" --param "input_mb=$mb" -- "xz -T1 -c /data/blob.txt > /dev/null"
  xz -T1 -c /data/blob.txt > /work/z/blob.xz
  timed xz-decompress "$system" --tool xz --version "$ver" --param "input_mb=$mb" -- "xz -T1 -dc /work/z/blob.xz > /dev/null"
  rm -f /work/z/blob.xz
fi
if have zstd zstd zstd-compress zstd-decompress; then
  ver=$(zstd --version | grep -o 'v[0-9][0-9.]*' | head -1); ver=${ver#v}
  timed zstd-compress "$system" --tool zstd --version "$ver" --param "input_mb=$mb" -- "zstd -T1 -q -c /data/blob.txt > /dev/null"
  zstd -T1 -q -c /data/blob.txt > /work/z/blob.zst
  timed zstd-decompress "$system" --tool zstd --version "$ver" --param "input_mb=$mb" -- "zstd -q -dc /work/z/blob.zst > /dev/null"
  rm -f /work/z/blob.zst
fi
