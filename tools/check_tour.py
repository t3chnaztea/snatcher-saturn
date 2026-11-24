"""Replay all four headquarters destinations after the chief's ID presentation."""
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
parser.add_argument("office", type=Path, help="checkpoint directory from check_chief.py")
parser.add_argument("--disc", type=Path, required=True)
args = parser.parse_args()
disc = args.disc.resolve()
with disc.with_suffix(".bin").open("rb") as stream:
    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
if json.loads((args.office / "receipt.json").read_text())["bin_sha256"] != checksum:
    parser.error("Use the disc that produced the office checkpoints")
out = Path(tempfile.mkdtemp(prefix="tour-", dir=root / "build"))
rooms = ["engineering", "detective", "computer", "shooting"]
verbs = ["look", "investigate", "show"]
items = ["id", "cash"]
def play(platform):
    saturn = platform == "saturn"
    directory = out / platform
    directory.mkdir()
    core = (sonic / ".deps/beetle-saturn/mednafen_saturn_libretro.dylib" if saturn
            else uncut / ".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib")
    bios = sonic / "assets/private" if saturn else uncut / "private/bios"
    cue = disc if saturn else uncut / "private/discs/segacd-usa/Snatcher.cue"
    env = {k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env["SNATCHER_PAD"] = "generic" if saturn else "genesis3"
    confirm = "800" if saturn else "100"
    def replay(label, initial, buttons, duration, samples=False):
        pad = directory / (label+".pad")
        pad.write_text("".join(f"{frame} {frame+2} {button}\n" for frame, button in buttons))
        snapshot = directory / (label+".state")
        with (directory / (label+".log")).open("w") as log:
            capture = dict(SNATCHER_CAPTURE_EVERY="4", SNATCHER_CAPTURE_PREFIX=str(directory/label)) if samples else {}
            subprocess.run([uncut / "build/harness/runner", core, bios, directory, cue, str(duration),
                            directory / (label+".png"), pad, initial, snapshot],
                           env=dict(env, **capture), stdout=log, stderr=log, check=True)
        return snapshot
    office = args.office / platform / "possessions.state"
    for v, verb in enumerate(verbs):
        for i, item in enumerate(items):
            buttons = [(30, "20"), (80, confirm)]+[(160+50*k,"20") for k in range(v)]
            buttons += [(320, confirm)]+([(450,"20")] if i else [])+[(560,confirm)]
            replay(verb+"-"+item, office, buttons, 1050)
    hall = replay("exit", office,
                  [(30,"10"), (60,"10"), (90,"10"), (120,confirm)], 600)
    for count, label in enumerate(rooms, 1):
        buttons = [(30, confirm)]+[(i*40+60, "20") for i in range(1,count+1)]+[(360, confirm)]
        scene = replay(label+"-entry", hall, buttons, 1500)
        settled = replay(label, scene, [], 256, samples=True)
        if label == "shooting":
            buttons = [(60,confirm),(300,"20"),(360,"20"),(420,"20"),(480,confirm)]
            buttons.extend((800+i*250, confirm) for i in range(14))
            # Use the settled tour checkpoint so inputs begin on Mika's greeting.
            pad = directory / "briefing.pad"
            pad.write_text("".join(f"{f} {f+2} {b}\n" for f,b in buttons))
            with (directory / "briefing.log").open("w") as log:
                subprocess.run([uncut/"build/harness/runner", core, bios, directory, cue, "4250",
                                directory/"briefing.png", pad, settled, directory/"briefing.state"], check=True,
                               env=dict(env, SNATCHER_CAPTURE_EVERY="250",
                                        SNATCHER_CAPTURE_PREFIX=str(directory/"briefing")),
                               stdout=log, stderr=log)
            replay("targets", directory/"briefing.state", [], 256, samples=True)

with ThreadPoolExecutor(2) as workers:
    list(workers.map(play, ["retail", "saturn"]))

def picture(path, platform):
    im = Image.open(path).convert("RGB")
    if platform == "retail":
        im = im.point(lambda c: (round(c*7/238)*255//7*31//255)<<3)
    else:
        im = im.crop((37,0,293,224))
    # The page indicator blinks independently on Sega CD.
    im.paste((0,0,0), (232,192,244,206))
    return im

inventory = []
for verb in verbs:
    for item in items:
        label = verb+"-"+item
        original, port = (picture(out / platform / (label+".png"), platform)
                          for platform in ("retail", "saturn"))
        if original.tobytes() != port.tobytes():
            raise SystemExit(f"Inventory response {label} differs from retail: {out}")
        inventory.append(original.tobytes())
if len(set(inventory)) != 6:
    raise SystemExit(f"Expected six distinct retail inventory responses: {out}")

def samples(platform, room):
    directory = out / platform
    pictures = []
    for path in sorted(directory.glob(room+"-[0-9]*.png")):
        pictures.append(picture(path, platform))
    if len(pictures) != 64:
        raise SystemExit(f"Missing captures for {room} on {platform}: {out}")
    return pictures

motions = {"engineering": (84,12,132,36), "shooting": (128,16,144,72)}
for label in rooms:
    original, port = (samples(platform, label) for platform in ("retail", "saturn"))
    if not {im.tobytes() for im in original}.intersection(im.tobytes() for im in port):
        raise SystemExit(f"No matching settled picture for {label}: {out}")
    if label in motions:
        bounds = motions[label]
        poses = {im.crop(bounds).tobytes() for im in port}
        if len(poses) != 4 or not poses.issubset(im.crop(bounds).tobytes() for im in original):
            raise SystemExit(f"Expected four matching animation poses for {label}: {out}")
    if label == "computer":
        # Both lights complete a full cycle during the 256-frame recording.
        for coordinate, period in [((125,9), 128), ((76,16), 224)]:
            cycle = [im.getpixel(coordinate) for im in original[:period//4]]
            played = [im.getpixel(coordinate) for im in port]
            if len(set(cycle)) < 8 or not any(
                all(color == cycle[(i+phase) % len(cycle)] for i,color in enumerate(played))
                for phase in range(len(cycle))
            ):
                raise SystemExit(f"Computer light at {coordinate} differs from retail: {out}")
for frame in range(750, 4251, 250):
    name = f"briefing-{frame:06}.png"
    original, port = (picture(out / platform / name, platform) for platform in ("retail", "saturn"))
    # The wall fan and target lamps run independently of text advancement.
    original = original.crop((0,142,256,224))
    port = port.crop((0,142,256,224))
    if original.tobytes() != port.tobytes():
        raise SystemExit(f"Shooting briefing differs at {frame}: {out}")
# Compare the upper picture across every lamp color while the last page waits.
baseline, played = (samples(platform, "targets") for platform in ("retail", "saturn"))
def target_poses(pictures):
    return {im.crop((0,0,256,142)).tobytes() for im in pictures}
poses = target_poses(baseline)
if len(poses) < 8 or poses != target_poses(played):
    raise SystemExit(f"Practice target lights or backdrop differ: {out}")
(out / "receipt.json").write_text(json.dumps(dict(bin_sha256=checksum, rooms=rooms, briefing_frames=list(range(750,4251,250)), inventory=[v+"-"+i for v in verbs for i in items],
    evidence="room art and entry dialogue, four engineering and range poses, two light cycles",
    excluded=["dialogue advance indicator"]), indent=2)+"\n")
print(out)
