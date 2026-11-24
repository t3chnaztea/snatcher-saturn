"""Pack track 11's original video-memory changes for CD-clocked Saturn playback."""
import struct


def pack_crash(work, output):
    # State contains VDP registers, CRAM, VSRAM, VRAM and the viewport palette.
    size = 65824 + 128
    previous = bytes(size)
    bank = bytearray()
    indices = {}
    movie = bytearray()
    old_fixes = None
    frames = 0
    last_sector = -1
    with (work / "crash.raw").open("rb") as source:
        while clock := source.read(2):
            sector = int.from_bytes(clock, "big")
            state = source.read(size)
            count = source.read(2)
            fixes = source.read(4 * int.from_bytes(count, "big"))
            if len(state) != size or len(count) != 2 or len(fixes) != 4 * int.from_bytes(count, "big"):
                raise ValueError("Truncated crash capture")
            if sector < last_sector:
                raise ValueError("Track 11 clock moved backwards")
            last_sector = sector
            frame = bytearray()
            changes = 0
            last = 0
            for i, (a, b) in enumerate(zip(memoryview(state).cast("Q"), memoryview(previous).cast("Q"))):
                if a == b or 4 <= i < 20:  # The sampled viewport palette supersedes CRAM.
                    continue
                if a not in indices:
                    indices[a] = len(indices)
                    bank.extend(state[8*i:8*i+8])
                gap = i - last
                if gap >= 128:
                    frame.append(128 | (gap >> 8))
                frame.append(gap & 255)
                frame.extend(struct.pack(">H", indices[a]))
                changes += 1
                last = i
            movie.extend(clock + struct.pack(">H", changes))
            movie.extend(frame)
            if fixes == old_fixes:
                movie.extend(b"\xff\xff")
            else:
                movie.extend(count + fixes)
                old_fixes = fixes
            previous = state
            frames += 1
    if frames != 6431 or last_sector != 7997:
        raise ValueError(f"Incomplete track 11 capture ({frames} frames, last sector {last_sector})")
    movie = struct.pack(">II", frames, len(bank)) + movie
    if len(movie) > 0x100000 or len(bank) > 0x60000:
        raise ValueError(f"Track 11 exceeds Saturn memory ({len(movie)} + {len(bank)} bytes)")
    (output / "CRASH11.BIN").write_bytes(movie)
    (output / "CRASHTIL.BIN").write_bytes(bank)
