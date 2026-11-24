"""Cold boot from the post-factory slot-three backup through Napoleon's call through Gibson's garden and the purchase at Plato's Cavern."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from PIL import Image

root = Path(__file__).resolve().parents[1]
uncut = root.parent / "snatcher-uncut"
sonic = root.parent / "sonic-cd-saturn"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--disc", required=True, type=Path)
parser.add_argument("--backup", required=True, type=Path)
args = parser.parse_args()
out = Path(tempfile.mkdtemp(prefix="hq-videophone-", dir=root/"build"))
flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "libpng"], text=True))
subprocess.run(["cc", "-O2", "-I"+str(uncut/"tools/harness"),
                "-I"+str(sonic/".deps/beetle-saturn/libretro-common/include"),
                root/"tools/factory_core.c", *flags, "-o", out/"runner"], check=True)
env = {k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
env.update(SNATCHER_PAD="generic", SNATCHER_BACKUP_INPUT=str(args.backup.resolve()),
           SNATCHER_BACKUP_OUTPUT=str(out/"internal.bin"), SNATCHER_FRAME_HASHES=str(out/"frames.txt"), SNATCHER_AUDIO=str(out/"mix.wav"))
with (out/"core.log").open("w") as log:
    subprocess.run([out/"runner", sonic/".deps/beetle-saturn/mednafen_saturn_libretro.dylib",
                    sonic/"assets/private", out, args.disc.resolve(), "94200", out/"end.png",
                    root/"tools/routes/hq-videophone.pad"], env=env, stdout=log, stderr=log, check=True)

def hashes(checkpoint):
    original = uncut/"build/evidence/m5/playthrough-lane/natural-run"/str(checkpoint)/"screen.png"
    picture = Image.open(original).convert("RGB").point(lambda c:(min(7,(c+17)//34)*255//7*31//255)<<3)
    result = []
    for region in ((32,8,224,136), (16,142,232,224)):
        value = 14695981039346656037
        for color in picture.crop(region).tobytes():
            value = ((value^color)*1099511628211)&0xffffffffffffffff
        result.append(f"{value:016x}")
    return result

frames = [row.split()[1:] for row in (out/"frames.txt").read_text().splitlines()]
cursor = 10000
matches = {}
# The challenge and keyboard checkpoints compare the entire picture area
# and text panel. Engineering's background has independent moving actors.
route = [(1444,(0,1)), (1446,(0,1)), (1450,(0,))]
route.extend((n,(0,1)) for n in range(1451,1464))
route.extend(((1465,(1,)), (1492,(0,1)), (1500,(1,)), (1501,(0,1))))
# The plaza signs and Napoleon's skyline run independently of the text.
# Check both regions where the source pose occurs during the matching page.
route.extend([
    (1503,(1,)), (1734,(1,)), (1740,(0,1)), (1748,(0,1)),
    (1753,(0,1)), (1754,(1,)), (1755,(1,)), (1756,(1,)),
    (1771,(0,1)), (1772,(0,1)), (1792,(0,1)), (1815,(0,1)),
    (1842,(0,1)), (1850,(0,1)), (1870,(1,)), (1871,(0,1)),
    (1895,(0,1)), (1913,(0,1)), (1919,(0,1)), (1940,(0,1)),
    (1954,(1,)), (1971,(0,1)), (1977,(0,1)), (1978,(0,1)),
    (1979,(0,1)), (1985,(1,)), (1987,(1,)), (1994,(1,)),
    (2000,(0,1)), (2007,(0,1)), (2008,(0,1)), (2009,(0,1)),
    (2016,(0,1)), (2022,(0,1)), (2037,(1,)), (2038,(1,)),
    (2078,(1,)), (2109,(0,1)), (2110,(0,1)), (2129,(1,)),
    (2132,(1,)), (2133,(0,1)), (2157,(1,)), (2176,(0,1)),
    (2190,(1,)), (2204,(1,)), (2205,(0,1)), (2206,(0,1)),
    (2229,(0,1)), (2233,(0,1)), (2240,(0,1)), (2254,(0,1)), (2277,(0,1)),
    (2281,(0,1)), (2287,(0,1)), (2288,(0,1)), (2298,(1,)), (2303,(1,)),
    (2311,(1,)), (2313,(1,)), (2315,(1,)), (2323,(1,)), (2326,(1,)),
    (2328,(1,)), (2347,(1,)), (2352,(1,)), (2355,(1,)), (2357,(1,)), (2359,(1,)),
])
# The monitor scrolls through all thirteen sections of Gibson's report.
route.extend((n,(0,1)) for n in range(2364,2397))
route.extend((n,(0,1)) for n in (2400,2401,2406,2423,2460,2474,2476,
                                  2477,2482,2485,2505,2510,2511,2513))
route.append((2516,(1,)))
route.extend((n,(0,1)) for n in (2716,2717,2720,2725,2730))
route.extend((n,(1,)) for n in (2765,2773,2779))
route.extend((n,(0,1)) for n in (2787,2788,2795,2798,2820,2823,2827,2838))
route.extend(((2843,(1,)),(2845,(1,)),(2853,(0,1))))
for number, parts in route:
    expected = hashes(number)
    while cursor<len(frames) and any(frames[cursor][p]!=expected[p] for p in parts):
        cursor += 1
    if cursor==len(frames):
        raise ValueError(f"Missing retail checkpoint {number} in {out}")
    cursor += 1
    matches[number] = dict(frame=cursor, viewport=0 in parts, dialogue_panel=1 in parts)
# The original flight has two VDP controller sections. Frame 63 starts
# their motion. Frame 918 returns control to the arrival dialogue.
reference=out/"flight-reference"
reference.mkdir()
run=uncut/"build/evidence/m5/playthrough-lane/natural-run"
env={k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
env.update(SNATCHER_PAD="genesis3",SNATCHER_FRAME_HASHES=str(reference/"frames.txt"))
with (reference/"core.log").open("w") as log:
    subprocess.run([out/"runner",uncut/".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib",
                    uncut/"private/bios",reference,uncut/"private/discs/segacd-usa/Snatcher.cue",
                    "1082",reference/"end.png",run/"1501/input.pad",run/"1500/native.state"],
                   env=env,stdout=log,stderr=log,check=True)
motion=[row.split()[1] for row in (reference/"frames.txt").read_text().splitlines()][62:917]
if len(motion)!=855: raise ValueError("Incomplete Sega CD flight")
scene_hashes=[row[0] for row in frames]
cursor=matches[1500]["frame"]
flight=[]
for index,scene in enumerate(motion):
    if index and scene==motion[index-1]: continue
    try: cursor=scene_hashes.index(scene,cursor)+1
    except ValueError: raise ValueError(f"Missing flight pose at Sega CD frame {index+63}") from None
    flight.append((index+63,cursor))
# Verify the phase order and cadence during the call from the shop.
phone=out/"shop-phone-reference"
phone.mkdir()
env["SNATCHER_FRAME_HASHES"]=str(phone/"frames.txt")
with (phone/"core.log").open("w") as log:
    subprocess.run([out/"runner",uncut/".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib",
                    uncut/"private/bios",phone,uncut/"private/discs/segacd-usa/Snatcher.cue",
                    "320",phone/"end.png",os.devnull,run/"2717/native.state"],
                   env=env,stdout=log,stderr=log,check=True)
cycle=[row.split()[1] for row in (phone/"frames.txt").read_text().splitlines()]
if len(cycle)!=320 or len(set(cycle))!=8: raise ValueError("Incomplete retail phone animation")
shop_frame=next((i+1 for i in range(matches[2516]["frame"],matches[2730]["frame"])
                 if scene_hashes[i:i+len(cycle)]==cycle),None)
if shop_frame is None: raise ValueError("Missing 320 consecutive shop phone frames")
(out/"receipt.json").write_text(json.dumps(dict(frames=len(frames),checkpoints=matches,
    shop_phone_first_frame=shop_frame,shop_phone_frames=len(cycle),
    flight_source_frames=len(motion),flight_distinct=len(set(motion)),flight_matches=flight),indent=2)+"\n")
print(out)
