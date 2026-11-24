"""Camera instructions and English voice onsets in the retail Act 3 performances."""
import hashlib
import struct

from prepare_freddy import pack_section, pack_row_pan

# Camera keys are SP36 instruction positions. Voice keys start at 0x1000.
# Times are Genesis Plus GX video frames counted from the patched New Game entry.
CUTS = (
    (0x0053, 41339), (0x1304, 41417), (0x1305, 41765), (0x1306, 42046),
    (0x006d, 42302), (0x1307, 42344), (0x1308, 42575), (0x1309, 42948),
    (0x130a, 43286), (0x130b, 43556), (0x130c, 43767), (0x130d, 44070),
    (0x130e, 44327), (0x00a1, 44570), (0x130f, 44660), (0x1310, 44978),
    (0x1311, 45230), (0x1312, 45530), (0x1313, 45705), (0x1314, 45840),
    (0x1315, 46176), (0x00db, 46488), (0x1316, 46595), (0x1317, 46844),
    (0x00fe, 47183), (0x1318, 47292), (0x0110, 47580), (0x1319, 47624),
    (0x011e, 48014), (0x131a, 48050), (0x131b, 48279), (0x131c, 48702),
    (0x131d, 48898), (0x131e, 49377), (0x0144, 49518), (0x131f, 49603),
    (0x1320, 49842), (0x1321, 50083), (0x1322, 50166), (0x1323, 50436),
    (0x1324, 50535), (0x1325, 50687), (0x1326, 50830), (0x1327, 51378),
    (0x0194, 51467), (0x1328, 51763), (0x1329, 51989), (0x01b5, 52101),
    (0x132a, 52134), (0x132b, 52537), (0x132c, 52666), (0x01da, 53259),
    (0x132d, 53294), (0x01e8, 53580), (0x132e, 53619), (0x132f, 53911),
    (0x1330, 54346), (0x0227, 54718), (0x1331, 54758), (0x0235, 54950),
    (0x1332, 54994), (0x1333, 55437), (0x1334, 55699), (0x024b, 55793),
    (0x1335, 55929), (0x1336, 56380), (0x1337, 56527), (0x1338, 56809),
    (0x1339, 56983), (0x133a, 57557), (0x0283, 57659), (0x133b, 57705),
    (0x133c, 58116), (0x133d, 58290), (0x133e, 58817), (0x133f, 59069),
    (0x1340, 59267), (0x1341, 59533), (0x1342, 59835), (0x02bf, 60024),
    (0x1343, 60050), (0x1344, 60137), (0x1345, 60390), (0x02e8, 60686),
    (0x1346, 60733), (0x1347, 61153), (0x1348, 61438), (0x1349, 61570),
    (0x030e, 61665), (0x134a, 61711), (0x134b, 62050), (0x134c, 62296),
)
LAST_FRAME = 64100


