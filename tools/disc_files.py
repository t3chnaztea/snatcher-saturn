"""Read the Saturn package filesystem for host-side comparisons."""
from pathlib import Path
import subprocess
import sys

uncut = Path(__file__).resolve().parents[2]/"snatcher-uncut"
sys.path.insert(0,str(uncut/"tools"))
from player_install import parse_cue

def read_extent(track, sector, size):
    with track.open("rb") as f:
        f.seek(sector * 2352)
        raw = f.read(((size + 2047) // 2048) * 2352)
    return b"".join(raw[i+16:i+2064] for i in range(0, len(raw), 2352))[:size]

def unpack(cue, output):
    layout = parse_cue(cue)
    first = layout.tracks[0]
    iso = output.with_suffix(".iso")
    iso.write_bytes(read_extent(first.file, first.start, (first.end-first.start)*2048))
    subprocess.run(["xorriso", "-osirrox", "on", "-indev", iso, "-extract", "/", output],
                   check=True, capture_output=True)
    return {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}, layout
