"""Replay the first five chief's office topics from the paired office checkpoints."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageChops

root = Path(__file__).resolve().parents[1]
uncut = root.parent / "snatcher-uncut"
sonic = root.parent / "sonic-cd-saturn"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("checkpoints", type=Path, help="output directory printed by check_mika.py")
parser.add_argument("--disc", type=Path, default=root / "dist/bin-cue/snatcher-saturn.cue")
args = parser.parse_args()
disc = args.disc.resolve()
source = args.checkpoints.resolve()
with disc.with_suffix(".bin").open("rb") as stream:
    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
if json.loads((source / "receipt.json").read_text())["bin_sha256"] != checksum:
    parser.error("Use the same Saturn build that produced the checkpoints")
out = Path(tempfile.mkdtemp(prefix="chief-", dir=root / "build"))
route = [(50, "down"), (150, "down"), (250, "down"), (350, "C")]
cases = {500: "ask-menu"}
frame = 650
for index, (topic, pages) in enumerate([("junkers", 2), ("authority", 7), ("duties", 2),
                                         ("staff", 2), ("snatchers", 3)]):
    if index:
        route.append((frame, "C"))
        frame += 200
        for _ in range(index):
            route.append((frame, "down"))
            frame += 100
    route.append((frame, "C"))
    frame += 600
    for page in range(pages):
        cases[(frame-50)//100*100] = f"{topic}-{page+1}"
        route.append((frame, "C"))
        frame += 600
    if topic != "snatchers":
        cases[(frame-50)//100*100] = f"{topic}-returned"

# Let the ID-card presentation finish before sampling the newly unlocked menu.
cases[15100] = "id-card"
cases[18800] = "possessions-unlocked"
end_frame = 18800

def play(platform):
    saturn = platform == "saturn"
    directory = out / platform
    directory.mkdir()
    buttons = {"C": "800" if saturn else "100", "down": "20"}
    pad = directory / "route.pad"
    pad.write_text("".join(f"{f} {f+2} {buttons[b]}\n" for f, b in route))
    core = (sonic / ".deps/beetle-saturn/mednafen_saturn_libretro.dylib" if saturn
            else uncut / ".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib")
    bios = sonic / "assets/private" if saturn else uncut / "private/bios"
    cue = disc if saturn else uncut / "private/discs/segacd-usa/Snatcher.cue"
    env = {k: v for k, v in os.environ.items() if not k.startswith("SNATCHER_")}
    env.update(SNATCHER_PAD="generic" if saturn else "genesis3", SNATCHER_CAPTURE_EVERY="100",
               SNATCHER_CAPTURE_PREFIX=str(directory / "frame"), SNATCHER_AUDIO=str(directory / "audio.wav"))
    with (directory / "core.log").open("w") as log:
        subprocess.run([uncut / "build/harness/runner", core, bios, directory, cue, str(end_frame),
                        directory / "end.png", pad, source / platform / "chief-office.state",
                        directory / "possessions.state"],
                       check=True, env=env, stdout=log, stderr=log)

with ThreadPoolExecutor(2) as workers:
    list(workers.map(play, ["retail", "saturn"]))
for frame, label in cases.items():
    name = f"frame-{frame:06}.png"
    retail = Image.open(out / "retail" / name).convert("RGB")
    retail = retail.point(lambda v: (round(v*7/238)*255//7*31//255) << 3)
    saturn = Image.open(out / "saturn" / name).convert("RGB")
    diff = ImageChops.difference(retail, saturn.crop((37, 0, 293, 224)))
    if label == "id-card":
        # The speaking portrait belongs to the lower panel.
        diff = diff.crop((0, 0, 256, 142))
        previous = Image.open(out / "retail/frame-014400.png").convert("RGB")
        current = Image.open(out / "retail" / name).convert("RGB")
        before = previous.crop((32, 8, 224, 136))
        after = current.crop((32, 8, 224, 136))
        if not ImageChops.difference(before, after).getbbox():
            raise SystemExit(f"Retail checkpoint does not show the ID card: {out}")
    elif not label.endswith(("menu", "returned", "unlocked")):
        diff.paste((0, 0, 0), (232, 192, 244, 206))
    if diff.getbbox():
        raise SystemExit(f"{label} differs at {diff.getbbox()}: {out}")
(out / "receipt.json").write_text(json.dumps(dict(bin_sha256=checksum, frames=cases,
    checkpoints=str(source), excluded=["dialogue advance indicator", "lower panel during ID-card speech"]), indent=2)+"\n")
print(out)
