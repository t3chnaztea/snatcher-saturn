#!/bin/bash
set -eo pipefail
cd "$(dirname "$0")/.."
root="$PWD"
source "${SNATCHER_SONIC:-../sonic-cd-saturn}/tools/env.sh"
work="$root/build/stunner-probe"
mkdir -p "$work/cd" "$work/audio-tracks"
cp tools/stunner-probe/{Makefile,main.c} src/lightgun.{c,h} "$work/"
cd "$work"
gmake
core="$SATURN_PROJECT_ROOT/.deps/beetle-saturn"
cc -O2 -I"$core/libretro-common/include" -I"$core/mednafen/cdrom" \
  "$SATURN_PROJECT_ROOT/tools/iso_to_raw.c" "$core/mednafen/cdrom/lec.c" -o iso_to_raw
./iso_to_raw stunner-probe.iso stunner-probe.bin.tmp
./iso_to_raw --check-data stunner-probe.iso stunner-probe.bin.tmp
mv stunner-probe.bin.tmp stunner-probe.bin
printf 'FILE "stunner-probe.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n' > stunner-probe.cue
shasum -a 256 stunner-probe.bin stunner-probe.cue
