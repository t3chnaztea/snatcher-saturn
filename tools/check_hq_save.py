"""Save the post-factory evidence in slot three. Check a reset and a subsequent cold boot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
sonic = root.parent / "sonic-cd-saturn"
uncut = root.parent / "snatcher-uncut"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--disc", required=True, type=Path)
parser.add_argument("--backup", required=True, type=Path, help="Gibson backup with slots one and two occupied")
args = parser.parse_args()
disc = args.disc.resolve()
prior = args.backup.resolve()
battery = prior.read_bytes()
if len(battery) != 32768 or any(name not in battery for name in (b"SNATCHERS1",b"SNATCHERS2")) or b"SNATCHERS3" in battery:
    parser.error("Expected the factory backup with the third slot empty")
out = Path(tempfile.mkdtemp(prefix="hq-save-",dir=root/"build"))
flags = shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","libpng"],text=True))
subprocess.run(["cc","-O2","-I"+str(uncut/"tools/harness"),"-I"+str(sonic/".deps/beetle-saturn/libretro-common/include"),
                root/"tools/factory_core.c",*flags,"-o",out/"runner"],check=True)

def run(name, frames, pad, backup=None, reset_frame=0):
    directory = out/name
    directory.mkdir()
    (directory/"input.pad").write_text(pad)
    env = {k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env["SNATCHER_FRAME_HASHES"] = str(directory/"frames.txt")
    state = "-"
    if backup:
        core = sonic/".deps/beetle-saturn/mednafen_saturn_libretro.dylib"
        bios = sonic/"assets/private"
        cue = disc
        env.update(SNATCHER_PAD="generic",SNATCHER_BACKUP_INPUT=str(backup),
                   SNATCHER_BACKUP_OUTPUT=str(directory/"internal.bin"),SNATCHER_RESET_FRAME=str(reset_frame))
    else:
        core = uncut/".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib"
        bios = uncut/"private/bios"
        cue = uncut/"private/discs/segacd-usa/Snatcher.cue"
        state = uncut/"build/evidence/m5/playthrough-lane/natural-run/1361/native.state"
        env["SNATCHER_PAD"]="genesis3"
    with (directory/"core.log").open("w") as log:
        subprocess.run([out/"runner",core,bios,directory,cue,str(frames),directory/"end.png",
                        directory/"input.pad",state],env=env,stdout=log,stderr=log,check=True)
    return (directory/"frames.txt").read_text().splitlines()[-1].split()[1:]

def buttons(events, offset=0):
    return "".join(f"{n+offset} {n+offset+3} {k}\n" for n,k in events)

# The retail checkpoint has just returned from inspecting the chess piece.
expected = run("retail",1100,buttons([(60,"20"),(180,"100"),(360,"100"),(540,"20"),(660,"20"),(780,"100")]))
routes = root/"tools/routes"
route = ""
for filename,cutoff in [("factory-escape-from-save.pad",25500),("factory-hq-return.pad",42000),("hq-investigation.pad",52020)]:
    for line in (routes/filename).read_text().splitlines():
        if line and not line.startswith("#") and int(line.split()[0]) < cutoff:
            route += line+"\n"
# Use Metal Gear > Save > Save 3. Allow the BIOS write to finish before resetting.
route += buttons([(4820,"20"),(4870,"20"),(4920,"20"),(4970,"800"),(5020,"20"),(5070,"800"),
                  (5120,"800"),(5170,"800")],47200)
route += buttons([(1,"20"),(51,"20"),(101,"800"),(151,"800"),(201,"800")],55100)
load = [(1800,"20"),(2000,"800"),(2250,"20"),(2450,"20"),(2800,"800"),
        (3300,"20"),(3350,"20"),(3400,"20"),(3450,"800"),(3500,"800"),
        (3550,"20"),(3600,"20"),(3650,"800")]
reset_frame=56000
after_reset = run("reset",reset_frame+4400,route+buttons(load,reset_frame),prior,reset_frame)
saved = out/"reset/internal.bin"
if b"SNATCHERS3A" not in saved.read_bytes():
    raise SystemExit(f"New slot three missing: {out}")
after_cold = run("cold",4400,buttons(load),saved)
if after_reset!=expected or after_cold!=expected or saved.read_bytes()!=(out/"cold/internal.bin").read_bytes():
    raise SystemExit(f"Room, evidence list, or battery differs after recovery: {out}")
with disc.with_suffix(".bin").open("rb") as f:
    digest=hashlib.file_digest(f,"sha256").hexdigest()
(out/"receipt.json").write_text(json.dumps(dict(bin_sha256=digest,slot=3,reset_frame=reset_frame,
    retail_picture=expected[0],retail_evidence_menu=expected[1],saturn_state_loads=0,
    backup_sha256=hashlib.sha256(saved.read_bytes()).hexdigest(),
    recovered=["Scrap of Paper","Key","Chess Piece","Disk"]),indent=2)+"\n")
print(out)
