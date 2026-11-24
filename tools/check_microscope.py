"""Compare the two forensic scans with independent US Sega CD replays."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
uncut, sonic = root.parent/"snatcher-uncut",root.parent/"sonic-cd-saturn"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--disc",type=Path,required=True)
parser.add_argument("--backup",type=Path,required=True,help="slot two from check_factory_save.py")
parser.add_argument("--original",type=Path,required=True,help="original state at Investigate with Gibson selected and both samples available")
parser.add_argument("--organic",action="store_true",help="test organic compounds using a retail Investigate checkpoint with that option visible")
args = parser.parse_args()
out = Path(tempfile.mkdtemp(prefix="microscope-",dir=root/"build"))
flags = shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","libpng"],text=True))
subprocess.run(["cc","-O2","-I"+str(uncut/"tools/harness"),"-I"+str(sonic/".deps/beetle-saturn/libretro-common/include"),
                root/"tools/factory_core.c",*flags,"-o",out/"runner"],check=True)

def run(case):
    scan,system = case
    saturn = system=="saturn"
    folder = out/scan/system
    folder.mkdir(parents=True)
    if saturn:
        # Cold load slot two, open Look, then follow the same hand inspection as New Game.
        keys = [(1800,"20"),(2000,"800"),(2250,"20"),(2800,"800"),(3400,"20"),(3650,"800")]
        for line in (root/"tools/routes/factory-hand.pad").read_text().splitlines():
            if line and not line.startswith("#"):
                n,_,key = line.split()
                keys.append((int(n)-104350,key))
        if scan=="organic":
            # Examine the corpse once more to discover the organic compounds.
            keys.extend([(11400,"800"),(11700,"800"),(14800,"800"),
                         (15100,"20"),(15400,"20"),(15700,"20"),(16000,"800")])
        else:
            keys.append((11400,"20"))
            if scan=="skin": keys.append((11600,"20"))
            keys.append((11900,"800"))
    else:
        steps = {"hair":1,"skin":2,"organic":3}[scan]
        keys = [(90+200*i,"20") for i in range(steps)]
        keys.append((90+200*steps,"100"))
    pad = folder/"route.pad"
    pad.write_text("".join(f"{n} {n+(2 if saturn else 8)} {key}\n" for n,key in keys))
    env={k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env.update(SNATCHER_PAD="generic" if saturn else "genesis3",SNATCHER_FRAME_HASHES=str(folder/"frames.txt"),
               SNATCHER_AUDIO=str(folder/"mix.wav"),SNATCHER_CAPTURE_PREFIX=str(folder/"frame"),SNATCHER_CAPTURE_EVERY="120")
    if saturn: env.update(SNATCHER_BACKUP_INPUT=str(args.backup.resolve()),SNATCHER_BACKUP_OUTPUT=str(folder/"internal.bin"))
    with (folder/"core.log").open("w") as log:
        subprocess.run([out/"runner",sonic/".deps/beetle-saturn/mednafen_saturn_libretro.dylib" if saturn else uncut/".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib",
                        sonic/"assets/private" if saturn else uncut/"private/bios",folder,
                        args.disc.resolve() if saturn else uncut/"private/discs/segacd-usa/Snatcher.cue",
                        ("20800" if scan=="organic" else "17000") if saturn else "4500",folder/"end.png",pad,"-" if saturn else args.original.resolve()],
                       env=env,stdout=log,stderr=log,check=True)
    return [tuple(line.split()[1:]) for line in (folder/"frames.txt").read_text().splitlines()]

results={}
scans=("organic",) if args.organic else ("hair","skin")
cases=[(scan,system) for scan in scans for system in ("saturn","retail")]
with ThreadPoolExecutor(4) as pool:
    traces=dict(zip(cases,pool.map(run,cases)))
for scan in scans:
    saturn,retail=traces[scan,"saturn"],traces[scan,"retail"]
    start,stop = {"hair":(352,3438),"skin":(551,3205),"organic":(742,2782)}[scan]
    source=set(retail[start-1:stop-1])
    matches=source.intersection(saturn[16000 if scan=="organic" else 11900:])
    results[scan]=dict(original_distinct_frames=len(source),matching_distinct_frames=len(matches),
                       matched_final_menu=saturn[-1]==retail[-1],first_menu=saturn[14999 if scan=="organic" else 11099]==retail[9])
with args.disc.with_suffix(".bin").open("rb") as f:
    digest=hashlib.file_digest(f,"sha256").hexdigest()
(out/"receipt.json").write_text(json.dumps(dict(bin_sha256=digest,scans=results),indent=2)+"\n")
print(out,results)
if any(not r["matched_final_menu"] or not r["first_menu"] or
       r["matching_distinct_frames"] != r["original_distinct_frames"] for r in results.values()):
    raise SystemExit("Microscope picture or menu mismatch")
