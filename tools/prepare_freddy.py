"""Compile SP15's Room 202 doorway effects from DATA_F0 on the supplied disc."""
import hashlib
import struct
import tempfile
from pathlib import Path

# The first two segments cover the door and dissolve. The last two reveal
# the room. Each segment fits in the 384 KiB Saturn animation buffer.
segments=((0,62),(63,114),(220,251),(252,332))
hashes={
    "FC1":"4bea41deaccbc39a0219f29d7728844939e70d9c86dfb094be1fcc9ece8942f9",
    "FG1":"e5cb6522dd48e2dd023e641fba58c303ef20a4b4de7718fce74d80bc8e608a8f",
    "FC2A":"c0cac954fbe39b867f3052a4dec865bc24ca11ab5864148c4685f3e4fe1536f2",
    "FC2B":"55ae9e4170b9820623a13fa2509d6aa5b15ca349aa33aa06bac8483ca7a56754",
    "FG2A":"84d9579abb0cfd3928eb99b8f0ea837e788774a2e20cccfd955b00259e6cd4ad",
    "FG2B":"8c45943181f93a63ef50f4086de59fe80607c16f38df489a03906134de2b36ff",
    "FR1A":"db9276b098460d4944cf0bbe3fe306a8e72511c436c7e6c45eccb920faa7bba4",
    "FR1B":"6cd0078c0ff4206c4d701be2463b2638f8a2de3d3de7840f3b8f1915d23947bf",
    "FR2A":"4571575b7e2324734501d82c1d38c4da8f69ddd19ea02c32cbe7803af1b799d1",
    "FR2B":"77f46fb3a4ac65505f6c32df21ecabbd4e609e315d33f8c42662c203fcfc9a18",
}

