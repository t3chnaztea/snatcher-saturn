"""Extract the nine Stage 10 target animations from the player's US disc."""
import hashlib
import struct
import tempfile
from pathlib import Path

# Each range begins a phase in the original target program. The last number
# is the first frame after retreat. Three pad routes expose all nine fields.
TARGETS = (
    (1, (18675,18701,18718,18735,18754,18795)),
    (0, (19446,19472,19489,19506,19523,19564)),
    (0, (18941,18967,18984,19001,19021,19063)),
    (1, (18798,18824,18841,18858,18878,18919)),
    (0, (18820,18846,18863,18880,18897,18938)),
    (3, (20090,20116,20133,20150,20169,20210)),
    (0, (19202,19228,19245,19262,19281,19322)),
    (0, (19325,19351,19368,19385,19402,19443)),
    (0, (18557,18583,18600,18617,18636,18678)),
)


def combat_input(hits):
    if not hits:
        return []
    actions = [(18538,18538,2)]
    for frame,aim in ((18584,0xa0),(18701,0x50),(18818,0x60))[:hits]:
        actions.extend(((frame,frame+11,aim),(frame+3,frame+3,0x100)))
    holster = {1:18614, 3:18848}[hits]
    actions.append((holster,holster+2,2))
    return actions


def target_bank(captures):
    # Tile IDs are local to each capture. Intern their actual 8x8 pixels
    # before sharing a single dictionary across the three routes.
    tiles = {}
    maps = {}
    sequences = []
    for field,(route,bounds) in enumerate(TARGETS):
        frames,patterns,first = captures[route]
        def picture(frame):
            local = struct.unpack_from(">384H",frames,(frame-first)*692*2)
            ids = []
            for index in local:
                tile = patterns[index*128:(index+1)*128]
                if len(tile)!=128:
                    raise ValueError(f"Missing retail tile in field {field}")
                ids.append(tiles.setdefault(tile,len(tiles)))
            tilemap = struct.pack(">384H",*ids)
            return maps.setdefault(tilemap,len(maps))
        if field==0:
            idle = picture(18485)
        for start,end in zip(bounds,bounds[1:]):
            sequences.append(bytes(picture(frame) for frame in range(start,end)))
    # Header, 45 phase offsets and final sentinel, frame IDs, maps, tile bank.
    offset = 0
    starts = []
    for seq in sequences:
        starts.append(offset)
        offset += len(seq)
    timeline = b"".join(sequences)
    header = struct.pack(">4H46H",idle,len(maps),len(tiles),len(timeline),*starts,offset)
    return header+timeline+bytes(len(timeline)%2)+b"".join(maps)+b"".join(tiles)


def prepare_mika(root, render):
    captures = {}
    for hits in (0,1,3):
        with tempfile.TemporaryDirectory(dir=root/"build") as tmp:
            work = Path(tmp)
            render(work,0x1506,mika_hits=hits)
            if hits==0:
                art=(work/"MFIGHT.BIN").read_bytes()
                if hashlib.sha256(art).hexdigest()!="e82f7ce240b36cc81d3642cdd56dd98c072b50fae17d5b94b40049913b910062":
                    raise ValueError("Unexpected Stage 10 sight patterns")
                (root/"cd"/"MFIGHT.BIN").write_bytes(art)
            captures[hits] = ((work/"frames.raw").read_bytes(),(work/"tiles.raw").read_bytes(),18485)
    bank = target_bank(captures)
    if hashlib.sha256(bank).hexdigest() != "b876604c1a12b1620fcc74fff29ad89c7c93d97036c55c99a86380196c8cca4f":
        raise ValueError("Unexpected Stage 10 target animations")
    (root/"cd"/"MIKATGT.BIN").write_bytes(bank)
