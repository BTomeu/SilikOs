#!/bin/sh
# the firmware built from nothing; its hash; what it says about when it was built
set -e
cmake --fresh -S . -B build > /dev/null
cmake --build build --clean-first > /dev/null
sha256sum build/fw.elf
strings -a build/fw.elf | grep -o "built [A-Z].*"
