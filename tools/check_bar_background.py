"""Verify the scope of the Outer Heaven restoration in two Saturn discs."""
import argparse
import hashlib
import struct
from pathlib import Path
import tempfile

from disc_files import unpack
from player_install import digest


def verify(stock_cue, restored_cue):
    with tempfile.TemporaryDirectory() as temp:
        stock, base_layout = unpack(stock_cue, Path(temp) / "retail")
        restored, alt_layout = unpack(restored_cue, Path(temp) / "restored")
    if stock.keys() != restored.keys():
        raise ValueError("The two discs contain different sets of files")
    changed = {name for name in stock if stock[name] != restored[name]}
    expected = {"DATA_O0.BIN", "A.BIN"}
    if "CLUBPAL.BIN" in stock:
        expected.add("CLUBPAL.BIN")
        # The same authored CRAM cycles address a different set of pixels.
        base_lights, alt_lights = stock["CLUBPAL.BIN"], restored["CLUBPAL.BIN"]
        if base_lights[:4] != alt_lights[:4] or base_lights[6:500] != alt_lights[6:500]:
            raise ValueError("The option changed the authored lighting program")
        for lights in (base_lights, alt_lights):
            pixel_count = int.from_bytes(lights[4:6], "big")
            if len(lights) != 500 + pixel_count * 4:
                raise ValueError("Invalid club lighting pixel table")
            last = -1
            for offset, color in struct.iter_unpack(">HH", lights[500:]):
                if not last < offset < 192*128 or color >= 64:
                    raise ValueError("Invalid club lighting pixel")
                last = offset
    if changed != expected:
        raise ValueError(f"Unexpected file differences: {sorted(changed)}")
    if hashlib.sha1(stock["DATA_O0.BIN"]).hexdigest() != "946b60d71918482203fe6b9c1f1929f7eab443a2":
        raise ValueError("Unexpected US club artwork")
    if hashlib.sha256(restored["DATA_O0.BIN"]).hexdigest() != "e3f95f273eb6128a3b0121dc110d00235326b1cc22c88c13eb204f269a8e5389":
        raise ValueError("Unexpected restored club artwork")
    if len(base_layout.tracks) != 21 or len(alt_layout.tracks) != 21:
        raise ValueError("Expected two mixed-mode Saturn discs")
    for base, alt in zip(base_layout.tracks[1:], alt_layout.tracks[1:]):
        def fingerprint(track):
            size = (track.end - track.start) * 2352
            return (track.number, track.indices[1] - track.start, size,
                    digest(track.file, start=track.start * 2352, length=size))
        if fingerprint(base) != fingerprint(alt):
            raise ValueError(f"Audio differs on track {base.number}")
    print(f"Verified {len(stock)} disc files and 20 audio tracks. Changed files: {', '.join(sorted(changed))}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("retail_cue", type=Path)
    parser.add_argument("restored_cue", type=Path)
    args = parser.parse_args()
    verify(args.retail_cue, args.restored_cue)
