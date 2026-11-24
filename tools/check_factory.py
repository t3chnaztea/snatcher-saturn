"""Replay the factory flight, exit, and first investigation on both systems."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import wave
from concurrent.futures import ThreadPoolExecutor

root=Path(__file__).resolve().parents[1]
uncut=root.parent/"snatcher-uncut"
sonic=root.parent/"sonic-cd-saturn"
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--disc",required=True,type=Path)
parser.add_argument("--backup",required=True,type=Path,help="Beetle internal.bin saved in the parking lot")
parser.add_argument("--cockpit",required=True,type=Path,help="Sega CD state at Metal Gear's destination prompt")
parser.add_argument("--interior", action="store_true",help="continue through the emergency call and the first interior Move > Advance")
parser.add_argument("--passage", action="store_true", help="continue past Little John through the next Move > Advance")
parser.add_argument("--gibson", action="store_true", help="continue to the identification of Gibson")
parser.add_argument("--evidence", action="store_true", help="find the key and paper in Gibson’s clothing")
parser.add_argument("--hand", action="store_true", help="find the hair and skin sample in Gibson’s right hand")
parser.add_argument("--chip", action="store_true", help="inspect Little John and recover his memory chip on the first visit")
args=parser.parse_args()
if args.chip:
    if args.passage or args.gibson or args.evidence or args.hand:
        parser.error("--chip branches from the first interior visit")
    args.interior = True
if args.hand:
    args.evidence = True
if args.evidence:
    args.gibson = True
if args.gibson:
    args.passage = True
if args.passage:
    args.interior = True
out=Path(tempfile.mkdtemp(prefix="factory-",dir=root/"build"))
flags=shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","libpng"],text=True))
subprocess.run(["cc","-O2","-I"+str(uncut/"tools/harness"),"-I"+str(sonic/".deps/beetle-saturn/libretro-common/include"),
                root/"tools/factory_core.c",*flags,"-o",out/"runner"],check=True)

def run(target):
    saturn=target=="saturn"
    d=out/target
    d.mkdir()
    buttons=([(1800,"20"),(2000,"800"),(2300,"800"),(3100,"800"),(4100,"800"),(4600,"20"),(4900,"800"),
              (8900,"800"),(9200,"800"),(10300,"800"),(10600,"20"),(10800,"800"),(11100,"800")] if saturn else
             [(60,"100"),(160,"20"),(250,"100"),(3400,"100"),(3700,"100"),(4500,"100"),
              (4750,"20"),(4950,"100"),(5300,"100")])
    if saturn:
        for enabled, name in [(args.interior,"interior"), (args.passage,"passage"),
                              (args.gibson,"gibson"), (args.evidence,"evidence"), (args.hand,"hand")]:
            if enabled:
                for line in (root/f"tools/routes/factory-{name}.pad").read_text().splitlines():
                    if line and not line.startswith("#"):
                        start, _, key = line.split()
                        buttons.append((int(start)-70300, key))
    else:
        if args.interior:
            buttons.extend((5700+n,"100") for n in range(60,3650,150))
            buttons.extend([(11600,"10"),(11800,"100"),(12400,"100"),(12800,"100"),(13200,"100"),
                            (14600,"100"),(15000,"100"),(15400,"100"),(15800,"100"),(16200,"100")])
        if args.passage:
            buttons.extend((20800+n,"100") for n in (60,160,300,460))
        if args.gibson:
            buttons.extend((22250+n,"100") for n in (60,200,400,700))
            buttons.extend((23850+n,key) for n,key in [(60,"20"),(190,"100"),(320,"100"),
                                                       (1750,"100"),(2100,"100")])
        if args.evidence:
            keys = ["20","100","100","20","100","100","100","100","100","20","100","100","10","100"]
            times = [26700,26950,27200,27450,27700,28300,28550,28800,29050,29400,29700,30350,30600,30900]
            buttons.extend(zip(times, keys))
        if args.hand:
            start = 31500
            for sequence in ["BDCCCCCC", "CCCC", "CCDDCCC", "C"]:
                keys = {"B":"1", "D":"20", "C":"100"}
                buttons.extend((start+90+i*200, keys[key]) for i,key in enumerate(sequence))
                start += 400+200*len(sequence)
    if args.chip:
        start = 26600 if saturn else 20800
        damage = 4730 if saturn else 5620
        if saturn:
            for line in (root/"tools/routes/factory-memory-chip.pad").read_text().splitlines():
                if line and not line.startswith("#"):
                    frame, _, key = line.split()
                    buttons.append((int(frame)-70300,key))
        else:
            for offset,spacing,keys in [(250,220,"DCDDDC"),(2550,240,"CDCDDDC"),(4880,240,"C"),
                                        (damage+150,240,"CCCCCC"),(damage+2240,240,"C"),
                                        (damage+3130,240,"DDDDC"),(damage+8820,240,"C")]:
                buttons.extend((start+offset+i*spacing, "100" if k=="C" else "20") for i,k in enumerate(keys))
    pad=d/"route.pad"
    pad.write_text("".join(f"{n} {n+(8 if (args.evidence and not saturn and n>=26700) or args.chip and n>=start else 2)} {b}\n" for n,b in buttons))
    env={k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env.update(SNATCHER_AUDIO=str(d/"drive.wav"),SNATCHER_FRAME_HASHES=str(d/"frames.txt"),
               SNATCHER_CAPTURE_PREFIX=str(d/"frame"),SNATCHER_CAPTURE_EVERY="100",
               SNATCHER_PAD="generic" if saturn else "genesis3")
    if saturn:
        env.update(SNATCHER_BACKUP_INPUT=str(args.backup.resolve()),SNATCHER_BACKUP_OUTPUT=str(d/"internal.bin"))
    frames=(26600 if args.interior else 11600) if saturn else (20800 if args.interior else 5800)
    if args.passage:
        frames = 29000 if saturn else 22250
    if args.gibson:
        frames = 34700 if saturn else 26500
    if args.evidence:
        frames = 38200 if saturn else 31500
    if args.hand:
        frames = 45200 if saturn else 37100
    if args.chip:
        frames = start+damage+9600
    with (d/"core.log").open("w") as log:
        subprocess.run([out/"runner",
            sonic/".deps/beetle-saturn/mednafen_saturn_libretro.dylib" if saturn else uncut/".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib",
            sonic/"assets/private" if saturn else uncut/"private/bios",d,
            args.disc.resolve() if saturn else uncut/"private/discs/segacd-usa/Snatcher.cue",
            str(frames),d/"end.png",pad,"-" if saturn else args.cockpit.resolve(),
            d/"end.state" if args.hand and not saturn else "-"],
            env=env,check=True,stdout=log,stderr=log)
    with (d/"audio-windows.json").open("w") as receipt:
        subprocess.run(["python3",root/"tools/check_drive_audio.py",d/"drive.wav",
                        uncut/"private/discs/segacd-usa/Snatcher.bin"],stdout=receipt,check=True)
    return {int(n):(scene,panel) for n,scene,panel in (row.split() for row in (d/"frames.txt").read_text().splitlines())}

with ThreadPoolExecutor(2) as pool:
    retail,saturn=pool.map(run,("retail","saturn"))
# Anchor the trip to its measured CD audio onset, so a similar static pose
# elsewhere in the game cannot count as a match. Landing follows a CD seek.
def clock(label,trace):
    d=out/label
    start=json.loads((d/"audio-windows.json").read_text())[0]["start_sample"]
    with wave.open(str(d/"drive.wav")) as wav:
        rate=max(trace)*wav.getframerate()/wav.getnframes()
    return start/44100,rate

rstart,rfps=clock("retail",retail)
sstart,sfps=clock("saturn",saturn)
def predicted(n):
    return round((n/rfps-rstart+sstart)*sfps)

def nearest(n,center,slack):
    return min((f for f in range(center-slack,center+slack+1)
                if f in saturn and saturn[f][0]==retail[n][0]),
               key=lambda f:abs(f-center),default=None)

landing=nearest(2800,predicted(2800),240)
flight={}
for n in range(560,2881,80):
    if n==2560: continue  # CD module change between shots
    if n>=2632:
        flight[n]=nearest(n,round((landing or predicted(2800))+(n-2800)*sfps/rfps),16)
    else:
        flight[n]=nearest(n,predicted(n),65 if n<596 else 16)
menus={}
for name,r,s in [("arrival",3350,8800),("destinations",3600,9100),("outside",4450,10200),
                 ("outside-menu",4650,10500),("look",5200,11000),("look-building",5700,11400)]:
    menus[name]=saturn[s][1]==retail[r][1]
interior={}
if args.interior:
    for name,r,s in [("enter-unlocked",11300,18000),("enter-warning",12200,18700),
                     ("draw-button",12700,19100),("save-warning",13000,19400),
                     ("entrance",14400,21000),("videophone",14800,21300),("commands",15200,21700),
                     ("move",15600,22200),("advance",16000,22600),("ahead",20600,26500)]:
        menus[name]=saturn[s][1]==retail[r][1]
    interior["entrance_art"]=saturn[21700][0]==retail[15200][0]
    # The falling water and the palette cycles run independently on this shot.
    # Count complete, distinct pictures during the idle command menu.
    native={saturn[f][0] for f in range(24900,26500)}
    original={retail[f][0] for f in range(19200,20700)}
    matching=len(original & native)
    interior["distinct_advance_frames"]=matching
    if matching<12: raise SystemExit(f"Only {matching} distinct matching factory frames")
if args.passage:
    for name, r, s in [("passage-move", 20900, 26810), ("gibson-warning", 21070, 27120),
                       ("caution-warning", 21205, 27360)]:
        menus[name] = saturn[s][1] == retail[r][1]
    interior["passage_art"] = saturn[29000][0] == retail[22250][0]
    menus["passage"] = saturn[29000][1] == retail[22250][1]
if args.gibson:
    interior["figure_art"] = saturn[30950][0] == retail[23750][0]
    menus["figure"] = saturn[30950][1] == retail[23750][1]
    interior["gibson_art"] = saturn[34700][0] == retail[26500][0]
    menus["gibson"] = saturn[34700][1] == retail[26500][1]
if args.evidence:
    # Each clue overlays different item art on Gibson. An unchanged portrait
    # on both consoles must not pass either item comparison.
    interior["different_clues"] = len({retail[f][0] for f in (26500,28450,30100)}) == 3
    for label, r, s in [("key",28450,36100), ("paper",30100,37350), ("discoveries",31500,38200)]:
        menus[label] = saturn[s][1] == retail[r][1]
        interior[label+"_art"] = saturn[s][0] == retail[r][0]
if args.hand:
    menus["hand-samples"] = saturn[45200][1] == retail[37100][1] != retail[31500][1]
    interior["hand-samples-art"] = saturn[45200][0] == retail[37100][0]
if args.chip:
    for label,r,s in [("wreck-condition",22800,28900),("laser-damage",26300,31200),
                      ("functions-lost",26700,31600),("memory-intact",27000,31900),
                      ("chip-listed",29100,34000),("chip-selected",30350,35200),
                      ("after-recovery",32000,37000),("chip-removed",35800,40700)]:
        menus[label] = saturn[s][1] == retail[r][1]
    menus["chip-list-changed"] = retail[29100][1] != retail[35800][1]
with args.disc.with_suffix(".bin").open("rb") as stream:
    digest=hashlib.file_digest(stream,"sha256").hexdigest()
(out/"receipt.json").write_text(json.dumps(dict(bin_sha256=digest,matching_poses=flight,dialogue=menus,interior=interior),indent=2)+"\n")
print(out)
if not all(menus.values()) or not all(flight.values()) or not all(interior.values()): raise SystemExit("Some retail frames differ; see receipt")
