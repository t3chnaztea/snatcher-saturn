"""Replay the first factory fight on the US Sega CD disc for Saturn acceptance."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
uncut = root.parent/"snatcher-uncut"
sonic = root.parent/"sonic-cd-saturn"
reference = uncut/"build/evidence/m5/playthrough-lane/natural-run/0822/native.state"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--state", type=Path, default=reference)
args = parser.parse_args()
if hashlib.sha1(args.state.read_bytes()).hexdigest() != "7ea4bf0e8256db344c9acca814b8388745a8e61f":
    parser.error("Expected the Uncut controller-only factory checkpoint at frame 179176")
out = Path(tempfile.mkdtemp(prefix="insector-reference-", dir=root/"build"))
flags = shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","libpng"],text=True))
subprocess.run(["cc","-O2","-I"+str(sonic/".deps/beetle-saturn/libretro-common/include"),
                uncut/"tools/harness/runner.c",*flags,"-o",out/"runner"],check=True)
# Genesis Plus GX serializes the sub-CPU memory as host-order 68000 words.
code = (uncut/"private/extracted/segacd-usa/SUBCODE.BIN").read_bytes()[:256]
marker = bytearray(code)
marker[::2],marker[1::2] = code[1::2],code[::2]
def replay(case):
    name,frames,pad = case
    target = out/name
    target.mkdir()
    state = target/"end.state"
    env = {k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env["SNATCHER_PAD"]="genesis3"
    with (target/"core.log").open("w") as log:
        subprocess.run([out/"runner",uncut/".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib",
                        uncut/"private/bios",target,uncut/"private/discs/segacd-usa/Snatcher.cue",
                        str(frames),target/"end.png",pad,args.state.resolve(),state],
                       check=True,env=env,stdout=log,stderr=log)
    data = state.read_bytes()
    if data.count(marker)!=1: raise ValueError("Could not locate the verified sub-CPU program")
    base=data.index(marker)-0xd400
    names=("shots","enemies","civilians","misses","damage")
    return dict(zip(names,struct.unpack_from("<5H",data,base+0x7908)))
cases=[("draw-and-fire",2304,root/"tools/routes/retail-factory-insectors.pad"),
       ("no-input",8500,"-")]
with ThreadPoolExecutor(2) as pool:
    results=dict(zip([c[0] for c in cases],pool.map(replay,cases)))
(out/"receipt.json").write_text(json.dumps(results,indent=2)+"\n")
print(out,results)
if list(results["draw-and-fire"].values()) != [34,34,0,0,0] or list(results["no-input"].values()) != [0,0,0,0,6]:
    raise SystemExit("Factory combat results differ from the retail reference")
