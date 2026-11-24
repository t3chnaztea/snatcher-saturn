"""Play both factory fight outcomes and retry from GAME OVER on Beetle Saturn."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
uncut = root.parent / "snatcher-uncut"
sonic = root.parent / "sonic-cd-saturn"
routes = root / "tools/routes"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--disc", type=Path, required=True)
parser.add_argument("--backup", type=Path, required=True, help="Gibson slot two from check_factory_save.py")
args = parser.parse_args()
disc = args.disc.resolve()
out = Path(tempfile.mkdtemp(prefix="insector-saturn-", dir=root/"build"))

def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

release = json.loads((disc.parent/"build-receipt.json").read_text())
digest = sha(disc.with_suffix(".bin"))
if digest != release["sha256"][disc.with_suffix(".bin").name]:
    parser.error("The image differs from its build receipt")
if sha(root/"dist/bin-cue/snatcher-saturn.bin") != release["saturn_track1_sha256"]:
    parser.error("Build the matching ELF with bash tools/build.sh before reading its scores")
symbols = (root/"build/saturn/snatcher-saturn.sym").read_text()
symbol, = re.findall(r"^(\w+) [bB] _game(?:\.lto_priv\.\d+)?$", symbols, re.M)
offset_tool = out/"offset"
subprocess.run(["cc","-Isrc","-x","c","-","-o",offset_tool],cwd=root,check=True,text=True,
               input='#include "script.h"\n#include <stdio.h>\n#include <stddef.h>\n'
                     'int main(void){printf("%zu",offsetof(struct investigation,practice));}')
score_offset = int(symbol,16)-0x06000000+int(subprocess.check_output([offset_tool]))
core = sonic/".deps/beetle-saturn/mednafen_saturn_libretro.dylib"
flags = shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","libpng"],text=True))
subprocess.run(["cc","-O2","-I"+str(uncut/"tools/harness"),
                "-I"+str(sonic/".deps/beetle-saturn/libretro-common/include"),root/"tools/backup_core.c",
                *flags,"-o",out/"runner"],check=True)

def play(name,frames,pad,state=None):
    run = out/name
    run.mkdir()
    env = {k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env["SNATCHER_PAD"]="generic"
    if state is None:
        env.update(SNATCHER_BACKUP_INPUT=str(args.backup.resolve()),SNATCHER_BACKUP_OUTPUT=str(run/"internal.bin"))
    with (run/"core.log").open("w") as log:
        subprocess.run([out/"runner",core,sonic/"assets/private",run,disc,str(frames),run/"end.png",
                        pad,state or "-",run/"end.state"],env=env,check=True,stdout=log,stderr=log)
    return run/"end.state"

briefing = play("briefing",25845,routes/"factory-escape-from-save.pad")
holstered = out/"holstered.pad"
holstered.write_text("20 24 800\n90 94 800\n160 164 800\n230 234 800\n")
with ThreadPoolExecutor(2) as pool:
    victory = pool.submit(play,"victory",5200,routes/"factory-insectors.pad",briefing)
    defeat = pool.submit(play,"defeat",4300,holstered,briefing)
    win,loss = victory.result(),defeat.result()
retry = play("retry",5500,routes/"factory-insector-retry.pad",loss)
names = ("shots","hits","civilians","misses","damage","all_civilians","drawn")
scores = {}
for name,state in [("victory",win),("defeat",loss),("retry",retry)]:
    data=state.read_bytes()
    marker=b"\x08WorkRAMH"+struct.pack("<I",0x100000)
    if data.count(marker)!=1: raise ValueError("Unsupported Beetle work RAM state")
    values=struct.unpack_from("<7H",data,data.index(marker)+len(marker)+score_offset)
    scores[name]=dict(zip(names,values))
    expected=(0,0,0,0,6,0,0) if name=="defeat" else (34,34,0,0,0,0,1)
    if values!=expected: raise ValueError(f"{name} returned {values}, expected {expected}: {out}")
if (win.parent/"end.png").read_bytes()!=(retry.parent/"end.png").read_bytes():
    raise ValueError(f"Retry did not restore the winning scene: {out}")
(out/"receipt.json").write_text(json.dumps(dict(bin_sha256=digest,core_sha256=sha(core),
    backup_sha256=sha(args.backup),scores=scores),indent=2)+"\n")
print(out,scores)
