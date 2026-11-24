"""Pack all streamed US Sega CD voices for native SCSP playback."""
import json
import os
from pathlib import Path
import struct

root = Path(__file__).resolve().parents[1]
source = Path(os.environ.get("SNATCHER_SOURCE", root.parent / "snatcher-uncut/private/extracted/segacd-usa"))
table = (source / "PCMLT_01.BIN").read_bytes()
lookup = bytes(((x & 127) if x & 128 else -(x & 127)) & 255 for x in range(256))
index = bytearray(2048 * 8)
# Each direct-output slot uses its own attenuation. Select the nearest SCSP
# total level to the RF5C164 envelope times that channel's linear pan gain.
levels = [(127-4*(level % 16)) / (127 * 2**(level//16)) for level in range(255)]
def attenuation(volume, pan):
    gain = volume * pan / (255 * 15)
    return min(range(255), key=lambda level: abs(levels[level]-gain)) if gain else 255

mix = bytearray([255]) * 4096
with (source / "PCMLD_01.BIN").open("rb") as samples, (root / "cd/VOICE.BIN").open("wb") as bank:
    bank.write(index)
    for sound in range(2048):
        _, mode, volume, pan, sector, count = struct.unpack_from(">4B2H", table, sound*8)
        if mode not in (2, 0x82):
            continue
        mix[sound*2] = attenuation(volume, pan >> 4)
        mix[sound*2+1] = attenuation(volume, pan & 15)
        samples.seek(sector*2048)
        raw = samples.read(count*2048)
        length = raw.index(255)
        if not 0 < length <= 0x100000:
            raise ValueError(f"Invalid streamed voice size for {sound}")
        struct.pack_into(">II", index, sound*8, bank.tell()//2048, length)
        bank.write(raw[:length].translate(lookup))
        bank.write(bytes(-length % 2048))
    bank.seek(0)
    bank.write(index)

(root / "cd/MIX.BIN").write_bytes(mix)

# The practice script selects resident bank 1 before the interactive routine.
# The second table addresses sounds within that bank's Sega CD RAM image.
def pack_resident(bank_id, sounds, filename, symbol):
    _, mode, _, _, sector, sectors = struct.unpack_from(">4B2H", table, bank_id*8)
    if mode != 1:
        raise ValueError(f"Expected resident bank {bank_id}")
    with (source / "PCMLD_01.BIN").open("rb") as disc:
        disc.seek(sector*2048)
        resident = disc.read(sectors*2048)
    packed = bytearray()
    records = []
    for sound in sounds:
        _, unit, volume, pan, pitch, address = struct.unpack_from(">4BHI", table, 0x4000+16*sound)
        start = address - 0x65000 + 16
        if not 0 <= start < len(resident):
            raise ValueError(f"Invalid sample address for {sound}")
        end = resident.index(255, start)
        if not 0 < end-start <= (0x20000 if bank_id==2 else 65535) or (pan>>4) != (pan&15):
            raise ValueError(f"Unsupported resident sample {sound}")
        records.append((len(packed) if filename else start, end-start, pitch, attenuation(volume,pan&15), unit))
        packed.extend(resident[start:end].translate(lookup))
        if len(packed)&1:
            packed.append(0)
    if filename:
        (root/"cd"/filename).write_bytes(packed)
    return f"static const struct range_sample {symbol}[] = {{\n" + "".join(
        "    {" + ", ".join(map(str,row)) + "},\n" for row in records) + "};\n"

(root/"build/range_pcm.h").write_text(
    pack_resident(29, range(49,56), None, "lisa_samples") +
    pack_resident(31, range(59,63), None, "ivan_samples") +
    pack_resident(3, (19,), None, "knock_samples") +
    pack_resident(18, (34,), None, "church_door_samples") +
    pack_resident(27, (44,), None, "garden_samples") +
    pack_resident(28, range(45,49), None, "factory_samples") +
    pack_resident(1, range(13,17), "RANGEPCM.BIN", "range_samples") +
    pack_resident(2, (17,), "STORM.BIN", "storm_samples") +
    pack_resident(6, (22,), "DRIP.BIN", "drip_samples") +
    pack_resident(8, (24,), "SHADOW.BIN", "shadow_samples") +
    pack_resident(7, (23,), "NAVPCM.BIN", "navigator_samples") +
    pack_resident(32, (63,), "GUNPCM.BIN", "blaster_samples") +
    pack_resident(35, range(71,74), None, "final_samples") +
    pack_resident(33, range(64,69), None, "ceiling_samples") +
    pack_resident(20, (36,), None, "taxi_samples") +
    pack_resident(16, (32,), "CARPCM.BIN", "canopy_samples"))

# The next INDEX 01 may include its own pregap. Stop at the last audio sector.
tracks=json.loads((root/"tools/retail-audio.json").read_text())
(root/"build/track_lengths.h").write_text("static const unsigned track_sectors[] = {"+
    ", ".join(str(tracks[str(i)]["sectors"]) for i in range(2,22))+"};\n")

# Preserve the original address layout for factory resident bank loads.
with (source/"PCMLD_01.BIN").open("rb") as samples:
    for bank_id, filename in [(5, "FACTPCM.BIN"), (20, "BODYPCM.BIN")]:
        _, mode, _, _, sector, sectors = struct.unpack_from(">4B2H", table, bank_id*8)
        if mode != 1 or sectors*2048 > 0x20000:
            raise ValueError(f"Unexpected factory PCM bank {bank_id}")
        samples.seek(sector*2048)
        bank = samples.read(sectors*2048)
        if len(bank) != sectors*2048:
            raise ValueError(f"Truncated factory PCM bank {bank_id}")
        (root/"cd"/filename).write_bytes(bank.translate(lookup))

# Additional story banks keep their original sample offsets. Embed each bank's
# sector span in the first sector so the SH-2 can read it in one transfer.
specialized = {1,2,5,6,7,8,16,20,32}
with (source/"PCMLD_01.BIN").open("rb") as samples, (root/"cd/RESIDENT.BIN").open("wb") as output:
    index = bytearray(2048)
    output.write(index)
    for bank_id in range(2048):
        _, mode, _, _, sector, count = struct.unpack_from(">4B2H",table,bank_id*8)
        if mode!=1 or bank_id in specialized: continue
        if bank_id>=512 or not 0<count<=64: raise ValueError(f"Unsupported resident bank {bank_id}")
        samples.seek(sector*2048)
        raw=samples.read(count*2048)
        if len(raw)!=count*2048: raise ValueError(f"Truncated resident bank {bank_id}")
        struct.pack_into(">HH",index,bank_id*4,output.tell()//2048,count)
        output.write(raw.translate(lookup))
    output.seek(0)
    output.write(index)
