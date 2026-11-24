"""Replay Harry's dispatch from the equipment questions into the turbocycle."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from PIL import Image

root = Path(__file__).resolve().parents[1]
uncut = root.parent/"snatcher-uncut"
sonic = root.parent/"sonic-cd-saturn"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("navigator", type=Path, help="output from check_navigator.py")
parser.add_argument("--disc", required=True, type=Path)
args = parser.parse_args()
disc = args.disc.resolve()
with disc.with_suffix(".bin").open("rb") as stream:
    checksum = hashlib.file_digest(stream,"sha256").hexdigest()
if json.loads((args.navigator/"receipt.json").read_text())["bin_sha256"] != checksum:
    parser.error("Use the disc that produced the Navigator checkpoints")
out = Path(tempfile.mkdtemp(prefix="dispatch-",dir=root/"build"))

def play(platform):
    saturn = platform == "saturn"
    directory = out/platform
    directory.mkdir()
    core = (sonic/".deps/beetle-saturn/mednafen_saturn_libretro.dylib" if saturn
            else uncut/".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib")
    bios = sonic/"assets/private" if saturn else uncut/"private/bios"
    cue = disc if saturn else uncut/"private/discs/segacd-usa/Snatcher.cue"
    confirm = "800" if saturn else "100"
    env = {k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env["SNATCHER_PAD"] = "generic" if saturn else "genesis3"

    def replay(label,state,buttons,duration,interval):
        pad = directory/(label+".pad")
        pad.write_text("".join(f"{n} {n+2} {b}\n" for n,b in buttons))
        snapshot = directory/(label+".state")
        with (directory/(label+".log")).open("w") as log:
            subprocess.run([uncut/"build/harness/runner",core,bios,directory,cue,str(duration),
                            directory/(label+".png"),pad,state,snapshot], check=True,
                           stdout=log,stderr=log,env=dict(env,SNATCHER_CAPTURE_EVERY=str(interval),
                           SNATCHER_CAPTURE_PREFIX=str(directory/label),
                           SNATCHER_AUDIO=str(directory/(label+".wav"))))
        return snapshot

    # About Blaster, About Snatchers, and the Metal Gear operating instructions.
    buttons = [(60,"20"),(150,confirm),(3860,confirm),(3960,"20"),(4040,"20"),(4120,confirm)]
    buttons.extend((4450+320*i,confirm) for i in range(6))
    buttons.extend([(6450,confirm),(6650,confirm)])
    buttons.extend((7150+360*i,confirm) for i in range(11))
    briefing = replay("briefing",args.navigator.resolve()/platform/"menu.state",buttons,11600,100)
    lot = replay("dispatch",briefing,[(60,confirm)],4400,8)
    # Reach two optional investigations from the same parking lot checkpoint.
    for verb,downs in (("look",1),("investigate",2)):
        moves = [(60+60*i,"20") for i in range(downs)]
        moves += [(260,confirm),(420,confirm)]
        replay(verb+"-body",lot,moves,900,100)
    save_menu = [(80,"20"),(140,"20"),(200,"20"),(300,confirm),(430,"20"),(520,confirm),
                 (900,confirm),(1300,confirm)]
    replay("save-menu",lot,save_menu,1800,100)
    cockpit = replay("boarding",lot,[(60,confirm)],1200,8)
    replay("destinations",cockpit,[(100,confirm)],420,20)

def picture(platform,label):
    image = Image.open(out/platform/(label+".png")).convert("RGB")
    if platform == "saturn":
        return image.crop((37,0,293,224))
    return image.point(lambda c: (round(c*7/238)*255//7*31//255)<<3)

with ThreadPoolExecutor(2) as workers:
    list(workers.map(play,("retail","saturn")))

for label in ("briefing","dispatch","boarding","destinations","look-body","investigate-body","save-menu"):
    a,b = (picture(p,label) for p in ("retail","saturn"))
    if label == "briefing":
        a,b = (im.crop((0,142,256,224)) for im in (a,b))
    if label in ("briefing","boarding","look-body","investigate-body"):
        y = 0 if label=="briefing" else 142
        for im in (a,b): im.paste((0,0,0),(232,50+y,245,65+y))
    if a.tobytes() != b.tobytes():
        raise SystemExit(f"{label} differs from Sega CD: {out}")
# Harry's save instructions span seven rows and require a second page.
for frame in (8500,8800):
    pages = [picture(p,f"briefing-{frame:06}").crop((0,142,256,224)) for p in ("retail","saturn")]
    for page in pages: page.paste((0,0,0),(232,50,245,65))
    if pages[0].tobytes() != pages[1].tobytes():
        raise SystemExit(f"Automatic dialogue break differs at {frame}: {out}")

def poses(platform, label, start, end, box):
    return {hashlib.sha256(picture(platform,f"{label}-{f:06}").crop(box).tobytes()).digest()
            for f in range(start,end+1,8)}

sampled = {}
for label,scene,start,end,box in [
        ("videophone","dispatch",680,904,(32,8,224,136)),
        ("Harry and Mika","dispatch",1104,1400,(32,36,224,136)),
        ("opening canopy","boarding",88,208,(32,8,224,136))]:
    original = poses("retail",scene,start,end,box)
    native = poses("saturn",scene,64,2200 if scene=="dispatch" else 600,box)
    sampled[label] = len(original & native)
    if not sampled[label]:
        raise SystemExit(f"No retail pose matched {label}: {out}")
(out/"receipt.json").write_text(json.dumps(dict(bin_sha256=checksum,
    poses=sampled, checkpoints=["final briefing page","parking lot commands","cockpit prompt","destination choices","Look at body","Investigate body","four save slots"]),indent=2)+"\n")
print(out)
