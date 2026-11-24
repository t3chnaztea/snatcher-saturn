"""Pack the SP33 return to Junker HQ and its closed reception booth."""
import hashlib
import struct
from prepare_freddy import pack_section
from prepare_street import pack_street

def prepare_hq_return(work,cd,pack_tiles):
    intro=pack_street(work,13650,13893)
    lights=pack_street(work,13894,13973)
    loop_offset=(4+len(intro)+1)&~1
    city=struct.pack(">I",loop_offset)+intro+bytes(loop_offset-4-len(intro))+lights
    raw=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    fade=pack_section(raw,tiles,14640,14770,13600,14770,pack_tiles)
    booth=pack_section(raw,tiles,14770,14846,13600,14846,pack_tiles)
    for name,data,expected in (
        ("HQCITY",city,"aed9a3f9c1a80d1522a05fd200b7b90ba8b363b1fc41ee9f2797d16459f90bd1"),
        ("HQFADE",fade,"3bd2d57906f4e5e3b6adb10b3acc3beae52e7053c837c8999510f72153889f8a"),
        ("HQBOOTH",booth,"2020fb2266dc08583d135470f3b564c665dcd333f7f00b4b9346ccebb92c847b"),
    ):
        if hashlib.sha256(data).hexdigest()!=expected:
            raise ValueError(f"Unexpected SP33 scene data for {name}")
        (cd/(name+".BIN")).write_bytes(data)


def prepare_shutter(work,cd,pack_tiles):
    raw=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    # The 23 numbered cuts start with the corresponding retail English voice.
    starts=(14696, 14800, 14970, 15087, 15549, 15714, 15964, 16194, 16318, 16566, 16717, 16828, 16933, 17198, 17410, 17515, 17802, 17926, 18290, 18573, 18741, 19036, 19180)
    cuts=[("SHUTIN",13684,13718),("SHUT709",13719,14235),("SHUTUP",14236,14518),
          ("SHUT36",14519,14695),("SHUTOUT",19180,19200),("HQHALL",19518,19635)]
    cuts.extend((f"SHUT{710+i}",a,b-1) for i,(a,b) in enumerate(zip(starts,starts[1:])))
    digest=hashlib.sha256()
    for name,a,b in cuts:
        clip=pack_section(raw,tiles,a,b,13600,b,pack_tiles,692)
        digest.update(clip)
        (cd/(name+".BIN")).write_bytes(clip)
    if digest.hexdigest()!="1d53fca5b1e8ada0bd70446d5944828e0e2a4ce5b65b5203bef7beea74310783":
        raise ValueError("Unexpected SP33 shutter animation")


def prepare_hall_track(work,cd,pack_tiles):
    from prepare_briefing import timed_bank
    raw=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    clock={frame:(track,lba,status) for frame,track,lba,status in
           (map(int,line.split()) for line in (work/"transport.tsv").read_text().splitlines())}

    def clip(first,last):
        return pack_section(raw,tiles,first,last,13600,last,pack_tiles,692,0x100000)

    bank=timed_bank(clip,clock,12,147305,(13656,29744))
    if hashlib.sha256(bank).hexdigest()!="8f380bae6f6a0009ae05624a12b4fb8447d406d32a016570ab09de151a95c0e1":
        raise ValueError("Unexpected hallway graphics or track 12 timing")
    (cd/"HALL12.BIN").write_bytes(bank)
    # A restored hallway save opens directly at the destination menu.
    start=(29820-13600)*692*2
    menu=pack_section(raw[start:start+768],tiles,0,0,0,0,pack_tiles)
    (cd/"HALLMENU.BIN").write_bytes(menu)


def prepare_hq_rooms(work,cd,pack_tiles):
    raw=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    cuts=[("A00",13735,1),("A03",14758,1),("A02",15921,720),
          ("B00",16884,64),("B01",17912,64),("C00",18955,840),
          ("C03",20063,840),("D00",21066,1),("D01",22099,1),
          ("E01",23197,28),("E02",24240,1)]
    digest=hashlib.sha256()
    for name,start,length in cuts:
        clip=pack_section(raw,tiles,start,start+length-1,13600,start,pack_tiles)
        digest.update(clip)
        (cd/("HQ"+name+".BIN")).write_bytes(clip)
    if digest.hexdigest()!="8d4bebd1fc7d62509bad72209a2e63cbe2af0371d33466bd7bf6319a43b3aac4":
        raise ValueError("Unexpected headquarters room graphics")


