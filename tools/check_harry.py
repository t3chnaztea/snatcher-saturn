"""Compare Harry's return to Engineering after a continuous headquarters tour."""
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
parser.add_argument("tour", type=Path, help="checkpoint directory from check_tour.py")
parser.add_argument("--disc", type=Path, required=True)
args = parser.parse_args()
disc = args.disc.resolve()
with disc.with_suffix(".bin").open("rb") as stream:
    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
if json.loads((args.tour / "receipt.json").read_text())["bin_sha256"] != checksum:
    parser.error("Use the disc that produced the tour checkpoints")
out = Path(tempfile.mkdtemp(prefix="harry-", dir=root / "build"))

def play(platform):
    saturn = platform == "saturn"
    directory = out / platform
    directory.mkdir()
    core = (sonic / ".deps/beetle-saturn/mednafen_saturn_libretro.dylib" if saturn
            else uncut / ".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib")
    bios = sonic / "assets/private" if saturn else uncut / "private/bios"
    cue = disc if saturn else uncut / "private/discs/segacd-usa/Snatcher.cue"
    confirm = "800" if saturn else "100"
    buttons = []
    frame = 100

    def press(button=confirm, gap=250):
        nonlocal frame
        buttons.append(f"{frame} {frame+2} {button}\n")
        frame += gap

    for visit, (room, pages) in enumerate([(1,2), (2,6), (3,2), (4,1), (1,2)]):
        press()
        for _ in range(room):
            press("20", 50)
        press(gap=450)
        for _ in range(pages):
            press()
        if visit < 4:
            press(gap=450)

    env = {k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env["SNATCHER_PAD"] = "generic" if saturn else "genesis3"
    state = args.tour.resolve() / platform / "exit.state"
    conversation = [(40, "20"), (90, "20"), (150, confirm), (220, "20"),
                    (270, "20"), (330, confirm)]
    conversation.extend((900+400*i, confirm) for i in range(6))
    dialogue_pad = [f"{n} {n+2} {button}\n" for n,button in conversation]
    for label, duration, rows in [("visit", frame+1800, buttons), ("menu", 128, []),
                                  ("snatchers", 3200, dialogue_pad)]:
        pad = directory / (label+".pad")
        pad.write_text("".join(rows))
        saved = directory / (label+".state")
        if label == "menu":
            env.update(SNATCHER_CAPTURE_EVERY="4", SNATCHER_CAPTURE_PREFIX=str(directory/label))
        if label == "snatchers":
            env.update(SNATCHER_CAPTURE_EVERY="200", SNATCHER_CAPTURE_PREFIX=str(directory/label))
        with (directory/(label+".log")).open("w") as log:
            subprocess.run([uncut/"build/harness/runner", core, bios, directory, cue,
                            str(duration), directory/(label+".png"), pad, state, saved],
                           env=env, stdout=log, stderr=log, check=True)
        state = saved

    pictures = []
    for path in sorted(directory.glob("menu-*.png")):
        im = Image.open(path).convert("RGB")
        if saturn:
            im = im.crop((37,0,293,224))
        else:
            im = im.point(lambda c: (round(c*7/238)*255//7*31//255)<<3)
        pictures.append(im)
    if len(pictures) != 32:
        raise SystemExit(f"Missing {platform} captures in {out}")
    return pictures

with ThreadPoolExecutor(2) as workers:
    original, port = workers.map(play, ("retail", "saturn"))
if not {im.tobytes() for im in original}.intersection(im.tobytes() for im in port):
    raise SystemExit(f"Harry's Engineering menu differs from retail: {out}")
def poses(pictures):
    return {im.crop((84,12,132,36)).tobytes() for im in pictures}
if len(poses(port)) != 4 or poses(original) != poses(port):
    raise SystemExit(f"Engineering fan differs from retail: {out}")
# Each question page and the recovered menu are stable between input presses.
pages = set()
for frame in range(800, 3201, 400):
    path = f"snatchers-{frame:06}.png"
    retail = Image.open(out/"retail"/path).convert("RGB").crop((0,142,256,224))
    retail = retail.point(lambda c: (round(c*7/238)*255//7*31//255)<<3)
    native = Image.open(out/"saturn"/path).convert("RGB").crop((37,142,293,224))
    for image in (retail, native):
        image.paste((0,0,0), (232,50,244,64))
    if retail.tobytes() != native.tobytes():
        raise SystemExit(f"Harry's Snatchers response differs at frame {frame}: {out}")
    pages.add(retail.tobytes())
if len(pages) != 7:
    raise SystemExit(f"Expected six dialogue pages and the investigation menu: {out}")
(out/"receipt.json").write_text(json.dumps(dict(bin_sha256=checksum, fan_poses=4, snatchers_pages=6,
    evidence="Harry's seated portrait and investigation menu after visiting four rooms"),
    indent=2)+"\n")
print(out)
