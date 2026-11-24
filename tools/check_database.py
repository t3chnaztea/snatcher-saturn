"""Compare retail and database-date Saturn packages to the accepted disc assets."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
uncut = root.parent / "snatcher-uncut"
sys.path.insert(0, str(uncut / "tools"))
from player_install import parse_cue, digest

from disc_files import read_extent, unpack

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("retail", type=Path)
parser.add_argument("dates", type=Path)
args = parser.parse_args()
manifest = json.loads((root / "tools/retail-extents.json").read_text())
with tempfile.TemporaryDirectory() as temp:
    retail, rl = unpack(args.retail, Path(temp)/"retail")
    dates, dl = unpack(args.dates, Path(temp)/"dates")
    assert retail.keys() == dates.keys()
    changed = {name for name in retail if retail[name] != dates[name]}
    assert changed == {"SP04.BIN", "SP05.BIN"}, changed
    for n in range(39):
        name = f"SP{n:02}.BIN"
        stock = (uncut / "private/extracted/segacd-usa" / name).read_bytes()
        assert hashlib.sha1(stock).hexdigest() == manifest[name]["sha1"]
        code, text = struct.unpack_from(">II", retail[name])
        assert len(retail[name]) == 8 + code + text
        assert retail[name][8+code:] == stock[0x3800:]
        if name in changed:
            row = manifest[name]
            accepted = read_extent(uncut / "dist/Snatcher Uncut (USA).bin", row["lba"], row["size"])
            assert dates[name][:8+code] == retail[name][:8+code]
            assert dates[name][8+code:] == accepted[0x3800:]
    bank = retail["VOICE.BIN"]
    mix = retail.get("MIX.BIN")  # V0.009 and later store a per-channel gain table.
    if mix is not None:
        assert len(mix) == 4096
    def slot_gain(level):
        return (1 - (level % 16)*4/127) * 2**-(level//16) if level < 255 else 0

    lookup = bytes(((i & 127) if i >= 128 else (256 - i)) % 256 for i in range(256))
    source = uncut / "private/extracted/segacd-usa"
    table = (source / "PCMLT_01.BIN").read_bytes()
    voices = 0
    with (source / "PCMLD_01.BIN").open("rb") as voice_data:
        for name, bank_id, sounds in [("RANGEPCM.BIN", 1, range(13,17)), ("DRIP.BIN", 6, (22,)), ("STORM.BIN", 2, (17,)),
                                      ("NAVPCM.BIN", 7, (23,)), ("GUNPCM.BIN", 32, (63,)), ("CARPCM.BIN", 16, (32,))]:
            if name not in retail:
                continue
            _, _, _, _, sector, sectors = struct.unpack_from(">4B2H", table, bank_id*8)
            assert table[bank_id*8+1] == 1
            voice_data.seek(sector*2048)
            resident = voice_data.read(sectors*2048)
            expected = bytearray()
            for i in sounds:
                addr, = struct.unpack_from(">I",table,0x4000+i*16+6)
                start = addr-0x65000+16
                samples = resident[start:resident.index(255,start)]
                expected.extend(samples.translate(lookup))
                expected.extend(bytes(len(samples)%2))
            assert retail[name] == expected
        for name, bank_id in [("FACTPCM.BIN", 5), ("BODYPCM.BIN", 20)]:
            if name in retail:
                _, mode, _, _, sector, count = struct.unpack_from(">4B2H", table, bank_id*8)
                assert mode == 1
                voice_data.seek(sector*2048)
                assert retail[name] == voice_data.read(count*2048).translate(lookup)
        if "RESIDENT.BIN" in retail:
            resident = retail["RESIDENT.BIN"]
            expected_sector = 1
            for bank_id in range(512):
                location, size = struct.unpack_from(">HH",resident,4*bank_id)
                _, mode, _, _, sector, count = struct.unpack_from(">4B2H",table,8*bank_id)
                if mode!=1 or bank_id in {1,2,5,6,7,8,16,20,32}:
                    assert (location,size)==(0,0)
                    continue
                assert (location,size)==(expected_sector,count)
                voice_data.seek(sector*2048)
                assert resident[location*2048:(location+size)*2048]==voice_data.read(size*2048).translate(lookup)
                expected_sector+=size
            assert len(resident)==expected_sector*2048
        for i in range(2048):
            offset, length = struct.unpack_from(">II", bank, i*8)
            _, mode, volume, pan, sector, count = struct.unpack_from(">4B2H", table, i*8)
            if mode not in (2, 0x82):
                assert (offset, length) == (0, 0)
                continue
            voice_data.seek(sector*2048)
            if mix is not None:
                for channel, nibble in enumerate((pan >> 4, pan & 15)):
                    level = mix[2*i+channel]
                    target = volume*nibble/(255*15)
                    error = abs(slot_gain(level)-target)
                    assert error <= min(abs(slot_gain(k)-target) for k in range(256)) + 1e-12
            original_pcm = voice_data.read(count*2048).split(b"\xff", 1)[0]
            assert length == len(original_pcm)
            assert bank[offset*2048:offset*2048+length] == original_pcm.translate(lookup)
            voices += 1
    assert voices == 1162
    original = parse_cue(uncut / "private/discs/segacd-usa/Snatcher.cue")
    for group in zip(original.tracks[1:], rl.tracks[1:], dl.tracks[1:]):
        assert len({(t.number, t.indices[1]-t.start, t.end-t.start) for t in group}) == 1
        assert len({digest(t.file, start=t.start*2352, length=(t.end-t.start)*2352)
                    for t in group}) == 1
print("39 retail script pools verified; exactly 2 changed pools match Uncut; 1,162 streamable PCM resources and all 20 audio tracks match.")
