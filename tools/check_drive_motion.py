"""Reproduce the fixed factory-flight motion table from its retail checkpoint."""
import argparse
from pathlib import Path
import os
import shlex
import struct
import subprocess
import tempfile
import zlib

root=Path(__file__).resolve().parents[1]
uncut=root.parent/"snatcher-uncut"
sonic=root.parent/"sonic-cd-saturn"
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("cockpit",type=Path)
args=parser.parse_args()
palette={}
shots=[]
# One-based boundaries observed at SUBCODE's queue head (0x9b40).
# Start track 20, wait for object 32, change scene, wait for the
# track to end, then wait for object 18. SP07 starts the landing.
segments=[(504,596),(596,1018),(1023,2467),(2467,2500),(2632,2902)]
with tempfile.TemporaryDirectory() as tmp:
    work=Path(tmp)
    flags=shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","libpng"],text=True))
    subprocess.run(["cc","-O2","-I"+str(uncut/"tools/harness"),"-I"+str(sonic/".deps/beetle-saturn/libretro-common/include"),
                    root/"tools/drive_trace.c",*flags,"-o",work/"runner"],check=True)
    pad=work/"drive.pad"
    pad.write_text("60 62 100\n160 162 20\n250 252 100\n")
    trace=work/"vdp.bin"
    env={k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env.update(SNATCHER_PAD="genesis3",SNATCHER_DRIVE_TRACE=str(trace))
    subprocess.run([work/"runner",uncut/".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib",uncut/"private/bios",
                    work,uncut/"private/discs/segacd-usa/Snatcher.cue","2902",work/"end.png",pad,args.cockpit.resolve()],
                   env=env,check=True,capture_output=True)
    raw=trace.read_bytes()
for start,stop in segments:
    rows=[]
    for frame in range(start,stop):
        d=raw[(frame-1)*932:frame*932]
        index=palette.setdefault(d[32:160],len(palette))
        va,vb=struct.unpack_from("<HH",d,160)
        sprites=[]
        k=0
        while True:
            y,size,tile,x=struct.unpack_from("<4H",d,288+8*k)
            sprites.append(struct.pack(">hhBH",(x&511)-128,(y&511)-128,size>>8&15,tile))
            k=size&127
            if not k: break
            if len(sprites)>=80: raise ValueError("Invalid sprite chain")
        value=struct.pack(">BhhB",index,va,vb,len(sprites))+b"".join(sprites)
        if rows and rows[-1][1]==value: rows[-1][0]+=1
        else: rows.append([1,value])
    shots.append(struct.pack(">H",len(rows))+b"".join(struct.pack(">H",n)+v for n,v in rows))
table=bytes([len(palette)])+b"".join(struct.pack(">64H",*struct.unpack("<64H",p)) for p in palette)+b"".join(shots)
if table!=zlib.decompress((root/"tools/drive-motion.z").read_bytes()):
    raise SystemExit("Motion differs from the retail checkpoint used for the factory trip")
print(f"Reproduced {len(table):,} bytes of factory motion from the Sega CD")
