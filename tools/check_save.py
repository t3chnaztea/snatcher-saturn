"""Use four-slot game commands, Beetle internal memory, a reset, and a separate cold boot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from PIL import Image

root=Path(__file__).resolve().parents[1]
uncut=root.parent/"snatcher-uncut"
sonic=root.parent/"sonic-cd-saturn"
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--disc",type=Path,required=True)
parser.add_argument("--approach-pad",type=Path,default=root/"tools/routes/act1-to-cockpit.pad",
                    help="Recorded New Game inputs up to the parking lot")
parser.add_argument("--parking-frame",type=int,default=73128,
                    help="Frame at which the parking lot accepts the test commands")
args=parser.parse_args()
if args.parking_frame<200:
    parser.error("The parking frame must leave time for the first comparison picture")
disc=args.disc.resolve()
out=Path(tempfile.mkdtemp(prefix="save-",dir=root/"build"))
flags=shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","libpng"],text=True))
subprocess.run(["cc","-std=gnu11","-O2","-I"+str(uncut/"tools/harness"),
                "-I"+str(sonic/".deps/beetle-saturn/libretro-common/include"),
                root/"tools/backup_core.c",*flags,"-o",out/"runner"],check=True)
core=sonic/".deps/beetle-saturn/mednafen_saturn_libretro.dylib"

def play(label,buttons,frames,backup=None,reset=None):
    d=out/label
    d.mkdir()
    pad=d/"route.pad"
    pad.write_text("".join(f"{f} {last} {b}\n" for f,last,b in buttons))
    env={k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env.update(SNATCHER_PAD="generic",SNATCHER_BACKUP_OUTPUT=str(d/"internal.bin"),
               SNATCHER_CAPTURE_PREFIX=str(d/"frame"),SNATCHER_CAPTURE_EVERY="100")
    if backup: env["SNATCHER_BACKUP_INPUT"]=str(backup)
    if reset: env["SNATCHER_RESET_FRAME"]=str(reset)
    with (d/"core.log").open("w") as log:
        subprocess.run([out/"runner",core,sonic/"assets/private",d,disc,str(frames),d/"end.png",pad],
                       check=True,stdout=log,stderr=log,env=env)
    return d

def press(buttons):
    return [(f,f+2,b) for f,b in buttons]

route=[]
for line in args.approach_pad.read_text().splitlines():
    if line and not line.startswith("#"):
        first,last,button=line.split()
        if int(first)<args.parking_frame: route.append((int(first),int(last),button))
# This optional investigation changes a story flag before Metal Gear saves it.
t=args.parking_frame
body=[(80,"20"),(260,"800"),(420,"800"),(900,"800"),(1300,"800")]
# Look leaves the root cursor on Look. Move down twice to Use Metal Gear.
save=[(1900,"20"),(2040,"20"),(2200,"800"),(2350,"20"),(2500,"800"),
      (2950,"800"),(3350,"800"),(3900,"800")]
route+=press([(t+f,b) for f,b in body+save])
# Reset the running core after the first slot is committed. New Game is the
# first title choice. Down selects Continue, then C selects the occupied slot.
reset_at=t+4872
load=[(1800,"20"),(2000,"800"),(2300,"800")]
route+=press([(reset_at+f,b) for f,b in load])
first=play("write-reset",route,reset_at+3000,reset=reset_at)
cold=play("cold-load",press(load),3000,first/"internal.bin")
if (cold/"internal.bin").read_bytes()!=(first/"internal.bin").read_bytes():
    raise SystemExit(f"Loading changed internal backup memory: {out}")
# The saved root is the parking lot. Selecting Look again must take its
# recorded branch, and both boots must show the same restored scene.
def pixels(path):
    return Image.open(path).convert("RGB").crop((37,0,293,224)).tobytes()
def captured(frame):
    return first/f"frame-{frame//100*100:06}.png"

if pixels(first/"end.png")!=pixels(cold/"end.png") or pixels(captured(t-128))!=pixels(cold/"end.png"):
    raise SystemExit(f"Restored parking lot differs after reset or cold boot: {out}")
if b"SNATCHERS1A" not in (first/"internal.bin").read_bytes():
    raise SystemExit(f"Missing Saturn backup directory entry: {out}")
# Reading the body the second time skips the extra line about its maker.
probe=play("restored-flag",press(load+[(3250,"20"),(3450,"800"),(3650,"800"),(4100,"800")]),
           4400,cold/"internal.bin")
if pixels(probe/"end.png") != pixels(captured(t+1472)):
    raise SystemExit(f"Restored investigation flag differs: {out}")

def save_menu_buttons():
    return load+[(3200,"20"),(3300,"20"),(3400,"20"),(3550,"800"),(3700,"20"),
                 (3850,"800"),(4250,"800"),(4650,"800")]

battery=cold/"internal.bin"
for slot in (2,3,4):
    moves=save_menu_buttons()+[(4900+100*i,"20") for i in range(slot-1)]+[(5300,"800")]
    created=play(f"write-slot-{slot}",press(moves),5850,battery)
    if f"SNATCHERS{slot}A".encode() not in (created/"internal.bin").read_bytes():
        raise SystemExit(f"Missing slot {slot}: {out}")
    battery=created/"internal.bin"

overwrite=save_menu_buttons()+[(5000,"800"),(5400,"800"),(5800,"800")]
decline=play("decline-overwrite",press(overwrite+[(6100,"20"),(6300,"800")]),6600,battery)
if (decline/"internal.bin").read_bytes()!=battery.read_bytes():
    raise SystemExit(f"Declining overwrite changed internal memory: {out}")
accepted=play("accept-overwrite",press(overwrite+[(6300,"800")]),6700,battery)
if b"SNATCHERS1B" not in (accepted/"internal.bin").read_bytes():
    raise SystemExit(f"Missing new generation after overwrite: {out}")
for slot in (1,2,3,4):
    moves=load[:2]+[(2250+100*i,"20") for i in range(slot-1)]+[(2850,"800")]
    loaded=play(f"reload-slot-{slot}",press(moves),3450,accepted/"internal.bin")
    # All four records are from the same parking lot. Check the selected file
    # on the title screen before confirming, as well as the restored scene.
    with Image.open(loaded/"frame-002800.png") as menu:
        palette=menu.convert("RGB")
        selected=[i+1 for i in range(4) if palette.getpixel((120,155+9*i))==(32,64,248)]
    if selected != [slot]:
        raise SystemExit(f"Expected file {slot}, highlighted {selected}: {out}")
    if pixels(loaded/"end.png")!=pixels(cold/"end.png"):
        raise SystemExit(f"Could not reload slot {slot}: {out}")

with disc.with_suffix(".bin").open("rb") as stream:
    checksum=hashlib.file_digest(stream,"sha256").hexdigest()
(out/"receipt.json").write_text(json.dumps(dict(bin_sha256=checksum,reset_frame=reset_at,
    cold_state_loads=0,backup_bytes=32768,slots=[1,2,3,4],restored_flag=True,overwrite=["decline","accept"]),indent=2)+"\n")
print(out)
