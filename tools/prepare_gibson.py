"""Encode the door opening and room dissolve from the player's DATA_G0."""
import hashlib
import struct
from pathlib import Path

# The two stage controllers signal the story VM at the boundary between clips.
def pack_gibson(work, output, second_visit=False):
    maps=(work/"frames.raw").read_bytes()
    bank=(work/"tiles.raw").read_bytes()
    if len(maps)!=(301 if second_visit else 230)*768 or len(bank)%128:
        raise ValueError("Incomplete Gibson house capture")
    clips=(
        (0,124,"GDOOR.BIN","fee6ab8b8a01b12953e4af3397a1a3aec4c130d3bc7aee17d6cad04a400164cc",
         "b28f48e07f2b94f73ef2f6ec5394b8a3811d5864d445dfc7bfda090f202a44ab"),
        (124,230,"GENTRY.BIN","a37f4cbc2321dceaf2d3b53ef5a9ddc9227d2d68272adb68f0d6a933759e0a1a",
         "d0f16f473cc27269abc57446f7bc12695c4f6879748dfbddd70d0394cf5b41ea"))
    if second_visit:
        opened="caca3ab8175dffe3030619ad29220a00f5301e062cdf7225a7059408fd0a4eb7"
        clips=((43,167,"G2DOOR.BIN",clips[0][3],opened),
               (167,273,"G2ENTRY.BIN",opened,"f2a75f4f37228f98910c6f7d52fb9ece865c64b9e820c497b97be8958a9d803f"))
    pack_door_clips(maps,bank,clips,output)

def pack_door_clips(maps,bank,clips,output):
    tiles=list(struct.iter_unpack(">64H",bank))
    for first,end,name,initial,final in clips:
        palette={}
        stream=bytearray()
        previous=[0x8000]*(192*128)
        for frame in range(first,end):
            cells=struct.unpack_from(">384H",maps,frame*768)
            pixels=[value for row in range(16) for y in range(8) for x in range(24)
                    for value in tiles[cells[row*24+x]][y*8:y*8+8]]
            if frame in (first,end-1):
                digest=hashlib.sha256(struct.pack(">24576H",*pixels)).hexdigest()
                if digest!=(initial if frame==first else final):
                    raise ValueError(f"Unexpected {name} boundary at frame {frame}")
            for pos in range(0,len(pixels),8):
                if pixels[pos:pos+8]==previous[pos:pos+8]: continue
                mask=0
                colors=[]
                for bit in range(8):
                    color=pixels[pos+bit]
                    if color!=previous[pos+bit]:
                        mask|=1<<bit
                        colors.append(palette.setdefault(color,len(palette)))
                stream.extend(struct.pack(">HB",pos//8,mask))
                stream.extend(colors)
            stream.extend(b"\xff\xff")
            previous=pixels
        header=struct.pack(">HH",end-first,len(palette))
        (output/name).write_bytes(header+struct.pack(f">{len(palette)}H",*palette)+stream)
