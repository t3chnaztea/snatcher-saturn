"""Reduce a retail microscope VDP trace to palette, scrolling and sprite commands.

The upper viewport and lower portrait use different palettes within one frame.
Pass two traces made by drive_trace.c from the same retail checkpoint. For the
upper trace, snapshot CRAM at scanline 48 in Genesis Plus GX's render_line().
Expose that 128-byte copy as scan_palette and set SNATCHER_SCAN_UPPER=1 for
the upper trace. The lower trace reads CRAM after the completed frame. Both
runs start at Investigate with Gibson highlighted. At frame 90 press Down.
For hair, confirm at 290. For skin, press Down at 290 and confirm at 490.
Hold each input for nine frames. The return sequences use the two controller scripts from the retail natural run, checkpoints 1074 and 1075, starting from checkpoint 1073.
"""
import argparse
from pathlib import Path
import struct
import zlib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("scene", choices=["hair","skin","organic","return0","return1","return2","return3"])
parser.add_argument("upper", type=Path)
parser.add_argument("lower", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
top, bottom = args.upper.read_bytes(), args.lower.read_bytes()
start, stop = {"hair":(352,3438),"skin":(551,3205),"organic":(742,2782),"return0":(3657,3950),"return1":(4485,4699),"return2":(4704,5838),"return3":(5846,7911)}[args.scene]
palettes, poses = {}, []
for frame in range(start, stop):
    offset = (frame-1)*932
    upper = top[offset:offset+932]
    lower = bottom[offset:offset+932]
    if len(upper)!=932 or upper[160:]!=lower[160:]:
        raise ValueError(f"Traces disagree at frame {frame}")
    def palette(data):
        return palettes.setdefault(data[32:160],len(palettes))
    va,vb = struct.unpack_from("<HH", upper, 160)
    ha,hb = struct.unpack_from("<HH", upper, 928)
    actors = []
    slot = 0
    for _ in range(80):
        y,link,word,x = struct.unpack_from("<4H", upper, 288+8*slot)
        x,y = (x&511)-128,(y&511)-128
        size = link>>8&15
        actors.append(struct.pack(">hhBH",x,y,size,word))
        slot = link&127
        if not slot: break
    else:
        raise ValueError(f"Invalid sprite list at frame {frame}")
    row = struct.pack(">BB4HB",palette(upper),palette(lower),va,vb,ha,hb,len(actors))+b"".join(actors)
    if poses and poses[-1][1]==row: poses[-1][0]+=1
    else: poses.append([1,row])
table = bytes([len(palettes)]) + b"".join(struct.pack(">64H",*struct.unpack("<64H",p)) for p in palettes)
table += struct.pack(">H",len(poses))+b"".join(struct.pack(">H",frames)+row for frames,row in poses)
args.output.write_bytes(zlib.compress(table,9))
