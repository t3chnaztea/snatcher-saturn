"""Compile the original SP20 CD-timed presentation for the Saturn bitmap."""
import hashlib
import struct
from prepare_freddy import pack_section

def prepare_briefing(work, output, pack_tiles):
    frames=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    clock={f:(t,lba,s) for f,t,lba,s in
           (map(int,line.split()) for line in (work/"transport.tsv").read_text().splitlines())}
    def clip(first,last):
        return pack_section(frames,tiles,first,last,14350,last,pack_tiles,896,0x100000)
    prelude=clip(14449,14507)
    def write_verified(name, data, digest):
        if hashlib.sha256(data).hexdigest()!=digest:
            raise ValueError(f"Unexpected retail SP20 graphics or CD timing for {name}")
        (output/name).write_bytes(data)
    write_verified("BRIEFING.BIN",prelude,"507228b74ec2565df944456eb22b14074efb4bd82ed1ff35d5424db6bc2e477d")
    for track,origin,bounds in [(8,106833,(14508,17243,20003,23969,27275)),
                                (9,122923,(27289,32415))]:
        bank=timed_bank(clip,clock,track,origin,bounds)
        expected={8:"351b9f9013f920d830f7434cfa8d611980fd6e4080ee1901e785265e9896c54d",
                  9:"1d1b8672631f52322497ea3354821ec6edccd226430873de59b57e8700fc2479"}
        write_verified(f"BRIEF{track}.BIN",bank,expected[track])


def timed_bank(clip,clock,track,origin,bounds):
    count=len(bounds)-1
    bank=bytearray(struct.pack(">I",count)+bytes(8*count))
    for i,(first,stop) in enumerate(zip(bounds,bounds[1:])):
        movie=clip(first,stop-1)
        _,steps,_=struct.unpack_from(">IHH",movie)
        offset=first
        times=[]
        for step in range(steps):
            drive_track,lba,status=clock[offset]
            sector=max(0,lba-origin)
            if drive_track!=track-1 or (times and sector<times[-1]):
                # At the end, Genesis Plus GX advances into the next pregap.
                if offset<stop-3: raise ValueError(f"Unexpected CD position at {offset}")
                sector=times[-1]
            times.append(sector)
            offset+=struct.unpack_from(">H",movie,32+step*4)[0]
        if offset!=stop: raise ValueError("Truncated briefing timing table")
        bank.extend(bytes(-len(bank)%4)); picture_offset=len(bank)
        bank.extend(movie); timing_offset=len(bank)
        bank.extend(struct.pack(f">{steps}H",*times))
        struct.pack_into(">II",bank,4+i*8,picture_offset,timing_offset)
    if len(bank)>0x100000: raise ValueError("Briefing exceeds low work RAM")
    return bank


def prepare_confrontation(work, output, pack_tiles):
    frames=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    clock={f:(track,lba,status) for f,track,lba,status in
           (map(int,line.split()) for line in (work/"transport.tsv").read_text().splitlines())}
    def clip(first,last):
        return pack_section(frames,tiles,first,last,13600,last,pack_tiles)

    # SP31 voices 658..660 play before the three quick cuts to the fight.
    cuts=(("QVISIN",13670,13700),("QVIS658",13701,13771),("QVIS659",13772,13917),
          ("QVIS660",13918,14128),("QVISD",14129,14352),("QVISE",14353,14505),
          ("QVISF",14506,14713),("QVISEND",14714,14718))
    digest=hashlib.sha256()
    for name,first,last in cuts:
        data=clip(first,last)
        (output/(name+".BIN")).write_bytes(data)
        digest.update(data)
    track=timed_bank(clip,clock,21,234583,(14719,39761))
    (output/"VIS21.BIN").write_bytes(track)
    digest.update(track)
    if digest.hexdigest()!="b91b0b490d7eb0d26883e13340d87ec05658d999bde1fc5c515dede67a66efff":
        raise ValueError("Unexpected SP31 confrontation graphics or track 21 timing")
