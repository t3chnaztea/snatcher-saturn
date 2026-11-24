"""Compile driving and microscope animation from the player's Sega CD tiles.

drive-motion.z holds register changes sampled at the retail frame boundaries:
palette, vertical scroll, sprite geometry, tile names and duration. No source
image pixels or audio samples are in that table. The five sections correspond
to launch, flight, Gillian speaking, the cut to black, and landing.
"""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from struct import pack, unpack, calcsize, iter_unpack
import zlib
from PIL import Image, ImageChops
import scd_gfx as gfx

def compile_drive(data, output, scan=None, transit=False):
    city = scan in ("return0","return1","return2","return3")
    portraits = scan in ("return2","return3")
    microscope = bool(scan) and not city
    motion = BytesIO(zlib.decompress(Path(__file__).with_name(f"{scan or ('transit' if transit else 'drive')}-motion.z").read_bytes()))
    def read(fmt):
        return unpack(fmt, motion.read(calcsize(fmt)))
    palettes = [read(">64H") for _ in range(read("B")[0])]
    colors_used = sorted({c for row in palettes for c in row})
    if len(colors_used)>256: raise ValueError("Driving palette exceeds 256 colors")
    sections = gfx.sequences(data)
    blocks, packets, poses = {}, [], []
    frame_sections = []
    programs = (0,3) if transit else (3,3,2,2,4) if not scan else ({"hair":11, "skin":12, "organic":13, "return0":0, "return1":1,"return2":2,"return3":3}[scan],)
    for program in programs:
        vram = bytearray(65536)
        for sequence in (sections[0], sections[program]):
            streams, errors = gfx.resources(data,[sequence])
            if errors: raise ValueError(errors)
            for stream in streams:
                start=stream["offset"]
                pixels,_=gfx.decode(data,start+2,gfx.u16(data,start))
                for ref in stream["references"]:
                    addr=ref["vram"]
                    vram[addr:addr+len(pixels)]=pixels
        if portraits:
            # The H08 reception and office shots load only the back plane.
            # The room transition clears the former front nametable in VRAM.
            vram[0xe000:0xe800]=bytes(2048)
        if microscope:
            # Metal Gear’s speaking portrait occupies a persistent tile bank.
            streams, errors = gfx.resources(data,[sections[23]])
            if errors: raise ValueError(errors)
            portrait, = [s for s in streams if s["decoded_size"]==2304 and
                         any(r["vram"]==0x1000 for r in s["references"])]
            vram[0x1000:0x1900] = gfx.stream_bytes(data,portrait)
        if scan=="organic":
            streams, errors = gfx.resources(data,[sections[27]])
            if errors: raise ValueError(errors)
            gillian, = [s for s in streams if s["decoded_size"]==3072 and
                        any(r["vram"]==0x20 for r in s["references"])]
            vram[0x20:0xc20] = gfx.stream_bytes(data,gillian)
        @lru_cache(None)
        def tile(word):
            start=(word&2047)*32
            bank=(word>>9)&48
            pixels=bytes((n+bank if n else 0) for v in vram[start:start+32] for n in (v>>4,v&15))
            return Image.frombytes("L",(8,8),pixels)
        @lru_cache(None)
        def piece(word,w,h):
            im=Image.new("L",(8*w,8*h))
            for x in range(w):
                for y in range(h):
                    im.paste(tile(word+x*h+y),(x*8,y*8))
            if word&2048: im=im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if word&4096: im=im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            return im
        planes=[]
        for base in (0xc000,0xe000):
            plane=Image.new("L",(256,256))
            high=plane.copy()
            for n,(word,) in enumerate(iter_unpack(">H",vram[base:base+2048])):
                xy=(8*(n%32),8*(n//32))
                im=piece(word,1,1)
                plane.paste(im,xy)
                if word&32768: high.paste(im,xy)
            planes.append((plane,high))
        mask=[0]+[255]*255
        prev=None; first=len(poses)
        for _ in range(read(">H")[0]):
            if scan:
                delay,pal,lower_pal,va,vb,ha,hb,count=read(">HBB4HB")
            else:
                delay,pal,va,vb,count=read(">HBhhB")
                ha=hb=0
            actors=[read(">hhBH") for _ in range(count)]
            # All sampled scroll positions keep the 192 x 128 viewport within the map.
            pictures=[]
            for (plane,high),scroll,horizontal in zip(planes,(vb,va),(hb,ha)):
                sy=(8+scroll)%256
                if scan and (horizontal or sy+128>256):
                    pictures.append(tuple(ImageChops.offset(im,horizontal,-scroll).crop((32,8,224,136))
                                          for im in (plane,high)))
                else:
                    pictures.append(tuple(im.crop((32,sy,224,sy+128)) for im in (plane,high)))
            (back,bhi),(front,fhi)=pictures
            image=back.copy()
            image.paste(front,(0,0),front.point(mask))
            # Genesis resolves sprite order before testing the winning sprite's
            # priority against either plane. Track that priority per opaque pixel.
            priority=Image.new("L",image.size)
            for x,y,size,word in reversed(actors):
                sprite=piece(word,1+(size>>2),1+(size&3));xy=(x-32,y-8)
                opaque=sprite.point(mask)
                image.paste(sprite,xy,opaque)
                priority.paste(255 if word&32768 else 0,(xy[0],xy[1],xy[0]+sprite.width,xy[1]+sprite.height),opaque)
            foreground=bhi.copy()
            foreground.paste(fhi,(0,0),fhi.point(mask))
            fgmask=foreground.point(mask)
            fgmask.paste(0,(0,0,image.width,image.height),priority)
            image.paste(foreground,(0,0),fgmask)
            lut=[colors_used.index(c) for c in palettes[pal]]+[0]*192
            raw=(image if city else image.point(lut)).tobytes()
            if microscope or portraits:
                portrait = Image.new("L",(64,64))
                for x,y,size,word in reversed(actors):
                    if y<140: continue
                    sprite=piece(word,1+(size>>2),1+(size&3))
                    portrait.paste(sprite,(x-168,y-149),sprite.point(mask))
                lower_lut=[colors_used.index(c) for c in palettes[lower_pal]]+[0]*192
                lower=(portrait if city else portrait.point(lower_lut)).tobytes()
                if scan=="organic" or portraits:
                    gillian = Image.new("L",(64,64))
                    for x,y,size,word in reversed(actors):
                        if y<140 or x>=88: continue
                        sprite=piece(word,1+(size>>2),1+(size&3))
                        gillian.paste(sprite,(x-24,y-149),sprite.point(mask))
                    lower+=(gillian if city else gillian.point(lower_lut)).tobytes()
            now=[]; changes=[]
            for k in range(512 if scan=="organic" or portraits else 448 if microscope else 384):
                if k<384:
                    x,y=k%24*8,k//24*8
                    indices=b"".join(raw[(y+j)*192+x:(y+j)*192+x+8] for j in range(8))
                else:
                    x,y=(k-384)%8*8,(k-384)//8*8
                    indices=b"".join(lower[(y+j)*64+x:(y+j)*64+x+8] for j in range(8))
                index=blocks.setdefault(indices,len(blocks))
                now.append(index)
                if prev is None or index!=prev[k]: changes.append(pack(">HH",k,index))
            prev=now
            poses.append((len(packets),len(changes),delay,pal,lower_pal) if city else (len(packets),len(changes),delay))
            packets.extend(changes)
        frame_sections.append((first,len(poses)-first))
        piece.cache_clear();tile.cache_clear()
    if motion.read(1): raise ValueError("Unexpected driving motion trailer")
    if city:
        # Scrolling streets reuse tile pixels across hundreds of palette changes.
        colors=b"".join(pack(">H",0x8000|sum((((w>>bit)&7)*255//7*31//255)<<shift
                        for bit,shift in ((0,0),(3,5),(6,10)))) for row in palettes for w in row)
        geometry=b"".join(pack(">I4H",*pose) for pose in poses)
        color_use=b"".join(pack(">2I",sum(1<<c for c in set(tile) if c<32),
                                sum(1<<(c-32) for c in set(tile) if c>=32)) for tile in blocks)
        return (pack(">4I",len(palettes),len(poses),len(packets),len(blocks))+colors+
                geometry+b"".join(packets)+color_use+b"".join(blocks))
    pixels=b"".join(blocks)
    updates=b"".join(packets)
    palette=b"".join(pack(">H",0x8000|sum((((w>>bit)&7)*255//7*31//255)<<shift for bit,shift in ((0,0),(3,5),(6,10)))) for w in colors_used).ljust(512,b"\0")
    data=pack(">II",540+8*len(poses),540+8*len(poses)+len(updates))+b"".join(pack(">HH",*s) for s in frame_sections).ljust(20,b"\0")+palette+b"".join(pack(">IHH",*p) for p in poses)+updates+pixels
    if len(data)>0x100000: raise ValueError(f"Drive exceeds low work RAM: {len(data)}")
    output.write_bytes(data)