def prepare_ceiling(work,cd,pack_tiles):
    frames=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    # Each distinct scanline fits once in work RAM. Replay the original
    # 192-frame scroll by copying those rows into the 192-pixel viewport.
    from prepare_freddy import pack_row_pan
    clip=pack_row_pan(frames,tiles,13864,14055,13600)
    if hashlib.sha256(clip).hexdigest()!="d42158178e3987f857969b27c96623ff7355d67a8375b563910ddcfdb857b399":
        raise ValueError("Unexpected ceiling scroll rows")
    (cd/"HQCEIL.BIN").write_bytes(clip)
    art=(work/"HFIGHT.BIN").read_bytes()
    if hashlib.sha256(art).hexdigest()!="613427f6e6adb66d983f3710101b22666090927160a7b743d2b3deb7c5719b7a":
        raise ValueError("Unexpected ceiling encounter sprite graphics")
    (cd/"HFIGHT.BIN").write_bytes(art)


def prepare_ceiling_victory(work,cd,pack_tiles):
    raw=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    starts=(14554,14957,15098,15241,15354,15533,15776,15872,15998,16219,16421)
    cuts=[("HQFALL",14360,14553),("HQALARM",15471,15532)]
    # Actor 31 changes the alarm palette between voice lines 736 and 737.
    cuts.extend((f"HQ{732+i}",a,15470 if i==4 else b-1)
                for i,(a,b) in enumerate(zip(starts,starts[1:])))
    digest=hashlib.sha256()
    for name,a,b in cuts:
        clip=pack_section(raw,tiles,a,b,13600,b,pack_tiles,692)
        digest.update(clip)
        (cd/(name+".BIN")).write_bytes(clip)
    if digest.hexdigest()!="89eb11f58c503d46b395723d09df6590af8901841f455f133a3913126865b247":
        raise ValueError("Unexpected ceiling victory animation")
    offset=(16680-13600)*692*2
    view=pack_section(raw[offset:offset+768],tiles,0,0,0,0,pack_tiles)
    (cd/"HQCLEAR.BIN").write_bytes(view)


def prepare_lobby(work,cd,pack_tiles):
    raw=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    starts=(14080,14348,14590,14654,14823,15015,15330,15502,15699,16372,
            16437,16613,16834,17026,17343,17829,18070,18134,18242,18485)
    cuts=[("LOBBYIN",13970,14079),("MIKAIN",15666,15698),("MIKA36",16190,16371)]
    cuts.extend((f"HQ{742+i}",a,15665 if i==7 else 16189 if i==8 else b-1)
                for i,(a,b) in enumerate(zip(starts,starts[1:])))
    offset=(13820-13600)*692*2
    hall=pack_section(raw[offset:offset+768],tiles,0,0,0,0,pack_tiles)
    digest=hashlib.sha256(hall)
    (cd/"ALHALL.BIN").write_bytes(hall)
    for name,a,b in cuts:
        clip=pack_section(raw,tiles,a,b,13600,b,pack_tiles,692)
        digest.update(clip)
        (cd/(name+".BIN")).write_bytes(clip)
    if digest.hexdigest()!="96aee0f0ed4d5fbda3d29c92e2737390ed096caa767b6c5b9a701262b614ba14":
        raise ValueError("Unexpected Junker HQ lobby graphics")


def prepare_rescue(work, cd, pack_tiles):
    from prepare_briefing import timed_bank

    frames = (work/"frames.raw").read_bytes()
    tiles = (work/"tiles.raw").read_bytes()
    clock = {f:(track,lba,status) for f,track,lba,status in
             (map(int,line.split()) for line in (work/"transport.tsv").read_text().splitlines())}

    def clip(first,last):
        return pack_section(frames,tiles,first,last,13600,last,pack_tiles,692,0x100000)

    for name,data,digest in (
        ("RESCIN",clip(13911,13971),"aff0b0c6e24d1676f354d34b5ae5f01b00dc3718e958ec3b2240cde6f7d4899a"),
        ("RESC13",timed_bank(clip,clock,13,167533,(13972,20792)),"7d93d881feb363607b63f8bd90358fdf36fe94571d5b65f45fdc04a5ddbd48e2"),
        ("RESC14",timed_bank(clip,clock,14,176155,(20800,25598)),"fcf789055e8fcf47f349e40afd9b2b38e49e9afbddbed12d06699271517634b9"),
        ("RESCOUT",clip(25598,25890),"026e5469003b0a2b3d852c23c7d202c0d9bb0f551c59cd3c5e7c15e9836e0b98"),
    ):
        if hashlib.sha256(data).hexdigest()!=digest:
            raise ValueError(f"Unexpected Act 2 rescue scene in {name}")
        (cd/(name+".BIN")).write_bytes(data)
