"""Test shooting encounters on a cold Beetle boot from the selected room's backup."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

root = Path(__file__).resolve().parents[1]
sonic = root.parent / "sonic-cd-saturn"
uncut = root.parent / "snatcher-uncut"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--disc", required=True, type=Path)
parser.add_argument("--backup", required=True, type=Path, help="Internal backup containing the selected room")
parser.add_argument("--native-build", type=Path, help="Development directory containing saturn/ symbols and dist/ data track")
parser.add_argument("--room", choices=("301","202","operating","crawler","tunnel","taxi","ceiling","mika","swarm","final-corridor"), default="301")
parser.add_argument("--hostage", action="store_true", help="Test the hostage fight after Lisa in Room 202")
parser.add_argument("--lisa-pad", type=Path, help="Room 202 investigation inputs through the bottle examination")
parser.add_argument("--lisa-offset", type=int, default=0, help="Shift the Lisa encounter inputs and recording end by this many frames")
parser.add_argument("--fight-delay", type=int, default=0, help="Shift the recorded Lisa pad inputs by this many frames")
parser.add_argument("--hostage-pad", type=Path, help="Investigation and Lisa fight inputs up to the hostage encounter")
parser.add_argument("--hostage-start", type=int, default=34550, help="First frame for the hostage trigger test")
parser.add_argument("--ivan-pad", type=Path, help="Room 301 investigation inputs up to Ivan's fight")
parser.add_argument("--ivan-start", type=int, default=8260, help="First trigger frame in Ivan's fight")
parser.add_argument("--skeleton-start",type=int,default=7264,help="Frame for the first operating room trigger")
parser.add_argument("--crawler-start",type=int,default=10318,help="Frame for the crawling skeleton trigger")
parser.add_argument("--tunnel-inputs", type=Path, help="Directory containing the two recorded tunnel fight inputs")
parser.add_argument("--mika-inputs", type=Path, help="Directory containing mika-pad-fight.pad and mika-stunner.gun")
parser.add_argument("--corridor-route",type=Path,help="Matching corridor pad recording with a sibling .gun file")
args = parser.parse_args()
if args.mika_inputs and args.room != "mika":
    parser.error("--mika-inputs requires --room mika")
if args.corridor_route and args.room not in ("swarm","final-corridor"):
    parser.error("--corridor-route requires a corridor encounter")
if (args.lisa_pad or args.lisa_offset) and (args.room != "202" or args.hostage):
    parser.error("Lisa route options require --room 202 without --hostage")
if args.lisa_offset <= -19800:
    parser.error("The Lisa trigger schedule must start after boot")
if args.ivan_start < 0:
    parser.error("--ivan-start must be nonnegative")
if args.ivan_pad and args.room != "301":
    parser.error("--ivan-pad requires --room 301")
if args.hostage_start < 0:
    parser.error("--hostage-start must be nonnegative")
if args.hostage and args.room != "202":
    parser.error("--hostage requires --room 202")
disc = args.disc.resolve()
backup = args.backup.resolve()
out = Path(tempfile.mkdtemp(prefix="stunner-duel-",dir=root/"build"))

def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()

release = json.loads((disc.parent/"build-receipt.json").read_text())
bin_hash = sha(disc.with_suffix(".bin"))
if bin_hash != release["sha256"]["snatcher-saturn.bin"]:
    parser.error("The Saturn BIN differs from its build receipt")
data_root=args.native_build or root
symbol_root=args.native_build or (root/"build")
if sha(data_root/"dist/bin-cue/snatcher-saturn.bin") != release["saturn_track1_sha256"]:
    parser.error("Run bash tools/build.sh for the matching retail ELF")
symbols = (symbol_root/"saturn/snatcher-saturn.sym").read_text()
symbol, = re.findall(r"^(\w+) [bB] _game(?:\.lto_priv\.\d+)?$",symbols,re.M)
subprocess.run(["cc","-I"+str(root/"src"),"-x","c","-","-o",out/"offset"],
               input='#include "script.h"\n#include <stddef.h>\n#include <stdio.h>\n'
                     'int main(void){printf("%zu %zu",offsetof(struct investigation,practice),offsetof(struct investigation,scene));}',
               text=True,check=True)
game_offset=int(symbol,16)-0x06000000
score_offset,scene_offset=map(int,subprocess.check_output([out/"offset"]).split())
flags = shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","libpng"],text=True))
subprocess.run(["cc","-O2","-I"+str(uncut/"tools/harness"),
                "-I"+str(sonic/".deps/beetle-saturn/libretro-common/include"),
                root/"tools/lightgun_core.c",*flags,"-o",out/"runner"],check=True)
core = sonic/".deps/beetle-saturn/mednafen_saturn_libretro.dylib"
routes=root/"tools/routes"
bathroom=args.room=="202"
pad=routes/("room202-investigation.pad" if bathroom else "room301-stunner.pad")
driver=args.room=="taxi"
ceiling=args.room=="ceiling"
mika=args.room=="mika"
final_corridor=args.room=="final-corridor"
swarm=args.room=="swarm" or final_corridor
tunnel=args.room=="tunnel"
tunnel_inputs=args.tunnel_inputs or routes
crawler=args.room=="crawler"
skeleton=args.room in ("operating","crawler")
if args.room=="301" and args.ivan_pad:
    pad = args.ivan_pad
cases = [("on-target",0,-6000,0),("wrong-field",-12800,-18000,0),("offscreen",0,-6000,1)]
if swarm:
    route_stem="final-corridor" if final_corridor else "corridor-swarm"
    pad=args.corridor_route or routes/(route_stem+".pad")
    wrong_y=-18000 if final_corridor else -9000
    cases=[("stunner",0,0,0),("pad",0,0,0),("wrong-field",0,wrong_y,0),
           ("offscreen",0,wrong_y,1),("held",0,wrong_y,0),("idle",0,0,0)]
elif mika:
    pad=routes/"mika-approach.pad"
    cases=[("stunner",0,0,0),("pad",0,0,0),("hostage",0,-6000,0),
           ("offscreen",0,-6000,1),("held",0,-6000,1)]
elif ceiling:
    pad=routes/"ceiling-approach.pad"
    cases=[("on-target",0,-18000,0),("pad",0,0,0),("wrong-field",-12800,-18000,0),
           ("offscreen",0,-18000,1),("held",-12800,-18000,0)]
elif driver:
    pad=routes/"taxi-approach.pad"
    cases=[("on-target",12800,-6000,0),("pad",0,0,0),("wrong-field",-12800,-6000,0),
           ("offscreen",12800,-6000,1),("held",-12800,-6000,0)]
elif tunnel:
    pad=routes/"tunnel-approach.pad"
    cases=[("stunner",0,0,0),("pad",0,0,0),("wrong-field",-12800,-18000,0),
           ("offscreen",0,-18000,1),("held",-12800,-18000,0)]
elif skeleton:
    pad=routes/("operating-room-crawler.pad" if crawler else "operating-room-stunner.pad")
    x,wrong,y=(-12800,0,0) if crawler else (0,-12800,-18000)
    cases=[("on-target",x,y,0),("wrong-field",wrong,y,0),
           ("offscreen",x,y,1),("held",wrong,y,0)]
elif args.hostage:
    pad=args.hostage_pad or routes/"room202-hostage.pad"
    cases=[("on-target",0,-18000,0),("wrong-field",-12800,-18000,0),("offscreen",0,-18000,1),("held",-12800,-18000,0)]
elif bathroom:
    pad=args.lisa_pad or pad
    cases=[("stunner",0,0,0),("pad",0,0,0),("idle",0,0,0)]
if bathroom or tunnel or driver or ceiling or mika or swarm:
    subprocess.run(["cc","-O2","-I"+str(uncut/"tools/harness"),
                    "-I"+str(sonic/".deps/beetle-saturn/libretro-common/include"),
                    root/"tools/backup_core.c",*flags,"-o",out/"pad-runner"],check=True)

def play(case):
    name,x,y,offscreen = case
    work = out/name
    work.mkdir()
    gun = work/"gun.txt"
    runner=out/"runner"
    inputs=pad
    frames=9700
    if swarm:
        # Read the score after cleanup, before the next encounter resets it.
        frames=35160 if final_corridor else 30040
        events=[]
        if name=="pad":
            runner=out/"pad-runner"
        else:
            inputs=work/"approach.pad"
            inputs.write_text("".join(line for line in pad.read_text().splitlines(True)
                                      if int(line.split()[0])<24900))
            run=[tuple(map(int,line.split())) for line in pad.with_suffix(".gun").read_text().splitlines()]
            start=31230 if final_corridor else 25000
            if final_corridor:
                events=[e for e in run if e[0]<30100]
            if name=="stunner":
                events=run
            elif name=="held":
                events.append((start,start+1000,x,y,offscreen))
            elif name!="idle":
                events.extend((f,f+3,x,y,offscreen) for f in (start,start+40,start+80))
    elif mika:
        frames=16200
        positive_gun = [(10594,10597,12800,6000,0),(10686,10689,-12800,-18000,0),
                        (11801,11804,12800,6000,0),(11903,11906,12800,-18000,0)]
        if args.mika_inputs:
            gun_file = args.mika_inputs/"mika-stunner.gun"
            positive_gun = [tuple(map(int,line.split())) for line in gun_file.read_text().splitlines()]
        start = positive_gun[0][0]
        if name=="pad":
            runner=out/"pad-runner"
            inputs=work/"input.pad"
            if args.mika_inputs:
                fight = (args.mika_inputs/"mika-pad-fight.pad").read_text()
            else:
                shots=[(10594,0x8a0),(10685,0x850),(11798,0x8a0),(11896,0x890),(11996,0x890)]
                fight="10561 10563 1\n"+"".join(f"{f} {f+3} {mask:x}\n" for f,mask in shots)
            inputs.write_text(pad.read_text().rstrip()+"\n"+fight)
            events=[]
        elif name=="stunner":
            events=positive_gun
        elif name=="held":
            events=[(start,start+1006,x,y,offscreen)]
        else:
            events=[(start+i*32,start+3+i*32,x,y,offscreen) for i in range(6)]
    elif driver or ceiling:
        frames=7400
        start=4180 if ceiling else 3880
        events=[]
        if name=="pad":
            runner=out/"pad-runner"
            inputs=work/"input.pad"
            draw=4170 if ceiling else start
            aim=0x810 if ceiling else 0x880
            inputs.write_text(pad.read_text()+f"{draw} {draw+3} 1\n{draw+20} {draw+23} {aim:x}\n")
        elif name=="held":
            events=[(start,start+650,x,y,offscreen)]
        else:
            offsets=(0,) if name=="on-target" else (0,30,60)
            events=[(start+n,start+n+3,x,y,offscreen) for n in offsets]
    elif tunnel:
        frames=13600
        events=[]
        if name=="stunner":
            events=[tuple(map(int,line.split())) for line in (tunnel_inputs/"tunnel-stunner.gun").read_text().splitlines()]
        elif name=="pad":
            runner=out/"pad-runner"
            inputs=work/"input.pad"
            inputs.write_text(pad.read_text()+(tunnel_inputs/"tunnel-pad-fight.pad").read_text())
        elif name=="held":
            events=[(7149,8750,x,y,offscreen)]
        else:
            events=[(f,f+3,x,y,offscreen) for f in (7149,7180,7210)]
    elif skeleton:
        start=args.crawler_start if crawler else args.skeleton_start
        frames=start+(4382 if crawler else 3236)
        offsets=(0,) if name=="on-target" else (0,30,60)
        events=[(start+n,start+n+3,x,y,offscreen) for n in offsets]
        if name=="held": events=[(start,start+1600,x,y,offscreen)]
    elif args.hostage:
        start=args.hostage_start
        frames=start+7950
        events=[(f,f+3,x,y,offscreen) for f in range(start,start+1720,18)]
        if name=="held":
            events=[(start,start+1720,x,y,offscreen)]
    elif bathroom:
        frames=23500+args.lisa_offset
        events=[(f+args.lisa_offset,f+args.lisa_offset+3,0,(-18000,-6000)[i%2],0) for i,f in enumerate(range(19800,23200,16))] if name=="stunner" else []
        if name!="stunner":
            runner=out/"pad-runner"
        if name=="pad":
            inputs=work/"input.pad"
            fight = []
            for line in (routes/"room202-fight.pad").read_text().splitlines():
                first, last, mask = line.split()
                fight.append(f"{int(first)+args.lisa_offset+args.fight_delay} {int(last)+args.lisa_offset+args.fight_delay} {mask}\n")
            inputs.write_text(pad.read_text()+"".join(fight))
    else:
        frames=args.ivan_start+1440
        events=[(f,f+4,x,y,offscreen) for f in range(args.ivan_start,args.ivan_start+121,60)]
    gun.write_text("".join(" ".join(map(str,event))+"\n" for event in events))
    env = {k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env.update(SNATCHER_GUN_INPUT=str(gun),SNATCHER_BACKUP_INPUT=str(backup),
               SNATCHER_BACKUP_OUTPUT=str(work/"internal.bin"),SNATCHER_PAD="generic")
    with (work/"core.log").open("w") as log:
        subprocess.run([runner,core,sonic/"assets/private",work,disc,str(frames),
                        work/"end.png",inputs,"-",work/"end.state"],env=env,
                       stdout=log,stderr=log,check=True)
    if runner==out/"runner" and "Controller 2: Stunner" not in (work/"core.log").read_text():
        raise ValueError("Beetle did not attach the Stunner")
    state = (work/"end.state").read_bytes()
    marker = b"\x08WorkRAMH"+struct.pack("<I",0x100000)
    if state.count(marker)!=1: raise ValueError("Unsupported Beetle work RAM layout")
    game_base=state.index(marker)+len(marker)+game_offset
    shots,hits,civilians,misses,damage,_,drawn = struct.unpack_from("<7H",state,game_base+score_offset)
    scene,=struct.unpack_from("<H",state,game_base+scene_offset)
    expected = (1,1,0,0,1) if name=="on-target" else (3,0,0,3,1)
    if swarm:
        won=name in ("stunner","pad")
        count={"stunner":40 if final_corridor else 64,"pad":32 if final_corridor else 80,"wrong-field":3,"offscreen":3,"held":1,"idle":0}[name]
        valid=(shots==count and hits==(count if won else 0) and misses==shots-hits
               and civilians==0 and drawn==int(name!="idle") and (damage<6)==won
               and (scene==(0x2902 if final_corridor else 0x2901) if won else damage==6 and scene==0x2905))
    elif mika:
        won=name in ("stunner","pad")
        expected_shots={"stunner":4,"pad":5,"hostage":5,"offscreen":6,"held":1}[name]
        valid=(drawn==1 and shots==expected_shots and hits==(shots if won else 0)
               and misses==(0 if name=="hostage" else shots) and civilians==0
               and (damage<6)==won and (scene!=0x2905)==won)
    elif tunnel:
        won=name in ("stunner","pad")
        quota=64 if name=="stunner" else 58
        valid=(drawn==1 and civilians==0 and misses==shots-hits and
               ((hits==quota and damage<6 and scene!=0x2905) if won else
                (shots==(1 if name=="held" else 3) and hits==0 and damage==6 and scene==0x2905)))
    elif skeleton or driver or ceiling:
        won=name in ("on-target","pad")
        expected_shots=1 if won or name=="held" else 3
        valid=(shots==expected_shots and hits==int(won) and misses==shots-hits
               and civilians==0 and drawn==1 and (damage<6)==won
               and (scene!=0x2905)==won
               and (not ceiling or damage==(0 if won else 6)))
    elif args.hostage:
        won=name=="on-target"
        valid=(shots>0 and hits==int(won) and damage==(0 if won else 6)
               and (name!="held" or shots==1) and misses==shots-hits
               and civilians==0 and drawn==1 and scene==(0x0603 if won else 0x2905))
    elif bathroom:
        valid=(hits=={"stunner":4,"pad":5,"idle":0}[name] and civilians==0
               and (damage==6)==(name=="idle") and drawn==int(name!="idle"))
    else:
        valid=(shots,hits,civilians,misses,drawn)==expected and (damage<6)==(name=="on-target")
    if not valid:
        raise ValueError(f"{name} failed at {work}: {(shots,hits,civilians,misses,damage,drawn)}")
    return name,dict(pad_sha256=sha(inputs),shots=shots,hits=hits,misses=misses,damage=damage,scene=hex(scene),trigger_input=gun.read_text().splitlines())

with ThreadPoolExecutor(max_workers=len(cases)) as pool:
    results = dict(pool.map(play,cases))
(out/"receipt.json").write_text(json.dumps(dict(build=bin_hash,core=sha(core),backup=sha(backup),
                                                pad=sha(pad),results=results),indent=2)+"\n")
print(out)
