"""Replay the factory exit on both systems and compare the street, lobby, reception, and office."""
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
uncut = root.parent/"snatcher-uncut"
sonic = root.parent/"sonic-cd-saturn"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--disc",type=Path,required=True)
parser.add_argument("--backup",type=Path,required=True,help="slot two at Gibson from check_factory_save.py")
parser.add_argument("--briefing",action="store_true",help="also check the V0.059 reception and office portraits")
parser.add_argument("--investigation", action="store_true",
                    help="continue from the briefing through Gibson's desk and the engineering investigation")
args=parser.parse_args()
if args.investigation:
    args.briefing=True
out=Path(tempfile.mkdtemp(prefix="hq-return-",dir=root/"build"))
source=uncut/"build/evidence/m5/playthrough-lane/natural-run"
state=source/"1073/native.state"
if hashlib.sha1(state.read_bytes()).hexdigest()!="4dc4a56fb7e991648d332bd9f136cd404e8d807e":
    raise ValueError("Expected the original retail factory victory checkpoint")
flags=shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","libpng"],text=True))
subprocess.run(["cc","-O2","-I"+str(uncut/"tools/harness"),"-I"+str(sonic/".deps/beetle-saturn/libretro-common/include"),
                root/"tools/factory_core.c",*flags,"-o",out/"runner"],check=True)

def events(path):
    for line in path.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            a,b,key=line.split()
            yield int(a),int(b),key

def replay(system):
    saturn=system=="saturn"
    run=out/system
    run.mkdir()
    route=root/"tools/routes"
    if saturn:
        steps=[s for s in events(route/"factory-escape-from-save.pad") if s[0]<25500]
        steps.extend(events(route/"factory-hq-return.pad"))
        if args.investigation:
            steps.extend(events(route/"hq-investigation.pad"))
    else:
        steps=list(events(source/"1074/input.pad"))
        steps.extend((a+6000,b+6000,key) for a,b,key in events(source/"1075/input.pad"))
    pad=run/"input.pad"
    pad.write_text("".join(f"{a} {b} {key}\n" for a,b,key in steps))
    env={k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env.update(SNATCHER_PAD="generic" if saturn else "genesis3",SNATCHER_FRAME_HASHES=str(run/"frames.txt"),
               SNATCHER_AUDIO=str(run/"mix.wav"))
    if saturn:
        env.update(SNATCHER_BACKUP_INPUT=str(args.backup.resolve()),SNATCHER_BACKUP_OUTPUT=str(run/"internal.bin"))
    core=sonic/".deps/beetle-saturn/mednafen_saturn_libretro.dylib" if saturn else uncut/".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib"
    frames = 7941
    if saturn:
        frames = 41000 if args.briefing else 38000
        if args.investigation:
            frames = steps[-1][1]+300
    with (run/"core.log").open("w") as log:
        subprocess.run([out/"runner",core,sonic/"assets/private" if saturn else uncut/"private/bios",run,
                        args.disc.resolve() if saturn else uncut/"private/discs/segacd-usa/Snatcher.cue",
                        str(frames),run/"end.png",pad,"-" if saturn else state],
                       env=env,check=True,stdout=log,stderr=log)
    return [tuple(line.split()[1:]) for line in (run/"frames.txt").read_text().splitlines()]

with ThreadPoolExecutor(2) as pool:
    retail,saturn=pool.map(replay,("retail","saturn"))
comparison={}
cursor=30000
shots=[("street",3657,3950),("lobby",4485,4699)]
if args.briefing:
    shots.extend([("reception",4704,5838),("office",5846,7911)])
for label,start,end in shots:
    reference=retail[start-1:end-1]
    ordered=[h for i,h in enumerate(reference) if i==0 or h!=reference[i-1]]
    for h in ordered:
        try: cursor=saturn.index(h,cursor)+1
        except ValueError: raise ValueError(f"Missing {label} viewport {h} in {out}") from None
    comparison[label]=dict(distinct=len(set(reference)),ordered=len(ordered))
if args.investigation:
    from PIL import Image
    route = json.loads((root/"tools/routes/hq-investigation.json").read_text())
    cursor = 40000
    for checkpoint, label, regions in route:
        frame = Image.open(source/str(checkpoint)/"screen.png").convert("RGB")
        frame = frame.point(lambda c: (min(7,(c+17)//34)*255//7*31//255)<<3)
        hashes = []
        for region in [(32,8,224,136),(16,142,232,224)]:
            value = 14695981039346656037
            for color in frame.crop(region).tobytes():
                value = ((value ^ color)*1099511628211) & 0xffffffffffffffff
            hashes.append(f"{value:016x}")
        indices = {"scene": (0,), "dialogue": (1,), "scene and dialogue": (0,1)}[regions]
        for i in range(cursor,len(saturn)):
            if all(saturn[i][part]==hashes[part] for part in indices):
                cursor=i+1
                break
        else:
            raise ValueError(f"Missing {label} (Sega CD checkpoint {checkpoint}): {out}")
        comparison[label] = {"source_checkpoint":checkpoint, "saturn_frame":cursor, "regions":regions}

with args.disc.with_suffix(".bin").open("rb") as stream:
    digest=hashlib.file_digest(stream,"sha256").hexdigest()
(out/"receipt.json").write_text(json.dumps(dict(bin_sha256=digest,scenes=comparison),indent=2)+"\n")
print(out,comparison)
