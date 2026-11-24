"""Pack the credits display changes into the Saturn's 1 MiB of low work RAM."""
import hashlib
from itertools import groupby
from operator import itemgetter
from pathlib import Path
import struct
import sys

ORIGIN = 331080
WIDTHS = (32, 2, 2, 1)
LENGTHS = (65536, 128, 128, 32)
EXPECTED = "5572ae48ecfdc3d4bf805fa8350cc32ab2166353bc6011ed2ff08659a1752c27"


def changes(trace):
    position = 0
    while position < len(trace):
        high, low, area, offset = struct.unpack_from("=4H", trace, position)
        position += 8
        if area >= len(WIDTHS):
            raise ValueError("Invalid credits memory area")
        width = WIDTHS[area]
        payload = trace[position:position + width]
        if offset % width or offset + width > LENGTHS[area] or len(payload) != width:
            raise ValueError("Invalid credits display update")
        yield (high << 16 | low), area, offset, payload
        position += width


def prepare(work, output):
    """Index the shared 8x8 patterns; other updates fit a single SH-2 word."""
    tiles = {}
    events = bytearray()
    last = -1
    for frame, group in groupby(changes((work / "changes.bin").read_bytes()), itemgetter(0)):
        relative = frame - ORIGIN
        if not last < relative < 65535 or (last == -1 and relative != 0):
            raise ValueError("Invalid credits timeline")
        updates = list(group)
        events.extend(struct.pack(">HH", relative, len(updates)))
        for _, area, offset, payload in updates:
            key = area << 14 | offset // WIDTHS[area]
            if area == 0:
                value = tiles.setdefault(payload, len(tiles))
            else:
                value = int.from_bytes(payload, sys.byteorder)
            events.extend(struct.pack(">HH", key, value))
        last = relative
    patterns = bytearray()
    for tile in tiles:
        for word in struct.unpack("=16H", tile):
            patterns.extend(struct.pack(">H", word))
    header = struct.pack(">III", len(tiles), 12 + len(patterns), last)
    bank = header + patterns + events + struct.pack(">HH", 65535, 0)
    if len(bank) > 0x100000 or hashlib.sha256(bank).hexdigest() != EXPECTED:
        raise ValueError("Unexpected US credits graphics or timing")
    (output / "CREDITS.BIN").write_bytes(bank)
