#!/bin/bash
set -eo pipefail
cd "$(dirname "$0")/.."
export SNATCHER_UNCUT="${SNATCHER_UNCUT:-$(cd ../snatcher-uncut && pwd)}"
sonic_root="${SNATCHER_SONIC:-../sonic-cd-saturn}"
source "$sonic_root/tools/env.sh"
mkdir -p build/cd-block
cp "$sonic_root/build/cd-block/cd-block_cmds.c" "$sonic_root/build/cd-block/cd-block-internal.h" "$sonic_root/src/cd_status.h" build/cd-block/
"$SNATCHER_UNCUT/.venv/bin/python" tools/prepare_reception.py
python3 tools/prepare_script.py
python3 tools/prepare_voice.py
python3 tools/prepare_fm.py
python3 tools/prepare_plaza.py
python3 tools/prepare_prologue.py
mkdir -p build/sound
cp "$sonic_root"/build/feedback/ponesound.{c,h} "$sonic_root/src/sound_bus.h" "$sonic_root/build/sound-driver/driver.bin" build/sound/
gmake
mkdir -p dist/bin-cue
cc -O2 -I"$sonic_root/.deps/beetle-saturn/libretro-common/include" \
    -I"$sonic_root/.deps/beetle-saturn/mednafen/cdrom" \
    "$sonic_root/tools/iso_to_raw.c" "$sonic_root/.deps/beetle-saturn/mednafen/cdrom/lec.c" \
    -o build/iso_to_raw
out=dist/bin-cue/snatcher-saturn
build/iso_to_raw dist/snatcher-saturn.iso "$out.bin.tmp"
build/iso_to_raw --check-data dist/snatcher-saturn.iso "$out.bin.tmp"
mv "$out.bin.tmp" "$out.bin"
printf 'FILE "snatcher-saturn.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n' > "$out.cue"
