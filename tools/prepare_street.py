"""Pack the Act 2 vertical pan as scanline copies and changed pixels."""
import struct

def pack_street(work, first, last, cells_per_frame=384):
    maps=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    colors={}
    frames=[]
    previous_map=None
    for number in range(first,last+1):
        start=(number-13600)*cells_per_frame*2
        tilemap=maps[start:start+768]
        if tilemap==previous_map:
            frames[-1][0]+=1
            continue
        previous_map=tilemap
        cells=struct.unpack(">384H",tilemap)
        lines=[]
        for block in range(0,384,24):
            for y in range(8):
                row=b"".join(tiles[t*128+y*16:t*128+y*16+16] for t in cells[block:block+24])
                lines.append(bytes(colors.setdefault(c,len(colors)) for c, in struct.iter_unpack(">H",row)))
        frames.append([1,lines])
    if len(colors)>128 or next(iter(colors))!=0x8000:
        raise ValueError("Unexpected Act 2 skyline palette")
    bank=bytearray(struct.pack(">HH",len(colors),len(frames)))
    bank.extend(struct.pack(f">{len(colors)}H",*colors))
    previous=[bytes(192)]*128
    # Each color index fits in seven bits. Count differing pixels by setting
    # the high bit of each nonzero byte in the XOR of two indexed scanlines.
    low_bits=int.from_bytes(b"\x7f"*192,"big")
    high_bits=int.from_bytes(b"\x80"*192,"big")
    for duration,lines in frames:
        bank.extend(struct.pack(">H",duration))
        prev_bits=[int.from_bytes(row,"big") for row in previous]
        for y,row in enumerate(lines):
            bits=int.from_bytes(row,"big")
            ref=min(range(max(0,y-8),min(128,y+9)),
                    key=lambda i: (((bits^prev_bits[i])+low_bits)&high_bits).bit_count())
            changes=[x for x in range(192) if row[x]!=previous[ref][x]]
            spans=[]
            for x in changes:
                if spans and x-spans[-1][1]<=3:
                    spans[-1][1]=x
                else:
                    spans.append([x,x])
            bank.extend((ref,len(spans)))
            for left,right in spans:
                bank.extend((left,right-left+1))
                bank.extend(row[left:right+1])
        previous=lines
    if len(bank)>0xf4000:
        raise ValueError("Act 2 skyline exceeds low work RAM")
    return bank
