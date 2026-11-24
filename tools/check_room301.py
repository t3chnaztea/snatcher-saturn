"""Compare Ivan's duel against a no-input Sega CD run that takes six hits."""
import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("retail", type=Path, help="Sega CD duel captures from the frame before combat setup")
parser.add_argument("saturn", type=Path, help="Beetle Saturn captures, including the loss")
args = parser.parse_args()

def region_hash(image, top, bottom, offset=0):
    region = image.crop((32 + offset, top, 224 + offset, bottom))
    return hashlib.sha256(region.tobytes()).hexdigest()

def retail_frame(frame):
    with Image.open(args.retail / f"frame-{frame:06}.png") as image:
        return image.convert("RGB").point(lambda c: (min(7, (c+17)//34)*255//7*31//255)<<3)

# Retail begins fading the screen immediately after the sixth hit.
health = [region_hash(retail_frame(n), 136, 144) for n in (112,160,240,328,408,488)]
assert len(set(health)) == 6
poses = {region_hash(retail_frame(n), 8, 136): n for n in (128,160)}
levels = []
found = {}
for capture in sorted(args.saturn.glob("frame-*.png")):
    frame = int(capture.stem.rsplit("-",1)[1])
    with Image.open(capture) as source:
        image = source.convert("RGB")
    if image.size != (330,224):
        raise ValueError(f"Expected a 330 by 224 Saturn capture at {capture}")
    bar = region_hash(image, 136, 144, 37)
    if len(levels) < len(health) and bar == health[len(levels)]:
        levels.append(frame)
    if levels:
        pose = region_hash(image, 8, 136, 37)
        if pose in poses:
            found.setdefault(poses[pose], frame)
print(json.dumps(dict(life_bar_frames=levels, target_pose_frames=found),indent=2))
if len(levels) != 6 or len(found) != 2:
    raise SystemExit("Missing a retail LIFE display or target pose")
