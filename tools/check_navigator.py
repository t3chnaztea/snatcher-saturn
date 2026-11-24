"""Replay Harry's Metal Gear introduction and inspect the newly available question."""
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
uncut = root.parent / "snatcher-uncut"
sonic = root.parent / "sonic-cd-saturn"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("harry", type=Path, help="checkpoint directory from check_harry.py")
parser.add_argument("--disc", type=Path, required=True)
parser.add_argument("--blaster", action="store_true", help="continue from the new menu through the Blaster demonstration")
args = parser.parse_args()
disc = args.disc.resolve()
with disc.with_suffix(".bin").open("rb") as stream:
    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
if json.loads((args.harry / "receipt.json").read_text())["bin_sha256"] != checksum:
    parser.error("Use the disc that produced the Engineering checkpoints")
out = Path(tempfile.mkdtemp(prefix="navigator-", dir=root / "build"))

def play(platform):
    saturn = platform == "saturn"
    directory = out / platform
    directory.mkdir()
    core = (sonic / ".deps/beetle-saturn/mednafen_saturn_libretro.dylib" if saturn
            else uncut / ".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib")
    bios = sonic / "assets/private" if saturn else uncut / "private/bios"
    cue = disc if saturn else uncut / "private/discs/segacd-usa/Snatcher.cue"
    confirm = "800" if saturn else "100"
    buttons = [(60,"20"), (110,"20"), (180,confirm), (350,confirm), (4400,confirm)]
    pad = directory / "navigator.pad"
    pad.write_text("".join(f"{n} {n+2} {button}\n" for n,button in buttons))
    env = {k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env.update(SNATCHER_PAD="generic" if saturn else "genesis3",
               SNATCHER_CAPTURE_EVERY="12", SNATCHER_CAPTURE_PREFIX=str(directory/"scene"),
               SNATCHER_AUDIO=str(directory/"navigator.wav"))
    with (directory/"core.log").open("w") as log:
        subprocess.run([uncut/"build/harness/runner",core,bios,directory,cue,"4600",
                        directory/"menu.png",pad,args.harry.resolve()/platform/"menu.state",
                        directory/"menu.state"], env=env, stdout=log, stderr=log, check=True)
    if args.blaster:
        # The input at 4400 left the Ask submenu on About Metal Gear.
        buttons = [(60,"20"), (150,confirm), (3800,confirm), (3900,"20"), (4000,confirm)]
        pad = directory/"blaster.pad"
        pad.write_text("".join(f"{n} {n+2} {button}\n" for n,button in buttons))
        env.update(SNATCHER_CAPTURE_EVERY="4", SNATCHER_CAPTURE_PREFIX=str(directory/"blaster"),
                   SNATCHER_AUDIO=str(directory/"blaster.wav"))
        with (directory/"blaster.log").open("w") as log:
            subprocess.run([uncut/"build/harness/runner",core,bios,directory,cue,"4500",
                            directory/"repeat.png",pad,directory/"menu.state",
                            directory/"blaster.state"],env=env,stdout=log,stderr=log,check=True)

def picture(platform, name):
    image = Image.open(out/platform/name).convert("RGB")
    if platform == "saturn":
        return image.crop((37,0,293,224))
    return image.point(lambda c: (round(c*7/238)*255//7*31//255)<<3)

with ThreadPoolExecutor(2) as workers:
    list(workers.map(play, ("retail","saturn")))
retail, saturn = (picture(platform,"menu.png").crop((0,142,256,224))
                  for platform in ("retail","saturn"))
if retail.tobytes() != saturn.tobytes():
    raise SystemExit(f"Metal Gear question menu differs from retail: {out}")
# The emulators reach each animation at different times. Match the retail
# poses in order while allowing the sampled frames to land on different ticks.
def signatures(platform, start, end, crop):
    result = []
    for tick in range(start,end+1,12):
        pixels = picture(platform,f"scene-{tick:06}.png").crop(crop).tobytes()
        result.append(hashlib.sha256(pixels).digest())
    return result

regions = [
    ("empty_office", 1116, 1140, (32,40,128,136), 1),
    ("walking", 1200, 2004, (32,40,128,136), 30),
    ("closeup", 2160, 3024, (0,0,256,142), 2),
]
matches = {}
for label,start,end,box,minimum in regions:
    expected = signatures("retail",start,end,box)
    actual = signatures("saturn",504,4356,box)
    cursor = 0
    seen = set()
    for pose in expected:
        if pose in seen:
            continue
        try:
            index = actual.index(pose,cursor)
        except ValueError:
            continue
        seen.add(pose)
        cursor = index+1
    matches[label] = len(seen)
    if len(seen) < minimum:
        raise SystemExit(f"{label} matched {len(seen)} of {len(set(expected))} sampled poses: {out}")
if args.blaster:
    def stills(platform, lo, hi, box):
        return {hashlib.sha256(picture(platform,f"blaster-{f:06}.png").crop(box).tobytes()).digest()
                for f in range(lo,hi+1,4)}
    for label,lo,hi,box,min_poses in [
            ("blaster_item",700,900,(128,24,192,72),1),
            ("blaster_demo",1352,1800,(32,8,224,136),3)]:
        original = stills("retail",lo,hi,box)
        native = stills("saturn",500,2400,box)
        matches[label] = len(original & native)
        if matches[label] < min_poses:
            raise SystemExit(f"{label} matched {matches[label]} sampled poses: {out}")
    pages = [picture(platform,"repeat.png").crop((0,142,256,224)) for platform in ("retail","saturn")]
    for page in pages:
        page.paste((0,0,0), (232,50,244,64))
    if pages[0].tobytes() != pages[1].tobytes():
        raise SystemExit(f"Repeat Blaster response differs: {out}")
(out/"receipt.json").write_text(json.dumps(dict(bin_sha256=checksum, poses=matches,
    menu="Ask submenu after the Navigator presentation"),indent=2)+"\n")
print(out)
