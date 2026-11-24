"""Extract the US opening display program from the verified Sega CD track."""
import ctypes
import ctypes.util
import hashlib
import os
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile

from prepare_credits import changes, LENGTHS, WIDTHS
from prepare_plaza import add_retail_toc, ROOT, SONIC, UNCUT

# The second bank loads during the black cut between CD tracks 3 and 5.
PARTS = ((6170, 14249), (14250, 33170))
BANK_LIMIT = 0xc0000


def dedication_changes(trace, raster):
    """Replace the raster interrupt with the same final pixels on a Saturn cell plane."""
    first, last = 7520, 8060
    row_format = struct.Struct("=258H")
    rows = list(row_format.iter_unpack(raster))
    if len(rows) < 224 or [(r[0], r[1]) for r in rows[:224]] != [(first, y) for y in range(224)]:
        raise ValueError("Incomplete opening dedication capture")
    colors = sorted({color for row in rows for color in row[2:]})
    if not colors or colors[0] != 0 or len(colors) > 16:
        raise ValueError("Unexpected dedication palette")
    indices = {color: index for index, color in enumerate(colors)}
    original = [bytearray(n) for n in LENGTHS]
    source = iter(changes(trace))
    for event in source:
        frame, kind, pos, data = event
        if frame >= first:
            break
        original[kind][pos:pos + len(data)] = data
        yield event

    def difference(frame, before, after):
        for kind, width in enumerate(WIDTHS):
            for pos in range(0, LENGTHS[kind], width):
                data = after[kind][pos:pos + width]
                if data != before[kind][pos:pos + width]:
                    yield frame, kind, pos, bytes(data)

    # Keep unused retail RAM in place so restoration fits in the same CD bank.
    display = [bytearray(data) for data in original]
    display[0][:897 * 32] = bytes(897 * 32)
    display[0][0xfe00:0xfe08] = bytes(8)
    display[2][:4] = bytes(4)
    for register, value in ((1, 0x64), (2, 0x38), (4, 7), (5, 0x7f), (13, 0x3e), (16, 0x10)):
        display[3][register] = value
    for index, color in enumerate(colors):
        struct.pack_into("=H", display[1], 2 * index, color)
    for cell in range(32 * 28):
        struct.pack_into("=H", display[0], 0xe000 + 2 * cell, 1 + cell)
    yield from difference(first, original, display)
    for frame, y, *pixels in rows:
        if not first <= frame <= last or y >= 224:
            raise ValueError("Invalid dedication row")
        for col in range(32):
            pattern = (1 + (y // 8) * 32 + col) * 32
            pos = pattern + (y % 8) * 4
            line = [indices[p] for p in pixels[col * 8:col * 8 + 8]]
            data = struct.pack("=2H", *((a << 12) | (b << 8) | (c << 4) | d
                                       for a, b, c, d in (line[:4], line[4:])))
            if display[0][pos:pos + 4] != data:
                display[0][pos:pos + 4] = data
                yield frame, 0, pattern, bytes(display[0][pattern:pattern + 32])
    while event[0] <= last:
        _, kind, pos, data = event
        original[kind][pos:pos + len(data)] = data
        event = next(source)
    yield from difference(last + 1, display, original)
    yield event
    yield from source


def pack(trace, destination, raster):
    library = ctypes.util.find_library("lz4")
    if not library:
        raise ValueError("The prologue extractor requires liblz4")
    lz4 = ctypes.CDLL(library)
    state = [bytearray(n) for n in LENGTHS]
    banks = [bytearray() for _ in PARTS]
    expected = ("95709cda83ff6086bbec1d533d525a751a3de22dca830db3c2e084d47e2c7d5e",
                "6b5322615425c477c36557fb48498a8ecc2cf352366af2b13a5dbbf102c7619c")
    hashes = [hashlib.sha256() for _ in PARTS]
    chunk = bytearray()
    part = -1
    last_frame = None

    def flush():
        if not chunk:
            return
        hashes[part].update(chunk)
        scratch = ctypes.create_string_buffer(lz4.LZ4_compressBound(len(chunk)))
        size = lz4.LZ4_compress_HC(bytes(chunk), scratch, len(chunk), len(scratch), 12)
        if not size:
            raise ValueError("Could not compress opening display data")
        banks[part].extend(struct.pack(">HH", size, len(chunk)))
        banks[part].extend(scratch.raw[:size])
        if size % 2:
            banks[part].append(0)
        chunk.clear()

    def write(frame, area, offset, value):
        nonlocal last_frame
        if frame != last_frame:
            if len(chunk) >= 12288:
                flush()
            chunk.extend(struct.pack(">HH", 65535, frame - PARTS[part][0]))
            last_frame = frame
        if len(chunk) + 34 > 16384:
            flush()
        chunk.extend(struct.pack(">H", area << 14 | offset // WIDTHS[area]))
        if area == 0:
            chunk.extend(struct.pack(">16H", *struct.unpack("=16H", value)))
        elif area == 3:
            chunk.extend(struct.pack(">H", value[0]))
        else:
            chunk.extend(struct.pack(">H", struct.unpack("=H", value)[0]))

    for frame, area, offset, value in dedication_changes(trace, raster):
        if frame > PARTS[-1][1]:
            break
        if part + 1 < len(PARTS) and frame >= PARTS[part + 1][0]:
            flush()
            part += 1
            for kind, bank in enumerate(state):
                width = WIDTHS[kind]
                for pos in range(0, len(bank), width):
                    write(PARTS[part][0], kind, pos, bank[pos:pos + width])
        if part >= 0:
            write(frame, area, offset, value)
        state[area][offset:offset + len(value)] = value
    flush()
    for number, (bounds, bank) in enumerate(zip(PARTS, banks)):
        if hashes[number].hexdigest() != expected[number]:
            raise ValueError(f"Unexpected US opening display data in bank {number}")
        payload = struct.pack(">4sII", b"PRO1", *bounds) + bank
        if not bank or len(payload) > BANK_LIMIT:
            raise ValueError("Opening display bank does not fit Saturn low RAM")
        (destination / f"PRO{number}.BIN").write_bytes(payload)


def prepare():
    source = Path(os.environ.get("SNATCHER_TRACK1", UNCUT / "private/extracted/segacd-usa/_track01.raw"))
    with tempfile.TemporaryDirectory(dir=ROOT / "build") as tmp:
        work = Path(tmp)
        remaining = 56014 * 2352
        with source.open("rb") as src, (work / "disc.bin").open("wb") as dst:
            while remaining:
                data = src.read(min(remaining, 1 << 20))
                if not data:
                    raise ValueError("Incomplete US opening data track")
                dst.write(data)
                remaining -= len(data)
        cue = work / "disc.cue"
        cue.write_text('FILE "disc.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n')
        add_retail_toc(work)
        pad = work / "start.pad"
        pad.write_text("5430 5440 2\n5520 5530 1\n5610 5620 8\n6030 6040 8\n6150 6160 8\n")
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "libpng"], text=True))
        subprocess.run(["cc", "-O2", "-I" + str(UNCUT / "tools/harness"),
                        "-I" + str(SONIC / ".deps/beetle-saturn/libretro-common/include"),
                        ROOT / "tools/render_credits.c", *flags, "-o", work / "capture"], check=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith("SNATCHER_")}
        env.update(SNATCHER_PAD="genesis3", SNATCHER_DISPLAY_FIRST="5800")
        subprocess.run([work / "capture", UNCUT / ".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib",
                        UNCUT / "private/bios", work, cue, "33170", work / "end.png", pad],
                       cwd=work, env=env, check=True)
        trace = (work / "changes.bin").read_bytes()
        pack(trace, ROOT / "cd", (work / "dedication.rows").read_bytes())


if __name__ == "__main__":
    prepare()
