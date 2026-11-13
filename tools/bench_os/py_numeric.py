#!/usr/bin/env python3
# py_numeric.py [N]: the numeric Python workload of the comparison between systems: a first-order low-pass filter
# and a running RMS over N samples of a made-up phase current (floats), then a sieve up to N (integers and lists).
# Pure Python, on purpose: it is the interpreter that is timed. Prints "checksum X", the same under every Python
# (IEEE doubles, no library function that could differ: the wave is made of integers).
import sys


def filtered(n):
    y = 0.0
    acc = 0.0
    peak = 0.0
    x = 12345
    for i in range(n):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        sample = ((i % 400) - 200) * 0.05 + (x >> 16) * 0.0001      # a triangle and noise
        y += 0.125 * (sample - y)
        acc += y * y
        if y > peak:
            peak = y
    return acc / n, peak


def sieve(n):
    flags = [True] * (n + 1)
    flags[0] = flags[1] = False
    i = 2
    while i * i <= n:
        if flags[i]:
            for j in range(i * i, n + 1, i):
                flags[j] = False
        i += 1
    return sum(flags)


def main(argv):
    n = int(argv[1]) if len(argv) > 1 else 10000000
    ms, peak = filtered(n)
    primes = sieve(n)
    print("mean square %.9f peak %.9f primes %d" % (ms, peak, primes))
    print("checksum %08x" % ((int(ms * 1e9) * 31 + int(peak * 1e9) * 7 + primes) & 0xFFFFFFFF))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
