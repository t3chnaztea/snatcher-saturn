"""Replay the Sega CD informer call from Engineering through the return to the room."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from PIL import Image, ImageChops

root=Path(__file__).resolve().parents[1]
uncut=root.parent/"snatcher-uncut"
sonic=root.parent/"sonic-cd-saturn"
source=uncut/"build/evidence/m5/playthrough-lane/natural-run"
out=Path(tempfile.mkdtemp(prefix="retail-videophone-",dir=root/"build"))
flags=shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","libpng"],text=True))
subprocess.run(["cc","-O2","-I"+str(uncut/"tools/harness"),"-I"+str(sonic/".deps/beetle-saturn/libretro-common/include"),
                root/"tools/factory_core.c",*flags,"-o",out/"runner"],check=True)

start=source/"1442/native.state"
record=json.loads((start.parent/"receipt.json").read_text())
if hashlib.sha1(start.read_bytes()).hexdigest()!=record["state"]["sha1"]:
    raise ValueError("Expected the original Engineering videophone menu checkpoint")
elapsed=0
checks={}
for index in range(1443,1467):
    folder=source/str(index)
    step=out/str(index)
    step.mkdir()
    recorded=json.loads((folder/"receipt.json").read_text())
    duration=recorded["frames"]
    previous=source/str(index-1)/"native.state"
    if hashlib.sha1(previous.read_bytes()).hexdigest()!=recorded["load_state"]["sha1"]:
        raise ValueError(f"Wrong source checkpoint before {index}")
    env={k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env.update(SNATCHER_PAD="genesis3",SNATCHER_FRAME_HASHES=str(step/"frames.txt"),
               SNATCHER_AUDIO=str(step/"mix.wav"))
    with (step/"core.log").open("w") as log:
        subprocess.run([out/"runner",uncut/".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib",
                        uncut/"private/bios",step,uncut/"private/discs/segacd-usa/Snatcher.cue",
                        str(duration),step/"end.png",folder/"input.pad",previous],env=env,
                       check=True,stdout=log,stderr=log)
    played=(step/"frames.txt").read_text().splitlines()[-1].split()[1:]
    elapsed+=duration
    image=Image.open(source/str(index)/"screen.png").convert("RGB")
    image=image.point(lambda c:(min(7,(c+17)//34)*255//7*31//255)<<3)
    expected=[]
    for rect in [(32,8,224,136),(16,142,232,224)]:
        h=14695981039346656037
        for color in image.crop(rect).tobytes():
            h=((h^color)*1099511628211)&0xffffffffffffffff
        expected.append(f"{h:016x}")
    if played!=expected:
        raise ValueError(f"Sega CD picture or text differs at checkpoint {index}: {out}")
    checks[index]={"frames":duration,"scene":expected[0],"panel":expected[1]}
# Actor 31 loads the background plane after the M0 initializer. Without
# this second transfer the center of the phone appears black instead of blue.
sys.path.insert(0,str(uncut/"tools"))
import scd_gfx as gfx
module=(uncut/"private/extracted/segacd-usa/DATA_M0.BIN").read_bytes()
seq=gfx.sequences(module)[0]
commands=seq["commands"]
tiles=bytearray(65536)
streams,errors=gfx.resources(module,[seq])
if errors: raise ValueError(errors)
for stream in streams:
    raw=gfx.stream_bytes(module,stream)
    for ref in stream["references"]:
        addr=ref["vram"]
        tiles[addr:addr+len(raw)]=raw
controller=next(p for cmd in commands if cmd["op"]==2
                for p in range(cmd["body"],cmd["body"]+cmd["length"],12) if module[p]==31)
pc=controller+12+int.from_bytes(module[controller+10:controller+12],"big",signed=True)
if module[pc:pc+2]!=bytes((0x97,0)) or module[pc+4]!=0x8a:
    raise ValueError("Expected the videophone background transfer")
event=pc+gfx.u16(module,pc+6)
offset=gfx.u32(module,event+2)-gfx.BASE
addr=gfx.u16(module,event+6)
size=gfx.u16(module,event+10)
if addr!=0xc000 or gfx.u16(module,offset)!=size:
    raise ValueError("Invalid videophone plane")
tiles[addr:addr+size]=gfx.decode(module,offset+2,size)[0]
colors,_=gfx.palette(module,commands)
# Digit lamps begin paused on a hidden frame until the corresponding keypress.
actors=[o for o in gfx.sprite_frames(module,commands)
        if not module[o["record"]+1]&2 and module[o["script"]] != 0x93]
picture=gfx.draw_sprites(gfx.compose(tiles,colors),tiles,colors,actors).crop((32,8,224,136))
original=Image.open(source/"1444/screen.png").convert("RGB").crop((32,8,224,136))
original=original.point(lambda c:min(7,(c+17)//34)*255//7)
if ImageChops.difference(original,picture).getbbox():
    raise ValueError("Compiled videophone does not match the original Call menu")
picture.save(out/"compiled-phone.png")
(out/"receipt.json").write_text(json.dumps(dict(frames=elapsed,phone_pixels=picture.width*picture.height,source_checkpoint_loads=len(checks),start_sha1=record["state"]["sha1"],checks=checks),
                                           indent=2)+"\n")
print(out)