def prepare_room(work, cd, pack_tiles):
    raw = (work/"frames.raw").read_bytes()
    tiles = (work/"tiles.raw").read_bytes()
    bank = bytearray(2048)
    struct.pack_into(">I", bank, 0, len(CUTS))
    for i, (key, first) in enumerate(CUTS):
        last = CUTS[i+1][1]-1 if i+1<len(CUTS) else LAST_FRAME
        # Cue 807 continues across the timed cut to the Moscow map.
        if key==0x1000+807:
            last=51762
        clip = pack_section(raw, tiles, first, last, 13600, last, pack_tiles, 692)
        struct.pack_into(">HH", bank, 4+i*4, key, len(bank)//2048)
        bank.extend(clip)
        bank.extend(bytes(-len(bank)%2048))
    if hashlib.sha256(bank).hexdigest() != "2376cc73c93f42607d35c9e9ff03f1103d91f7f904620bcf8f7c44e7c53a3876":
        raise ValueError("Unexpected Act 3 room performance")
    (cd/"ACT3ROOM.BIN").write_bytes(bank)


# The quiz runs on player input. Capture only the upper viewport.
QUIZ_CUTS = (
    (0x3c7, 65356, 65955),
    (0x3e0, 65956, 66006),
    (0x3ef, 66007, 67296),
    (0x427, 67297, 67936),
    (0x447, 67937, 68033),
    (0x4ba, 68034, 70177),
    (0x5bf, 70178, 70816),
    (0x5e0, 70817, 71137),
    (0x5f9, 71138, 71617),
    (0x60f, 71618, 71777),
    (0x61e, 71778, 71937),
    (0x62d, 71938, 72097),
    (0x63c, 72098, 74584),
)

# The voices and camera changes after the city answer run without player input.
MAP_CUTS = (
    (0x071c, 74585), (0x134d, 74640), (0x134e, 75168), (0x0730, 75319),
    (0x134f, 75360), (0x1350, 75576), (0x1351, 75664), (0x1352, 75898),
    (0x1353, 76040), (0x0756, 76389), (0x1354, 76432), (0x0764, 76650),
    (0x1355, 76696), (0x1356, 76991), (0x1357, 77297), (0x077e, 77509),
    (0x1358, 77599), (0x1359, 77889), (0x135a, 78106), (0x135b, 78361),
    (0x135c, 78687), (0x135d, 79035), (0x135e, 79704), (0x135f, 79956),
    (0x1360, 80275), (0x1361, 80522), (0x1362, 80661), (0x1363, 80967),
    (0x1364, 81027), (0x1365, 81125), (0x1366, 81376), (0x1367, 81613),
    (0x1368, 81912), (0x1369, 82460), (0x136a, 82657), (0x136b, 82914),
    (0x136c, 83216), (0x136d, 83435), (0x0870, 83675), (0x136e, 83702),
    (0x136f, 83875),
)


def prepare_quiz(work, cd, pack_tiles):
    raw=(work/"frames.raw").read_bytes()
    view=b"".join(raw[i:i+768] for i in range(0,len(raw),1384))
    tiles=(work/"tiles.raw").read_bytes()
    path=cd/"ACT3ROOM.BIN"
    bank=bytearray(path.read_bytes())
    count=struct.unpack_from(">I",bank)[0]
    # Gillian and Mika keep moving while the player reads these answers.
    # The sixteen frames before each loop match the end of that camera clip.
    idle_loops={0x3ef:66075,0x4ba:68124,0x5f9:71233}
    for key,first,last in QUIZ_CUTS:
        loop=idle_loops.get(key,last)
        clip=pack_section(view,tiles,first,last,63800,loop,pack_tiles)
        struct.pack_into(">HH",bank,4+count*4,key,len(bank)//2048)
        bank.extend(clip)
        bank.extend(bytes(-len(bank)%2048))
        count+=1
    for i,(key,first) in enumerate(MAP_CUTS):
        last=MAP_CUTS[i+1][1]-1 if i+1<len(MAP_CUTS) else 83933
        clip=pack_section(raw,tiles,first,last,63800,last,pack_tiles,692)
        struct.pack_into(">HH",bank,4+count*4,key,len(bank)//2048)
        bank.extend(clip)
        bank.extend(bytes(-len(bank)%2048))
        count+=1
    struct.pack_into(">I",bank,0,count)
    if hashlib.sha256(bank).hexdigest()!="012fb095279c5db72dda8e44c7b4c15892761da8d8fa87b0e468d88bb35a09d8":
        raise ValueError("Unexpected quiz camera or actor animation")
    path.write_bytes(bank)


def prepare_track15(work, cd, pack_tiles):
    from prepare_briefing import timed_bank

    raw=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    clock={f:(track,lba,status) for f,track,lba,status in
           (map(int,r.split()) for r in (work/"transport.tsv").read_text().splitlines())}

    def clip(first,last):
        return pack_section(raw,tiles,first,last,63800,last,pack_tiles,692,0x100000)

    for name,data,digest in (
        ("A3CDIN",clip(83934,83939),"11567b6ea8d48b5d0b973db140768b571ab53ce78a51d6541a56f9a66c6e1926"),
        ("A3CD15",timed_bank(clip,clock,15,182297,(83940,88565)),"e229c70eebdd80eccf3ff9a5cf428a511393ed8c3ecc21f0ab3d19f9e8a788b1"),
        ("A3CDOUT",clip(88565,88652),"5693c77e6d7fca8d991404efd73d97206ab4623db639c9796647b80855a0b6b8"),
    ):
        if hashlib.sha256(data).hexdigest()!=digest:
            raise ValueError(f"Unexpected track 15 animation in {name}")
        (cd/(name+".BIN")).write_bytes(data)


def prepare_departure(work, cd, pack_tiles):
    """Build the Act 3 parking lot and flight from the retail SP37 route."""
    raw = (work / "frames.raw").read_bytes()
    tiles = (work / "tiles.raw").read_bytes()
    view = b"".join(raw[i:i+768] for i in range(0, len(raw), 1384))
    cuts = (
        ("CANOPY", 110336, 110447, 384, "25145564b5bf124e8a4f7a396a0ec89234af0b435483fd72d9c5b03f55f5e72c"),
        ("BOARD", 110530, 110595, 384, "77ce8dcc58e4d68823a95b2e590bf36ad22a3e133bcd214307f81660aab4b2d2"),
        ("V880", 111036, 111241, 692, "414b4ec50ef0a0e38e350d841d872e204573871667df53d2eea345ec6012a169"),
        ("TAKE1", 111242, 111499, 384, "7e1b3419cb8b6c5c9b89db4ef0d1b076ba3b71167a21d10500d584fbd248b855"),
        ("TAKE2", 111500, 111779, 384, "80105ea7a24216040bc3193e5127abf90637735f5f5fc45e216344e091010817"),
        ("TAKE3", 111780, 111862, 384, "19cbe460f7ad655266d7f9405d8f14cf895fe222862c19f3661269aab55819d0"),
        ("V881", 111863, 112043, 692, "24d8579438ac2f5008ef6af9d67f781f36f9e332828970f58acb41a17cda3197"),
        ("CRUISE", 112044, 112195, 692, "8fb6ae87cb90b9bb15a152c48072d4e41c5e06722ae03e00d01e59659d9315d4"),
        ("V882", 112196, 112409, 692, "e1110a9e7d1e808903e4291c00d0aea525185d9126c87a3f7ba7db9028c8e737"),
        ("V883", 112410, 112715, 692, "82c3dde44ef6bf0bdfa5305f200a21ad7343ac4f577249d6b582a46847315318"),
        ("V884", 112716, 113154, 692, "b1e5473451b2693c6b5830e0b3d1a07244a6d8ccdce3bb1bc0aecff04ec2df44"),
        ("LAND", 113155, 113249, 692, "1d0c55e393def8dad4e439575a0345af1ffc4daa51498554033a9aaf040e28a3"),
        ("V885", 113250, 113352, 692, "cb69e37b134097e42051a30e30e3a78c257494a874bf2f4b2c31ab6edda4cba4"),
        ("V886", 113353, 113811, 692, "c50d616fbc4d50caba20881cd855715939d8b32db7d42668bbd7835b75840e1a"),
        ("V887", 113812, 113902, 692, "51856dff1342791cf405306c1a772acbab3eccd79925e72db02af850a67c9ed0"),
        ("V888", 113903, 114275, 692, "bec2d485a215204f246d09302cc9bebfad5b63befbe86ac97e312aa975561afc"),
        ("D8", 114276, 114395, 692, "fc8ed4aec73b51e0327d206cd969e017c17de6c72c077e3d1632dc1dd10120e0"),
        ("D7", 114396, 114414, 692, "20e2a7dc5a487a6bb63dc60f9d528c6c3d4e2db0186701f658de7573fdac68e0"),
        ("D6", 114415, 114435, 692, "bc26ff508b5a85dbd7775ac9a209a87b38ed4376e69d3fe079b686be5071214f"),
        ("D5", 114436, 114471, 692, "0531ccf768e3801fbcfc43866f648f06399aa7dbd209d7d506ed12976681c4b3"),
        ("V889", 114472, 114717, 692, "2c65d23fa06b2f64a85343c974f5a9b0274c61e58ba40962b60662320c94309d"),
        ("D4", 114718, 114764, 692, "e6d66b621c5d064078259bc83910be6e6ea253f085cc2e28904197ee34c7d6d9"),
        ("V890", 114765, 114948, 692, "1717e6a8e9b27aede3d1c4aa5869304e1b392e4ed3cea1612841069364c9d2ef"),
        ("D3", 114949, 115145, 384, "29411a0acad1da7ec8bc8305da45da0738aec5304f09bd63daeb1d4c0573b42e"),
        ("EXIT", 115146, 115217, 384, "c400065cc0b321d36b553915dbd0d67cd2d7016561e451d5ed84c27d49d3672e"),
        ("CHURCH", 115218, 115586, 384, "fe2752f6254974b924fdeb1b5f4169f9faf2ca236c4b559679676839e709b606"),
    )
    for name, first, last, cells, digest in cuts:
        loop = {"D3": 115010, "CHURCH": 115425}.get(name, last)
        def encode(rows, patterns, repeat, limit):
            # Snow moves independently of menu input. Redraw the complete
            # viewport when these two clips return to their first idle frame.
            return pack_tiles(rows, patterns, repeat, limit, keyframes=(repeat,) if loop != last else ())
        clip = pack_section(raw if cells == 692 else view, tiles, first, last, 110300, loop, encode, cells)
        if hashlib.sha256(clip).hexdigest() != digest:
            raise ValueError(f"Unexpected SP37 picture sequence in {name}")
        (cd / f"A3{name}.BIN").write_bytes(clip)

def _church_dissolve(raw, tiles, first, last):
    # These two fades replace individual pixels across the entire viewport.
    # Positions use the Saturn bitmap pitch so the SH-2 can write each change.
    bank = bytearray(struct.pack(">H", last - first + 1))
    previous = None
    for frame in range(first, last + 1):
        ids = struct.unpack_from(">384H", raw, (frame - 121840) * 1384)
        image = bytearray(192 * 128 * 2)
        for cell, tile in enumerate(ids):
            for y in range(8):
                dst = ((cell // 24 * 8 + y) * 192 + cell % 24 * 8) * 2
                src = tile * 128 + y * 16
                image[dst:dst+16] = tiles[src:src+16]
        if previous is None:
            bank.extend(image)
        else:
            count_pos = len(bank)
            bank.extend(bytes(2))
            before = memoryview(previous).cast("H")
            after = memoryview(image).cast("H")
            for pixel, (old, new) in enumerate(zip(before, after)):
                if old != new:
                    bank.extend(struct.pack(">H", pixel // 192 * 512 + pixel % 192))
                    bank.extend(image[2*pixel:2*pixel+2])
            struct.pack_into(">H", bank, count_pos, (len(bank)-count_pos-2)//4)
        previous = image
    return bank


def prepare_church_entry(work, cd, pack_tiles):
    raw = (work / "frames.raw").read_bytes()
    tiles = (work / "tiles.raw").read_bytes()
    view = b"".join(raw[i:i+768] for i in range(0, len(raw), 1384))
    cuts = (
        ("V891", 121966, 122070, 692, "55f7b0f11bdcfa9434d1b3d7aa1760bb357097cacce2561f412a86e712f362e1"),
        ("REVEAL", 122071, 122134, 384, "ee538e23f67e147972ee8679b849df46eeee62950438042a997f7681fcc06a1e"),
        ("V892", 122135, 122268, 692, "38d1336588b4866989a506ec8ea35ab88ec2082cd66d9df48f1be01b0941e43f"),
        ("V893", 122269, 122515, 692, "2bf582f0fa8338f3f70f947a7a6e7eee29116d746987f32fe87558c0cd1c689b"),
        ("V894", 122516, 122874, 692, "72417c0e8a9715cd647b4d085d68a3f54ce82405efa200ea6f934ff046df359f"),
        ("V895", 122875, 122978, 692, "ffa9997105756ec88844b2a505fa96626a24ca11851213dc193b521696aa4b6e"),
        ("V896", 122979, 123383, 692, "f05885cb63f5e6b143a1426f8e54a1811050184e6cb57d728382f22bb5c2305c"),
        ("OPEN", 123384, 123590, 0, "8b86168346db89bedddf7b31982f848216a0b09ec6c1752e0d20767d5c310f30"),
        ("V897", 123593, 123943, 692, "9a91ee56ac928fd1f5015fc9832a815df490af10f780a0df76b3622a5d00593d"),
        ("AISLE", 123944, 124007, 0, "1aefa5d6bdc2d835953c4a9e1ba31c223d6e657f6501ecaf74f7affa7ac859ec"),
        ("PAN", 126637, 126763, 384, "63acaa73160892f055682da4f53d97faeb91df26c70536ea5f98f99ae5a85e4e"),
        ("SMALL", 126763, 126763, 384, "ba3693c476c6cd4a48fae158095cc46eee68ba2efef562b533ec3fd9496c6268"),
        ("LARGE", 126968, 126968, 384, "6e98ed46b785adfa94773df7d8c0fa27604cbfa97296d5205d31b69dc1b09268"),
        ("RFADE", 138157, 138205, 384, "8b95095dd3e2314cc5a049576cbcd5aaede5737035a7d4f1addaf110b4b2bd42"),
        ("CULT", 138789, 139300, 384, "d988f8aeacd7612629805b6e17689194afb986070c0e8897deadc433cd755515"),
        ("OUT", 130637, 130673, 384, "e649338baa673f0024770f36c25764c95cd46a76e86b5a4426dd0979eaa651e0"),
        ("REAR", 131203, 131227, 384, "c060188c8172d89aa48b829eb6ce1f1416ea563f368774991804caf4dfb29bf6"),
        ("REARID", 131227, 131227, 384, "3389ddf0088aca9a47622421023ec1d954268061f5b4f427e8bc65bb4f90a483"),
        ("FRAME", 132727, 132739, 384, "db15f9364d87c79a707bd03e1572fe36557707fef2d513f7c561d0064818cf30"),
        ("BACK", 133197, 133208, 384, "87873a2b70d5ddabefcae3cf79fa9850895f81dd9f7018243e39f7213993c5e9"),
    )
    for name, first, last, cells, digest in cuts:
        if name == "CULT":
            # Restart the bubbling vats from a full viewport after the entrance.
            def encode(rows, patterns, repeat, limit):
                return pack_tiles(rows, patterns, repeat, limit, keyframes=(repeat,))
            clip = pack_section(view, tiles, first, last, 121840, 138917, encode)
        elif name == "PAN":
            clip = pack_row_pan(view, tiles, first, last, 121840)
        elif cells:
            clip = pack_section(raw if cells == 692 else view, tiles, first, last, 121840, last, pack_tiles, cells)
        else:
            clip = _church_dissolve(raw, tiles, first, last)
        if hashlib.sha256(clip).hexdigest() != digest:
            raise ValueError(f"Unexpected church entry animation in {name}")
        (cd / f"A3{name}.BIN").write_bytes(clip)


# Frames in the original SP37 performances. V clips include both portraits.
CHURCH_PERFORMANCES = (
    (143500, 149660, (
        ("V898", 144067, 144270),
        ("V899", 144390, 144749),
        ("V900", 144750, 145801),
        ("V901", 145802, 146113),
        ("V902", 146114, 146517),
        ("V903", 146518, 146668),
        ("V904", 146669, 146773),
        ("V905", 146774, 147307),
        ("V906", 147308, 147472),
        ("V907", 147473, 148110),
        ("V908", 148111, 148364),
        ("V909", 148365, 148872),
        ("V910", 148873, 149034),
        ("V911", 149035, 149450),
        ("CYL", 144271, 144389),
        ("RETURN", 149451, 149660),
    ), "052d70eccc6e348af839ca6b1197b17ec1030394544abf650de373d042e1016e"),
    (152800, 164500, (
        ("V912", 153397, 154067),
        ("V913", 154068, 154273),
        ("V914", 154274, 154400),
        ("V915", 154401, 154720),
        ("DAD0", 154721, 154817),
        ("V916", 154818, 155533),
        ("V917", 155534, 155627),
        ("DB0A", 155628, 155673),
        ("V918", 155674, 155944),
        ("DB18", 155945, 155974),
        ("V919", 155975, 156352),
        ("V920", 156353, 157087),
        ("V921", 157088, 157442),
        ("V922", 157443, 157821),
        ("V923", 157822, 158088),
        ("V924", 158089, 158422),
        ("V925", 158423, 158997),
        ("V926", 158998, 159471),
        ("V927", 159472, 159656),
        ("DB56", 159657, 159769),
        ("V928", 159770, 160053),
        ("DB68", 160054, 160186),
        ("V929", 160187, 160508),
        ("DB7E", 160509, 160618),
        ("V930", 160619, 160876),
        ("V931", 160877, 161019),
        ("V932", 161020, 161229),
        ("V933", 161230, 161643),
        ("DBB2", 161644, 161700),
        ("V934", 161701, 161799),
        ("DBC8", 161800, 161863),
        ("V935", 161864, 162097),
        ("V936", 162098, 162190),
        ("V937", 162191, 162364),
        ("DBE6", 162365, 162409),
        ("V938", 162410, 162728),
        ("V939", 162729, 162780),
        ("DBF6", 162781, 162819),
        ("V940", 162820, 163378),
        ("DC18", 163379, 163415),
        ("V941", 163416, 163652),
        ("V942", 163653, 164010),
        ("DOOR", 164011, 164074),
        ("DOOR2", 164075, 164193),
        ("DC40", 164194, 164239),
        ("HALL2", 164240, 164271),
    ), "f1676ca25c6bfaa91bac20ea9bf433efdc8a96873e48a23971b562f5512d9ebd"),
    (165501, 165942, (
        ("RIN", 165612, 165661),
        ("RDOOR1", 165662, 165728),
        ("RDOOR2", 165729, 165757),
        ("RDOOR3", 165758, 165800),
        ("RDOOR4", 165801, 165858),
        ("RHALL1", 165859, 165911),
        ("RHALL2", 165912, 165942),
    ), "347a707ea1c0b7f6fc704ae7b62977a6f2882e0896d2f6fe9d28222a34eff4c3"),
    (167600, 176676, (
        ("V943", 167766, 168117),
        ("V944", 168118, 168523),
        ("E12A", 168524, 168577),
        ("E12B", 168578, 168630),
        ("DC99A", 168631, 168735),
        ("DC99B", 168736, 168839),
        ("V945", 168840, 169095),
        ("V946", 169096, 169274),
        ("V947", 171290, 172096),
        ("E13A", 172097, 172149),
        ("E13B", 172150, 172202),
        ("DCF0A", 172203, 172277),
        ("DCF0BA", 172278, 172315),
        ("DCF0BB", 172316, 172352),
        ("ENDIN", 172726, 172888),
        ("V951", 172889, 173032),
        ("V952", 173033, 173185),
        ("V953", 173186, 173287),
        ("V954", 173288, 173657),
        ("V955", 173658, 173847),
        ("ENDTWO", 173848, 173884),
        ("V956", 173885, 174080),
        ("V957", 174081, 174234),
        ("V958", 174235, 174738),
        ("V959", 174739, 175064),
        ("V960", 175065, 175519),
        ("V961", 175520, 176075),
        ("V963", 176076, 176165),
        ("V964", 176166, 176468),
        ("V965", 176469, 176676),
    ), "11f92ccd5bccb705894c0d9fee4320e71fee3655109b574dd2dbc9b9ffd420ca"),
    (172415, 173206, (
        ("FAILIN", 172661, 172767),
        ("V950", 172768, 173169),
        ("FAILFX", 173170, 173206),
    ), "96045f01176b88fb01ff5229959f2f0359809e5634b2361584ad26d361f58711"),
    (176677, 194174, (
        ("E0AD", 176677, 176852),
        ("V966", 176853, 177199),
        ("V967", 177200, 177418),
        ("V968", 177419, 177976),
        ("V969", 177977, 178238),
        ("V970", 178239, 178463),
        ("V971", 178464, 178755),
        ("E0E7", 178756, 178801),
        ("V972", 178802, 179272),
        ("V973", 179273, 179471),
        ("V974", 179472, 180244),
        ("E10D", 180245, 180289),
        ("V975", 180290, 180794),
        ("V976", 180795, 181415),
        ("V977", 181416, 181925),
        ("V978", 181926, 182237),
        ("V979", 182238, 183018),
        ("V980", 183019, 183523),
        ("V981", 183524, 184198),
        ("E152", 184199, 184262),
        ("V982", 184263, 184465),
        ("V983", 184466, 185003),
        ("V984", 185004, 185459),
        ("V985", 185460, 185718),
        ("V986", 185719, 186629),
        ("E180", 186630, 186674),
        ("V987", 186675, 187111),
        ("V988", 187112, 187670),
        ("V989", 187671, 188005),
        ("V990", 188006, 188423),
        ("V991", 188424, 188558),
        ("V992", 188559, 188874),
        ("V993", 188875, 189105),
        ("V994", 189106, 189348),
        ("E1C8", 189349, 189398),
        ("V995", 189399, 189713),
        ("V996", 189714, 190291),
        ("E1EF", 190292, 190372),
        ("V997", 190373, 190633),
        ("E1FD", 190634, 190678),
        ("V998", 190679, 191069),
        ("V999", 191070, 191480),
        ("V1000", 191481, 191675),
        ("E21B", 191676, 191720),
        ("V1001", 191721, 192250),
        ("V1002", 192251, 192681),
        ("V1003", 192682, 193023),
        ("V1004", 193024, 193362),
        ("E24E", 193363, 193458),
        ("V1005", 193459, 193618),
        ("V1006", 193619, 193820),
        ("V1007", 193821, 194174),
    ), "ec64c65ede88d95e3bce5ed435ad3e57773973aa174884ec80b875c07b2df6f5"),
    (194175, 203082, (
        ("E276", 194175, 194274),
        ("V1008", 194275, 194365),
        ("V1009", 194366, 194822),
        ("E299", 194823, 195274),
        ("V1010", 195275, 195447),
        ("V1011", 195448, 195628),
        ("V1012", 195629, 195882),
        ("V1013", 195883, 196753),
        ("E2CE", 196754, 196798),
        ("V1014", 196799, 197289),
        ("E2E0", 197290, 197333),
        ("V1015", 197334, 197658),
        ("V1016", 197659, 198063),
        ("E2F7", 198064, 198108),
        ("V1017", 198109, 198431),
        ("V1018", 198432, 198639),
        ("V1019", 198640, 199058),
        ("V1020", 199059, 199430),
        ("E31B", 199431, 199475),
        ("V1021", 199476, 199980),
        ("V1022", 199981, 200861),
        ("V1023", 200862, 201439),
        ("V1024", 201440, 201889),
        ("V1025", 201890, 202055),
        ("V1026", 202056, 203082),
    ), "e3f19ecfe21bab9256222c9e39adb0ef8a223e7a806796ed256e1c06410e53e9"),
    (203083, 213504, (
        ("E35A", 203083, 203227),
        ("V1027", 203228, 203586),
        ("V1028", 203587, 203935),
        ("E376", 203936, 203975),
        ("V1029", 203976, 204216),
        ("V1030", 204217, 204671),
        ("V1031", 204672, 204909),
        ("E39F", 204910, 204990),
        ("V1032", 204991, 205338),
        ("V1033", 205339, 205494),
        ("V1034", 205495, 206104),
        ("V1035", 206105, 206330),
        ("E3CE", 206331, 206432),
        ("V1036", 206433, 206875),
        ("V1037", 206876, 207336),
        ("V1038", 207337, 207976),
        ("E3E4", 207977, 208014),
        ("V1039", 208015, 208313),
        ("V1040", 208314, 209100),
        ("E40B", 209101, 209146),
        ("V1041", 209147, 209817),
        ("V1042", 209818, 210447),
        ("V1043", 210448, 210549),
        ("V1044", 210550, 211024),
        ("E42B", 211025, 211069),
        ("V1045", 211070, 211989),
        ("V1046", 211990, 212827),
        ("V1047", 212828, 213504),
    ), "92fb40cad1ec310cd1a2722cfa8342d917f62c2beac9a1fea4981aa20fe1a60d"),
    (213505, 224766, (
        ("E445", 213505, 213607),
        ("V1048", 213608, 214260),
        ("V1049", 214261, 214916),
        ("E468", 214917, 215009),
        ("V1050", 215010, 215145),
        ("V1051", 215146, 215464),
        ("V1052", 215465, 215953),
        ("E495", 215954, 216035),
        ("V1053", 216036, 216403),
        ("V1054", 216404, 216916),
        ("E4B0", 216917, 216961),
        ("V1055", 216962, 217967),
        ("V1056", 217968, 218294),
        ("V1057", 218295, 218527),
        ("E4D5", 218528, 218571),
        ("V1058", 218572, 219157),
        ("V1059", 219158, 219477),
        ("E4E5", 219478, 219522),
        ("V1060", 219523, 219906),
        ("V1061", 219907, 220193),
        ("V1062", 220194, 220522),
        ("V1063", 220523, 221217),
        ("E514", 221218, 221262),
        ("V1064", 221263, 221736),
        ("V1065", 221737, 222478),
        ("V1066", 222479, 222754),
        ("V1067", 222755, 223411),
        ("V1068", 223412, 223821),
        ("V1069", 223822, 224584),
        ("V1070", 224585, 224766),
    ), "3bf09134acc030d71067c24a8d7fe99a6f9d3b5f59d045853efaa5f9754cf54b"),
    (224767, 238035, (
        ("E559", 224767, 224912),
        ("V1071", 224913, 225269),
        ("V1072", 225270, 225690),
        ("V1073", 225691, 226160),
        ("E57B", 226161, 226213),
        ("V1074", 226214, 227225),
        ("V1075", 227226, 227661),
        ("E58F", 227662, 227714),
        ("V1076", 227715, 227978),
        ("V1077", 227979, 228344),
        ("V1078", 228345, 228658),
        ("V1079", 228659, 228845),
        ("E5B6", 228846, 228902),
        ("V1080", 228903, 229394),
        ("V1081", 229395, 229589),
        ("V1082", 229590, 229798),
        ("E5D0", 229799, 229856),
        ("V1083", 229857, 230256),
        ("V1084", 230257, 230676),
        ("E5EC", 230677, 230735),
        ("V1085", 230736, 231062),
        ("V1086", 231063, 231627),
        ("V1087", 231628, 231959),
        ("V1088", 231960, 232533),
        ("E60C", 232534, 232662),
        ("V1089", 232663, 233581),
        ("V1090", 233582, 233841),
        ("V1091", 233842, 234182),
        ("E62A", 234183, 234332),
        ("V1092", 234333, 234891),
        ("V1093", 234892, 235600),
        ("V1094", 235601, 235833),
        ("V1095", 235834, 236504),
        ("V1096", 236505, 237103),
        ("V1097", 237104, 237738),
        ("E665", 237739, 237800),
        ("V1098", 237801, 238035),
    ), "3117687c178d7b153d89394400a80fe53f14ac945951730839dc01a3184d1885"),
    (238036, 248748, (
        ("E673", 238036, 238097),
        ("V1099", 238098, 238773),
        ("V1100", 238774, 239256),
        ("E683", 239257, 239373),
        ("V1101", 239374, 239656),
        ("V1102", 239657, 239800),
        ("E697", 239801, 240038),
        ("V1103", 240039, 240260),
        ("E6B8", 240261, 240577),
        ("V1104", 240578, 240701),
        ("E6E6", 240702, 240819),
        ("V1105", 240820, 241011),
        ("V1106", 241012, 241198),
        ("V1107", 241199, 241838),
        ("V1108", 241839, 242312),
        ("V1109", 242313, 242788),
        ("V1110", 242789, 243372),
        ("E71E", 243373, 243529),
        ("V1111", 243530, 244005),
        ("V1112", 244006, 245134),
        ("V1113", 245135, 245611),
        ("E744", 245612, 245721),
        ("V1114", 245722, 245819),
        ("V1115", 245820, 246477),
        ("V1116", 246478, 247024),
        ("E76E", 247025, 247081),
        ("V1117", 247082, 247235),
        ("E77C", 247236, 247300),
        ("V1118", 247301, 247964),
        ("V1119", 247965, 248279),
        ("V1120", 248280, 248748),
    ), "851a5e9c4c6e429da75441465f5a444bcda5aea89d679eca988f0f94f2e01159"),
    (248749, 256970, (
        ("E79A", 248749, 248875),
        ("V1121", 248876, 249217),
        ("V1122", 249218, 249728),
        ("V1123", 249729, 250131),
        ("E7B4", 250132, 250197),
        ("V1124", 250198, 251167),
        ("V1125", 251168, 251271),
        ("E7D4", 251272, 251316),
        ("V1126", 251317, 251390),
        ("V1127", 251391, 251559),
        ("E7E8", 251560, 251623),
        ("V1128", 251624, 252025),
        ("V1129", 252026, 252212),
        ("E7FC", 252213, 252275),
        ("V1130", 252276, 252814),
        ("E80A", 252815, 252865),
        ("V1131", 252866, 252968),
        ("E814", 252969, 253032),
        ("V1132", 253033, 253645),
        ("V1133", 253646, 253805),
        ("E836", 253806, 253871),
        ("V1134", 253872, 254412),
        ("V1135", 254413, 254607),
        ("E84A", 254608, 254675),
        # SP38 plays the second speaker inside the recording for 1136.
        ("V1136", 254676, 255061),
        ("E854", 255062, 255114),
        ("V1138", 255115, 255255),
        ("V1139", 255256, 255622),
        ("V1140", 255623, 256310),
        ("V1141", 256311, 256970),
    ), "ae67153b32dc9cbdff89f77aa137bdf150a8ee90898aff8fa3786fabbddd0aff"),
    (256478, 260515, (
        ("E882", 256478, 256970),
        ("E8A1", 256971, 257052),
        ("E8AD", 257053, 257209),
        ("M8C2", 257210, 257390),
        ("E8E3", 257391, 257451),
        ("V1142", 257452, 257614),
        ("E8F5", 257615, 257660),
        ("V1143", 257661, 257827),
        ("V1144", 257828, 257997),
        ("V1145", 257998, 258474),
        ("V1146", 258475, 258595),
        ("E92B", 258596, 258688),
        ("E937", 258689, 258812),
        ("E950", 258813, 258894),
        ("V1147", 258895, 259202),
        ("V1148", 259203, 259352),
        ("E968", 259353, 259416),
        ("V1149", 259417, 259656),
        ("V1150", 259657, 260151),
        ("E98A", 260152, 260200),
        ("V1151", 260201, 260291),
        ("V1152", 260292, 260515),
    ), "ff93f24066d7488b31c1c83a70c8fbd6ca644fb721ce4783fa3742b870076b82"),
    (260516, 269219, (
        ("E99E", 260516, 260659),
        ("V1153", 260660, 261025),
        ("E9AC", 261026, 261092),
        ("V1154", 261093, 261483),
        ("V1155", 261484, 262084),
        ("V1156", 262085, 262415),
        ("V1157", 262416, 262594),
        ("V1158", 262595, 262974),
        ("V1159", 262975, 263069),
        ("E9D8", 263070, 263132),
        ("V1160", 263133, 263419),
        ("E9E6", 263420, 263460),
        ("V1161", 263461, 263501),
        ("E9F0", 263502, 263566),
        ("V1162", 263567, 263793),
        ("E9FE", 263794, 263859),
        ("V1163", 263860, 264240),
        ("V1164", 264241, 264421),
        ("EA12", 264422, 264485),
        ("V1165", 264486, 264741),
        ("V1166", 264742, 264858),
        ("EA26", 264859, 264922),
        ("V1167", 264923, 265279),
        ("V1168", 265280, 265565),
        ("V1169", 265566, 265682),
        ("EA52", 265683, 265741),
        ("V1170", 265742, 266321),
        ("EA71", 266322, 266389),
        ("V1171", 266390, 266623),
        ("V1172", 266624, 266979),
        ("V1173", 266980, 267461),
        ("EA8F", 267462, 267524),
        ("V1174", 267525, 267758),
        ("EA9D", 267759, 267900),
        ("EAAC", 267901, 267963),
        ("V1175", 267964, 268279),
        ("EABA", 268280, 268341),
        ("V1176", 268342, 268556),
        ("EAC8", 268557, 268614),
        ("V1177", 268615, 268786),
        ("EADA", 268787, 268849),
        ("V1178", 268850, 269075),
        ("EAE8", 269076, 269123),
        ("V1179", 269124, 269219),
    ), "20a684168cdffcb20025decbd58643da377e2b161f763bc2c0b14d1b5975f4b2"),
    (269220, 276599, (
        ("EB0B", 269220, 269450),
        ("EB1F", 269451, 269601),
        ("EB56", 270580, 270688),
    ), "39191f955d746767eebf002e944bd0292a533b610eaff4f055272e7b4922b78a"),
    (276567, 277100, (
        ("EB8C", 276567, 277100),
    ), "f3080fc6a41d556a1f4d39f9000355c868fbc65e42f4e62e7c4410b702a7ac0d"),
    (324800, 329800, (
        ("ED64", 324892, 324895),
        ("ED6E", 327618, 329695),
    ), "78e451c0686ce472c38ed86c69849981810a958a01546b826535e8fd6e1c3246"),
    (329696, 331091, (
        ("EE28", 329696, 329867),
        ("V1182", 329868, 330205),
        ("V1183", 330206, 330455),
        ("V1184", 330456, 331090),
    ), "ac1527bd20e075b2e1cc10da3158d754a3b92f69ff5f4a87ee1c0fcfa88a5bc8"),
)


def prepare_church_performance(work, cd, pack_tiles, origin, cuts, expected):
    raw=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    view=b"".join(raw[i:i+768] for i in range(0,len(raw),1384))
    digest=hashlib.sha256()
    for name,first,last in cuts:
        faces=name.startswith("V")
        loop=149490 if name=="RETURN" else last
        def encode(rows,patterns,repeat,limit):
            return pack_tiles(rows,patterns,repeat,limit,keyframes=(repeat,) if loop!=last else ())
        clip=pack_section(raw if faces else view,tiles,first,last,origin,loop,encode,692 if faces else 384)
        digest.update(clip)
        (cd/f"A3{name}.BIN").write_bytes(clip)
    if digest.hexdigest()!=expected:
        raise ValueError("Unexpected US culturing room performance")
    if origin==269220:
        prepare_farewell_tracks(work, cd, pack_tiles)
    if origin == 324800:
        from prepare_briefing import timed_bank

        clock = {frame: (track, lba, status) for frame, track, lba, status in
                 (map(int, row.split()) for row in (work / "transport.tsv").read_text().splitlines())}

        def departure_clip(first, last):
            return pack_section(view, tiles, first, last, origin, last, pack_tiles)

        bank = timed_bank(departure_clip, clock, 18, 196866, (324896, 327611))
        if hashlib.sha256(bank).hexdigest() != "0807ba334bdb909b7a955040106610c96af70281a84463a4cd9a2b4dbc4aa65f":
            raise ValueError("Unexpected US departure animation for track 18")
        (cd / "A3CD18.BIN").write_bytes(bank)
    if origin==152800:
        patterns=(work/"SWARM.BIN").read_bytes()
        if hashlib.sha256(patterns).hexdigest()!="58c5b6703b2fc0b60548c96d7ce2b14121c2582afe9a52efc65310ebe7ac0e81":
            raise ValueError("Unexpected Stage 12 sprite patterns or palette")
        (cd/"SWARM.BIN").write_bytes(patterns)

    if origin==167600:
        patterns=(work/"FINAL13.BIN").read_bytes()
        if hashlib.sha256(patterns).hexdigest()!="4be0c44b4de9fad3a85abe28847e75413c200a92009b277cd705868f9f03e8a6":
            raise ValueError("Unexpected Stage 13 sprite patterns or palette")
        (cd/"FINAL13.BIN").write_bytes(patterns)
        patterns=(work/"FINAL14.BIN").read_bytes()
        if hashlib.sha256(patterns).hexdigest()!="ce805a4d98d59cdfbc19e1cfa670d6692588971343a0e95208a4624f4c7b759f":
            raise ValueError("Unexpected Stage 14 sprite patterns or palette")
        (cd/"FINAL14.BIN").write_bytes(patterns)


def prepare_farewell_tracks(work, cd, pack_tiles):
    from prepare_briefing import timed_bank

    raw = (work / "frames.raw").read_bytes()
    tiles = (work / "tiles.raw").read_bytes()
    clock = {frame: (track, lba, status) for frame, track, lba, status in
             (map(int, row.split()) for row in (work / "transport.tsv").read_text().splitlines())}

    def clip(first, last):
        return pack_section(raw, tiles, first, last, 269220, last, pack_tiles, 692, 0x100000)

    for number, start_lba, first, stop in ((16, 188155, 269602, 270573),
                                           (17, 189442, 270689, 276558)):
        bank = timed_bank(clip, clock, number, start_lba, (first, stop))
        if hashlib.sha256(bank).hexdigest() != ('58650de9cfcbafe282a62d16a7ebd513fe95834a5229eb61355468b37bc2cce3', '1494a781a9ab5568c26b0e4a0ebd7f90dfc9ad9ef3e2ea350e4fbf080563df2c')[number - 16]:
            raise ValueError(f"Unexpected US ending animation for track {number}")
        (cd / f"A3CD{number}.BIN").write_bytes(bank)
