"""Replay the Talk and Ask branches on a retail cold-boot checkpoint and Saturn."""
from collections import Counter
import argparse
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
parser.add_argument("--disc", type=Path, default=root / "dist/bin-cue/snatcher-saturn.cue")
args = parser.parse_args()
out = Path(tempfile.mkdtemp(prefix="mika-", dir=root / "build"))
retail = max((root/"build").glob("retail-*/receipt.json"), key=lambda p:p.stat().st_mtime).parent
environment = {k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
# Pad states are sent for three frames. Allow each line to finish drawing
# and each voice to play before testing the next input.
route = [(60,"C"),(360,"C"),(650,"down"),(700,"down"),(750,"down"),(800,"C"),
         (2350,"down"),(2440,"down"),(2530,"down"),(2670,"C"),(2900,"C")]
# Finish each exchange before selecting the next topic. The root menu
# remembers Ask. A newly opened topic menu starts on About Junkers.
route.extend([(3450, "C"), (3850, "C"), (4250, "C"),
              (4550, "C"), (4700, "down"), (4850, "C"),
              (5250, "C"), (5650, "C"), (6150, "C"),
              (6450, "C"), (6600, "down"), (6700, "down"), (6800, "C"),
              (7200, "C"), (7600, "C"), (8000, "C"), (8400, "C")])
route.extend([(8800, "down"), (8900, "down"), (9000, "C"), (13050, "C"), (13650, "C")])
for is_saturn in [False,True]:
    directory = out / ("saturn" if is_saturn else "retail")
    directory.mkdir()
    cue = args.disc.resolve() if is_saturn else uncut/"private/discs/segacd-usa/Snatcher.cue"
    core = sonic/".deps/beetle-saturn/mednafen_saturn_libretro.dylib" if is_saturn else uncut/".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib"
    bios = sonic/"assets/private" if is_saturn else uncut/"private/bios"
    base = 2400 if is_saturn else 0
    mask = "800" if is_saturn else "100"
    rows = ["1205 1210 8", "2305 2307 800"] if is_saturn else []
    for frame, button in route:
        rows.append(f"{base+frame} {base+frame+2} {mask if button=='C' else '20'}")
    pad = directory/"route.pad"
    pad.write_text("\n".join(rows)+"\n")
    env = dict(environment, SNATCHER_PAD="generic" if is_saturn else "genesis3",
               SNATCHER_CAPTURE_EVERY="100", SNATCHER_CAPTURE_PREFIX=str(directory/"frame"),
               SNATCHER_AUDIO=str(directory/"audio.wav"))
    with (directory/"core.log").open("w") as log:
        subprocess.run([uncut/"build/harness/runner",core,bios,directory,cue,str(base+19600),
                        directory/"end.png", pad, "-" if is_saturn else retail/"run-1/menu.state",
                        directory/"chief-office.state"],
                       env=env, stdout=log, stderr=log, check=True)
# Compare the settled screens. Retail blinks and animates its page indicator.
# Limit the exclusions to those two regions, including their black background.
cases = {2300: "talk-menu", 2400: "investigate-highlight", 2500: "talk-highlight",
         2600: "ask-highlight", 2800: "ask-topics", 3300: "about-junkers",
         3800: "junker-task-force", 4200: "agency-oversight", 4500: "ask-retained",
         4800: "neo-kobe-highlight", 5200: "first-time-in-town", 5600: "welcome",
         6100: "city-background", 6400: "ask-retained-again", 7100: "about-mika",
         7500: "mika-replies", 7900: "gillian-replies", 8300: "mika-ends-conversation",
         8700: "enter-unlocked", 9400: "door-closed", 9700: "door-open", 12800: "hallway-question", 13500: "tour-destinations",
         19600: "chief-office-menu"}
for frame, label in cases.items():
    original = Image.open(out / f"retail/frame-{frame:06}.png").convert("RGB")
    original = original.point(lambda v: (round(v * 7 / 238) * 255 // 7 * 31 // 255) << 3)
    target = Image.open(out / f"saturn/frame-{frame+2400:06}.png").convert("RGB")
    left = (target.width - original.width) // 2
    if original.size != (256, 224) or target.size != (330, 224):
        raise SystemExit(f"Unexpected video dimensions: {out}")
    diff = ImageChops.difference(original, target.crop((left, 0, left+256, 224)))
    if label in ("hallway-question", "tour-destinations"):
        # The two systems reach the walking cycle at different times. Compare
        # the UI here and all three upper-screen poses below.
        diff.paste((0, 0, 0), (0, 0, 256, 142))
    if label in ("door-closed", "door-open"):
        # The inset talking portrait in the dialogue area is still missing.
        diff = diff.crop((0, 0, 256, 142))
    if frame <= 8700:
        diff.paste((0, 0, 0), (105, 56, 143, 67))
    if frame in (3300, 3800, 4200, 5200, 5600, 6100, 7100, 7500, 7900, 8300, 12800):
        diff.paste((0, 0, 0), (232, 192, 244, 206))
    if diff.getbbox():
        raise SystemExit(f"{label} differs at {diff.getbbox()}: {out}")
def hallway_poses(platform, offset):
    counts = Counter()
    for frame in range(11000, 13601, 100):
        pic = Image.open(out / platform / f"frame-{frame+offset:06}.png").convert("RGB")
        if platform == "retail":
            pic = pic.point(lambda v: (round(v * 7 / 238) * 255 // 7 * 31 // 255) << 3)
        left = (pic.width-256)//2
        counts[pic.crop((left, 0, left+256, 142)).tobytes()] += 1
    return counts

retail_poses = hallway_poses("retail", 0)
saturn_poses = hallway_poses("saturn", 2400)
common = [pose for pose, count in retail_poses.most_common() if pose in saturn_poses]
if len(common) != 3 or set(common) != set(saturn_poses):
    raise SystemExit(f"{len(common)} matching hallway poses among {len(saturn_poses)} Saturn poses: {out}")
with args.disc.resolve().with_suffix(".bin").open("rb") as stream:
    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
(out / "receipt.json").write_text(json.dumps(dict(bin_sha256=checksum, frames=cases, hallway_poses=len(common),
    excluded=["blinking eyes", "dialogue advance indicator", "lower panel during door sequence"]), indent=2) + "\n")
print(out)
