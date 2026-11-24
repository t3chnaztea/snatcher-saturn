"""Save Gibson's investigation to slot two and recover both clues after a reset."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
sonic = root.parent / "sonic-cd-saturn"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("replay", type=Path, help="completed check_factory.py --evidence directory")
parser.add_argument("--disc", type=Path, required=True)
args = parser.parse_args()
disc = args.disc.resolve()
replay = args.replay.resolve()
receipt = json.loads((replay / "receipt.json").read_text())
with disc.with_suffix(".bin").open("rb") as stream:
    digest = hashlib.file_digest(stream, "sha256").hexdigest()
if receipt["bin_sha256"] != digest or not receipt["dialogue"].get("discoveries"):
    parser.error("Expected a successful evidence replay of this BIN")
out = Path(tempfile.mkdtemp(prefix="factory-save-", dir=root / "build"))

def play(label, pad, frames, battery, reset=0):
    folder = out / label
    folder.mkdir()
    (folder/"route.pad").write_text(pad)
    env = {k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env.update(SNATCHER_PAD="generic", SNATCHER_FRAME_HASHES=str(folder/"frames.txt"),
               SNATCHER_BACKUP_INPUT=str(battery), SNATCHER_BACKUP_OUTPUT=str(folder/"internal.bin"))
    if reset:
        env["SNATCHER_RESET_FRAME"] = str(reset)
    with (folder/"core.log").open("w") as log:
        subprocess.run([replay/"runner", sonic/".deps/beetle-saturn/mednafen_saturn_libretro.dylib",
                        sonic/"assets/private",folder,disc,str(frames),folder/"end.png",folder/"route.pad"],
                       env=env,check=True,stdout=log,stderr=log)
    return folder

def buttons(steps, offset=0):
    return "".join(f"{offset+n} {offset+n+2} {key}\n" for n,key in steps)

def final_screen(folder):
    return (folder/"frames.txt").read_text().splitlines()[-1].split()[1:]

# Close Look > Corpse, open Use Metal Gear > Save, then choose slot two.
save = [(38400,"800"),(38700,"800"),(39000,"800"),(39300,"10"),(39600,"10"),(39900,"800"),
        (40200,"20"),(40500,"800"),(41000,"800"),(41500,"800"),(42000,"20"),(42300,"800"),(42900,"800")]
# Continue > slot two, then open Look to expose the saved evidence flags.
load = [(1800,"20"),(2000,"800"),(2250,"20"),(2800,"800"),(3400,"20"),(3650,"800")]
prior = replay/"saturn/internal.bin"
if b"SNATCHERS2" in prior.read_bytes():
    parser.error("Use a parking-lot replay with slot two empty")
# A longer replay can continue past both discoveries. Stop its controller
# input at the evidence menu before selecting the save command.
rows = (replay/"saturn/route.pad").read_text().splitlines()
route = "".join(row+"\n" for row in rows if int(row.split()[0]) <= 38200) + buttons(save)
reset_frame = 43700
reset = play("reset",route+buttons(load,reset_frame),reset_frame+4300,prior,reset_frame)
battery = reset/"internal.bin"
if b"SNATCHERS2A" not in battery.read_bytes():
    raise SystemExit(f"Slot two was not written: {out}")
cold = play("cold",buttons(load),4300,battery)
with (replay/"retail/frames.txt").open() as frames:
    expected = next(row.split()[1:] for row in frames if row.startswith("31500 "))
if any(final_screen(folder) != expected for folder in [reset,cold]):
    raise SystemExit(f"Gibson and both evidence choices must match Sega CD after each load: {out}")
if battery.read_bytes() != (cold/"internal.bin").read_bytes():
    raise SystemExit(f"Cold load changed the save: {out}")
(out/"receipt.json").write_text(json.dumps(dict(bin_sha256=digest,slot=2,reset_frame=reset_frame,
    emulator_state_loads=0,backup_sha256=hashlib.sha256(battery.read_bytes()).hexdigest(),
    retail_picture=expected[0],retail_menu=expected[1],recovered=["key","scrap of paper"]),indent=2)+"\n")
print(out)
