"""Boot the packaged Saturn disc and replay reception input against original Sega CD captures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from PIL import Image, ImageChops

root = Path(__file__).resolve().parents[1]
sonic = root.parent / "sonic-cd-saturn"
uncut = root.parent / "snatcher-uncut"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--disc", type=Path, default=root / "dist/bin-cue/snatcher-saturn.cue")
disc = parser.parse_args().disc.resolve()
core = sonic / ".deps/beetle-saturn/mednafen_saturn_libretro.dylib"
run = Path(tempfile.mkdtemp(prefix="beetle-", dir=root / "build"))
env = {k: v for k, v in os.environ.items() if not k.startswith("SNATCHER_")}
retail_runs = sorted((root / "build").glob("retail-*/receipt.json"), key=lambda p: p.stat().st_mtime, reverse=True)
retail = next((p.parent / "run-1" for p in retail_runs if (p.parent / "run-1/look.png").exists() and (p.parent / "run-1/frame-013800.png").exists()), None)
if retail is None:
    raise SystemExit("Record the original first with python3 tools/retail_reference.py")
pad = run / "reception.pad"
pad.write_text("1205 1210 8\n2305 2310 800\n2405 2410 800\n2505 2510 800\n2605 2610 20\n2650 2655 800\n")
with (run / "core.log").open("w") as log:
    result = subprocess.run([uncut / "build/harness/runner", core, sonic / "assets/private",
                             run, disc, "2700", run / "reception.png", pad], check=True,
                            env=dict(env, SNATCHER_PAD="generic", SNATCHER_CAPTURE_EVERY="100", SNATCHER_AUDIO=str(run / "saturn.wav"),
                                     SNATCHER_CAPTURE_PREFIX=str(run / "frame")),
                            stdout=subprocess.PIPE, stderr=log)
reference = Image.open(uncut / "private/work/gfx/segacd/DATA_H08/seq_001.png").convert("RGB")
palette = {(0, 0, 0): (0, 0, 0), (238, 238, 238): (248, 248, 248),
           (238, 238, 0): (248, 248, 0), (0, 238, 238): (0, 248, 248),
           (32, 68, 238): (32, 64, 248)}
cases = [(2300, "frame-015000", 171), (2400, "menu", 197),
         (2500, "enter", 171), (2700, "look", 197)]
for capture, original, label in [(1100, 6000, "New Game"), (1400, 13800, "Act 1")]:
    actual_title = Image.open(run / f"frame-{capture:06}.png").convert("RGB")
    retail_title = Image.open(retail / f"frame-{original:06}.png").convert("RGB")
    expected_title = Image.new("RGB", actual_title.size)
    expected_title.paste(retail_title.point(lambda v: (round(v*7/238)*255//7*31//255)<<3),
                         ((actual_title.width-retail_title.width)//2, 0))
    if ImageChops.difference(expected_title, actual_title).getbbox():
        raise SystemExit(f"{label} title mismatch: {run}")
for frame, name, bottom in cases:
    actual = Image.open(run / f"frame-{frame:06d}.png").convert("RGB")
    expected = Image.new("RGB", actual.size)
    left = (actual.width - reference.width) // 2
    expected.paste(reference.point(lambda v: (v * 31 // 255) << 3), (left, 0))
    panel = Image.open(retail / f"{name}.png").convert("RGB").crop((16, 143, 240, bottom))
    panel.putdata([palette[pixel] for pixel in panel.get_flattened_data()])
    expected.paste(panel, (left + 16, 143))
    if actual.height != 224 or ImageChops.difference(actual, expected).getbbox():
        raise SystemExit(f"Reception {name} mismatch: {run}")
report = json.loads(result.stdout)
with disc.with_suffix(".bin").open("rb") as stream:
    image_hash = hashlib.file_digest(stream, "sha256").hexdigest()
report.update(bin_sha256=image_hash,
              cue_sha256=hashlib.sha256(disc.read_bytes()).hexdigest(),
              core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(),
              cases=["new-game", "act1-title"]+[name for _, name, _ in cases], pixels_compared=(2+len(cases)) * actual.width * actual.height)
(run / "receipt.json").write_text(json.dumps(report, indent=2) + "\n")
print(run, report)
