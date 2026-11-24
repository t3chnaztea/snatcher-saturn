"""Record the two retail practice outcomes from the end of Mika's briefing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
uncut = root.parent / "snatcher-uncut"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("checkpoint", type=Path, help="retail/briefing.state from the tour replay")
args = parser.parse_args()
state = args.checkpoint.resolve()
subcode = (uncut / "private/extracted/segacd-usa/SUBCODE.BIN").read_bytes()
core = uncut / ".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib"
cue = uncut / "private/discs/segacd-usa/Snatcher.cue"
out = Path(tempfile.mkdtemp(prefix="practice-retail-", dir=root / "build"))
def score(checkpoint):
    raw = checkpoint.read_bytes()
    if not raw.startswith(b"GENPLUS-GX"):
        raise ValueError("Expected a Genesis Plus GX state")
    marker = bytearray(subcode[:256])
    marker[::2], marker[1::2] = marker[1::2], marker[::2]
    index = raw.find(marker)
    if index < 0 or raw.find(marker, index+1) >= 0:
        raise ValueError("Cannot locate the resident retail module")
    base = index - 0xd400
    fields = {"fired":0x7908, "enemies":0x790a, "civilians":0x790c,
              "misses":0x790e, "damage":0x7910, "drew_weapon":0x7918}
    return {key:struct.unpack_from("<H",raw,base+address)[0] for key,address in fields.items()}

results = {}
for draw in (False, True):
    name = "draw-and-fire" if draw else "holstered"
    run = out / name
    run.mkdir()
    # After C dismisses the briefing, A draws the gun. C fires in the current field.
    rows = [(50,0x100)]
    if draw:
        rows.append((380,0x2))
        for i in range(85):
            direction = (0, 0x40, 0x80, 0x10, 0x20)[i%5]
            rows.append((500+22*i,0x100 | direction))
    pad = run / "input.pad"
    pad.write_text("".join(f"{n} {n+2} {mask:x}\n" for n,mask in rows))
    env = {k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env.update(SNATCHER_PAD="genesis3", SNATCHER_AUDIO=str(run/"audio.wav"), SNATCHER_CAPTURE_EVERY="250",
               SNATCHER_CAPTURE_PREFIX=str(run/"frame"))
    result = run / "score.state"
    with (run / "core.log").open("w") as log:
        subprocess.run([uncut/"build/harness/runner", core, uncut/"private/bios", run, cue,
                        "4200", run/"feedback.png", pad, state, result],
                       check=True,env=env,stdout=log,stderr=log)
    values = score(result)
    if draw:
        if not (values["drew_weapon"] and values["enemies"] and values["civilians"] and values["misses"]
                and values["fired"] == values["enemies"]+values["civilians"]+values["misses"]):
            raise SystemExit(f"Missing retail shot outcomes: {values} in {run}")
    elif any(values.values()):
        raise SystemExit(f"Expected holstered practice result: {values} in {run}")
    results[name] = dict(score=values, route_sha256=hashlib.sha256(pad.read_bytes()).hexdigest())
receipt = dict(source="US retail Sega CD", initial_state_sha256=hashlib.sha256(state.read_bytes()).hexdigest(),
               core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(), results=results)
(out / "receipt.json").write_text(json.dumps(receipt, indent=2)+"\n")
print(out)
