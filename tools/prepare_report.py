"""Pack Gibson's computer report into independently triggered scrolling sections."""
import hashlib
import struct

FIRST=13740
HEIGHT=132
WIDTH=192
# Every boundary is the frame on which the retail VM dispatches the actor or
# receives its completion signal. The test program leaves 45 ticks between actors.
SECTIONS=((13811,14038),(14083,14303),(14348,14567),(14611,14831),
          (14877,15097),(15142,15361),(15405,15625),(15671,15890),
          (15934,16154),(16198,16417),(16461,16681),(16727,16946),(16990,17207))

def report_program():
    program=bytearray.fromhex("25 3d 070e 25 4a 0080")
    for actor in range(20,33):
        program.extend((37,0,35,0,actor,0,0,37,69,0,actor,37,74,0,45))
    return bytes(program)+bytes.fromhex("4a 7000")

def pack_report(work,out):
    base=(work/"base.raw").read_bytes()
    maps=(work/"ids.raw").read_bytes()
    ids=list(struct.iter_unpack(">132H",maps))
    raw=(work/"rows.raw").read_bytes()
    if len(base)!=256*224*2 or len(ids)!=17251-FIRST+1 or len(raw)%(WIDTH*2):
        raise ValueError("Incomplete report animation")
    expected=("b32d54636d6bd2ae93332a8905679a1b393078dbf05e651a2b0eed24a586c378",
              "95e402d2b7835e6ff733d185d1f2c5b3d9f66b83970a1e963c2cc68d748f74ba",
              "3d95d5bcf5c099504006eec6cc1b20da56c2eb27a3f9ffc46496d0cf05e4d73e")
    if tuple(hashlib.sha256(x).hexdigest() for x in (base,maps,raw))!=expected:
        raise ValueError("Retail computer report differs from verified graphics")
    (out/"GTERM.BIN").write_bytes(base)
    for actor,(start,end) in enumerate(SECTIONS,20):
        frames=ids[start-FIRST:end-FIRST+2]
        # Store only the rows used by this section. Consecutive pictures
        # scroll most of their rows together, then introduce new letters.
        row_ids={}
        colors={}
        rows=bytearray()
        steps=bytearray()
        previous=None
        for frame in frames:
            current=[]
            for source in frame:
                if source not in row_ids:
                    row_ids[source]=len(row_ids)
                    pos=source*WIDTH*2
                    for color in struct.unpack_from(">192H",raw,pos):
                        rows.append(colors.setdefault(color,len(colors)))
                current.append(row_ids[source])
            shifts=(0,1,-1,2,-2,3,-3,4,-4) if previous else (0,)
            def same(shift,y):
                return previous is not None and 0<=y+shift<HEIGHT and previous[y+shift]==current[y]
            shift=max(shifts,key=lambda n:sum(same(n,y) for y in range(HEIGHT)))
            changed=[y for y in range(HEIGHT) if not same(shift,y)]
            steps.extend(struct.pack(">bB",shift,len(changed)))
            for y in changed: steps.extend(struct.pack(">BH",y,current[y]))
            previous=current
        header=struct.pack(">4H",len(frames),len(row_ids),len(colors),0)
        data=header+struct.pack(f">{len(colors)}H",*colors)+rows+steps
        if len(data)>0x25000 or ((len(data)+1)&~1)+len(row_ids)*WIDTH*2>0x25000:
            raise ValueError(f"Report actor {actor} exceeds Saturn memory")
        (out/f"GTERM{actor}.BIN").write_bytes(data)
