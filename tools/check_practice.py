"""Play the Saturn introductory exercise twice from the verified tour checkpoint."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import struct
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

root = Path(__file__).resolve().parents[1]
sonic = root.parent / "sonic-cd-saturn"
uncut = root.parent / "snatcher-uncut"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("tour", type=Path)
parser.add_argument("--disc", type=Path, required=True)
parser.add_argument("--reference", type=Path, help="compare with check_practice_reference.py captures (Pillow required)")
args = parser.parse_args()
disc = args.disc.resolve()
with disc.with_suffix(".bin").open("rb") as f:
    checksum = hashlib.file_digest(f,"sha256").hexdigest()
if checksum != json.loads((args.tour/"receipt.json").read_text())["bin_sha256"]:
    parser.error("Use the package that produced this checkpoint")
receipt = json.loads((disc.parent/"build-receipt.json").read_text())
with (root/"dist/bin-cue/snatcher-saturn.bin").open("rb") as f:
    if hashlib.file_digest(f,"sha256").hexdigest() != receipt["saturn_track1_sha256"]:
        parser.error("Rebuild the matching local ELF with bash tools/build.sh")
symbols = (root/"build/saturn/snatcher-saturn.sym").read_text().splitlines()
game, = [int(line.split()[0],16) for line in symbols if re.search(r" [bB] _game(?:\.lto_priv\.\d+)?$",line)]
out = Path(tempfile.mkdtemp(prefix="practice-saturn-",dir=root/"build"))
with tempfile.TemporaryDirectory() as temp:
    offset_tool = Path(temp)/"offset"
    subprocess.run(["cc","-x","c","-I",root/"src","-o",offset_tool,"-"],input=
                   '#include "script.h"\n#include <stddef.h>\n#include <stdio.h>\n'
                   'int main(void){printf("%zu",offsetof(struct investigation,practice));}\n',
                   text=True,check=True)
    offset = int(subprocess.check_output([offset_tool]))
core = sonic/".deps/beetle-saturn/mednafen_saturn_libretro.dylib"
def play(route):
    run = out/route
    run.mkdir()
    buttons = [(50,0x800)]
    if route == "draw-and-fire":
        buttons.append((380,1))
        buttons.extend((500+i*22,0x800|(0,0x40,0x80,0x10,0x20)[i%5]) for i in range(85))
    elif route == "single-civilian":
        buttons.append((925,1))
        buttons.extend([(992,0x80),(998,0x880)])
    pad = run/"input.pad"
    durations = {925:5, 992:18, 998:4} if route == "single-civilian" else {}
    pad.write_text("".join(f"{n} {n+durations.get(n,2)} {mask:x}\n" for n,mask in buttons))
    state = run/"score.state"
    env = {k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env.update(SNATCHER_PAD="generic",SNATCHER_CAPTURE_EVERY="50",SNATCHER_CAPTURE_PREFIX=str(run/"frame"),
               SNATCHER_AUDIO=str(run/"audio.wav"))
    with (run/"core.log").open("w") as log:
        subprocess.run([uncut/"build/harness/runner",core,sonic/"assets/private",run,disc,"4200",
                        run/"feedback.png",pad,args.tour/"saturn/briefing.state",state],
                       check=True,env=env,stdout=log,stderr=log)
    raw = state.read_bytes()
    marker = b"\x08WorkRAMH"+struct.pack("<I",0x100000)
    if raw.count(marker) != 1:
        raise SystemExit("Unsupported Beetle state")
    pos = raw.index(marker)+len(marker)+game-0x06000000+offset
    values = struct.unpack_from("<7H",raw,pos)
    result = dict(zip(("shots","enemies","civilians","misses","damage","all_civilians","drawn"),values))
    (run/"score.json").write_text(json.dumps(result,indent=2)+"\n")
    if (route == "draw-and-fire" and not (result["drawn"] and result["enemies"] and result["misses"] and
                      result["shots"] == result["enemies"]+result["civilians"]+result["misses"])) or (route == "holstered" and any(values)):
        raise SystemExit(f"Unexpected practice score {result}: {run}")
    if route == "single-civilian" and values != (1,0,1,0,0,0,1):
        raise SystemExit(f"Isolated shot missed the civilian: {result} in {run}")
    return result

with ThreadPoolExecutor(3) as pool:
    results = list(pool.map(play,("holstered","draw-and-fire","single-civilian")))
if args.reference:
    from PIL import Image
    def crop(path, rect, saturn):
        im = Image.open(path).convert("RGB")
        if saturn:
            im = im.crop((37,0,293,224))
        else:
            im = im.point(lambda c:(round(c*7/238)*255//7*31//255)<<3)
        return im.crop(rect).tobytes()
    # The holstered route has the same result on both consoles. The second
    # route's shot counts depend on target timing and placement.
    retail = args.reference/"holstered"
    port = out/"holstered"
    rect = (16,142,232,215)
    if crop(retail/"feedback.png", rect, False) != crop(port/"feedback.png",rect,True):
        raise SystemExit(f"Holstered feedback differs from retail: {out}")
    rect = (16,112,40,136)
    phases = [crop(retail/f"frame-{n:06}.png", rect, False) for n in (250,500,2500)]
    shown = {crop(p, rect, True) for p in port.glob("frame-*.png")}
    if len(set(phases)) != 3 or not set(phases).issubset(shown):
        raise SystemExit(f"Missing READY, GO or OVER sign: {out}")
(out/"receipt.json").write_text(json.dumps(dict(bin_sha256=checksum,holstered=results[0],
    draw_and_fire=results[1], single_civilian=results[2], core_sha256=hashlib.sha256(core.read_bytes()).hexdigest()),indent=2)+"\n")
print(out)