def pack_row_pan(frames,tiles,first,last,origin):
    row_ids={}
    timeline=bytearray()
    for frame in range(first,last+1):
        cells=struct.unpack_from(">384H",frames,(frame-origin)*768)
        for y in range(128):
            ids=cells[(y//8)*24:(y//8+1)*24]
            row=b"".join(tiles[i*128+(y%8)*16:i*128+(y%8+1)*16] for i in ids)
            timeline.append(row_ids.setdefault(row,len(row_ids)))
    return struct.pack(">HH",last-first+1,len(row_ids))+timeline+b"".join(row_ids)


def pack_section(raw,bank,first,last,origin,loop,pack_tiles,cells_per_frame=384,limit=0x60000):
    rows=[]
    tiles={}
    patterns=bytearray()
    for frame in range(first,last+1):
        cells=struct.unpack_from(f">{cells_per_frame}H",raw,(frame-origin)*cells_per_frame*2)
        for cell in cells:
            if cell not in tiles:
                tiles[cell]=len(tiles)
                patterns.extend(bank[cell*128:(cell+1)*128])
        rows.append(struct.pack(f">{cells_per_frame}H",*(tiles[cell] for cell in cells)))
    return pack_tiles(rows,patterns,loop-first,limit)

def prepare(root,render,pack_tiles):
    for dark in (False,True):
        for assisted in (False, True):
            with tempfile.TemporaryDirectory(dir=root/"build") as tmp:
                work=Path(tmp)
                render(work,0x0502,assisted=assisted,dark=dark)
                raw=(work/"frames.raw").read_bytes()
                bank=(work/"tiles.raw").read_bytes()
            start=13835 if dark else 13833
            color="FG" if dark else "FC"
            variant="A" if assisted else "B"
            names=(color+"1",color+"2"+variant,"FR1"+variant,"FR2"+variant)
            for name,(first,last) in zip(names,segments):
                clip=pack_section(raw,bank,start+first,start+last,13650,start+last,pack_tiles)
                if hashlib.sha256(clip).hexdigest()!=hashes[name]:
                    raise ValueError(f"Unexpected retail Room 202 section {name}")
                (root/"cd"/(name+".BIN")).write_bytes(clip)
    with tempfile.TemporaryDirectory(dir=root/"build") as tmp:
        work=Path(tmp)
        render(work,0x0508)
        prepare_sections(root,work,pack_tiles,reveal_sections)
    with tempfile.TemporaryDirectory(dir=root/"build") as tmp:
        work=Path(tmp)
        render(work,0x0600)
        prepare_sections(root,work,pack_tiles,mirror_sections)
    with tempfile.TemporaryDirectory(dir=root/"build") as tmp:
        work=Path(tmp)
        render(work,0x0602)
        prepare_sections(root,work,pack_tiles,shot_sections)
    with tempfile.TemporaryDirectory(dir=root/"build") as tmp:
        work=Path(tmp)
        render(work,0x0604)
        closing_bank(root,work,pack_tiles)
    with tempfile.TemporaryDirectory(dir=root/"build") as tmp:
        work=Path(tmp)
        render(work,0x1601)
        prepare_sections(root,work,pack_tiles,cure_title_sections)
    with tempfile.TemporaryDirectory(dir=root/"build") as tmp:
        work=Path(tmp)
        render(work,0x050a)
        raw=(work/"frames.raw").read_bytes()
        bank=(work/"tiles.raw").read_bytes()
        clip=pack_section(raw,bank,13677,14023,13600,14023,pack_tiles)
        if hashlib.sha256(clip).hexdigest()!="f093cf185f5847d399f2cbf6fd789b378ff9c83ac646ad9ac86cb97fc3599b71":
            raise ValueError("Unexpected retail Snatcher reveal")
        (root/"cd"/"FRFALL.BIN").write_bytes(clip)

def prepare_sections(root,work,pack_tiles,sections):
    raw=(work/"frames.raw").read_bytes()
    bank=(work/"tiles.raw").read_bytes()
    # SP15 independently starts actors 16 and 17 during the second shot.
    for name,first,last,loop,digest in sections:
        clip=pack_section(raw,bank,first,last,13600,loop,pack_tiles)
        if hashlib.sha256(clip).hexdigest()!=digest:
            raise ValueError(f"Unexpected retail bathroom reveal {name}")
        (root/"cd"/(name+".BIN")).write_bytes(clip)

reveal_sections=(
    ('FRSHOW', 13685, 13947, 13947, '575944d5526ec36ee1e17b6113480d40b93259dac8c261cf459b2c39ed16451c'),
    ('FRFACE', 13974, 13974, 13974, '29d636a930e36669240f8fdb8e50686a436c2220d32278dd2f2881d26be636e5'),
    ('FRGASP', 14060, 14220, 14220, '288e4eae07a10adf7093141dc65613b06c84f56d3d0e37ffb2302672471cb56d'),
    ('FRCRY', 14228, 14374, 14360, 'b55f082ac4b9415ca66457c025b933c0fc09f2444fd8af9f59e6829d65fcafdc'),
)

mirror_sections=(
    ("FRMIRROR",13667,13709,13709,"05c3faa25b712b0cf6616789d405387aeb74d604d046ec21ac2a7dc3aa25ba90"),
    ("FRREFL",13745,13775,13775,"ba33e081fe5b99f15c6db63433f80d4e8ce485e2301e57a6767248f7de09150f"),
)

shot_sections=(
    ("FRSHOT",14040,14259,14259,"383420c91993425a36a5265f64dc1b01c967f6fb47e69993505b5be39a740c95"),
)

# Retail transport boundaries in playback order, including the prelude and coda.
closing_sections=(
    (13994,14071,"aec92ce66d82d21f81e3735b52f707f21587ab27878ffff90ac72856d7afe7be"),
    (14072,14598,"ac753dc195e668398b878c1af4a3f397b617664efb5ad1ce8f22391702e80531"),
    (14599,17025,"922d853850802008ad732ec7235564f9c24472bb78954dea0b4001cb84a75f1e"),
    (17026,19477,"ec23243d412d1820c7e5a72fda3495a9ef92dfd1745d7951df4ec4b23b868bdb"),
    (19478,20410,"cc20e0e20d45434f1d10a81e1192d525e533e5c698d8df98c7dcbfe171148c55"),
    (20411,21498,"6a2b5729e03916b6c50e38934f813d25157632fe75406c0703594dc38bd2fc22"),
    (21499,23985,"91c39a46aacd7cbfd75dab0965f44e3fe82a64242403f5e62dbb627184bfca1b"),
    (23986,24245,"a29ca9a76a97e7ee5b23246a4e52c27900585f1ddfa012dcb09f20cef1eb3c54"),
)

def closing_bank(root, work, pack_tiles):
    raw=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    bank=bytearray(4*len(closing_sections))
    for index,(first,last,digest) in enumerate(closing_sections):
        clip=pack_section(raw,tiles,first,last,13600,last,pack_tiles,384+28*11,0x100000)
        if hashlib.sha256(clip).hexdigest()!=digest:
            raise ValueError(f"Unexpected Act 1 closing animation at frame {first}")
        bank.extend(bytes(-len(bank)%4))
        struct.pack_into(">I",bank,index*4,len(bank))
        bank.extend(clip)
    if len(bank)>0x100000:
        raise ValueError("Act 1 closing graphics exceed Saturn low work RAM")
    (root/"cd"/"ACT1END.BIN").write_bytes(bank)

cure_title_sections=(
    ('CUREIN', 13857, 13907, 13907, 'e9dfed5032799c5b005aa2bdfe9441033391a2801a2050670effd35b555969c4'),
    ('CUREOUT', 14108, 14157, 14157, '15ed1ec142c94f9d37b8da99ce3227762a09b26d21c1bd8807503443d52d32ff'),
)
