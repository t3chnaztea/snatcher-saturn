"""Render the plaza from the verified game, then pack native timed tile changes."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
UNCUT=Path(os.environ.get("SNATCHER_UNCUT",ROOT.parent/"snatcher-uncut")).resolve()
SONIC=Path(os.environ.get("SNATCHER_SONIC",ROOT.parent/"sonic-cd-saturn")).resolve()
sys.path.insert(0,str(UNCUT/"tools"))
from scd_disc import mode1_sector

def add_retail_toc(work):
    # The source animators use the CD position. Supply the original TOC
    # during extraction. The release patcher supplies the actual audio.
    def msf(sector):
        minute,remaining=divmod(sector,4500)
        second,frame=divmod(remaining,75)
        return f"{minute:02}:{second:02}:{frame:02}"
    lines=(work/"disc.cue").read_text().splitlines()
    sectors=56014
    tracks=json.loads((ROOT/"tools/retail-audio.json").read_text())
    for number in range(2,22):
        entry=tracks[str(number)]
        lines.extend([f"  TRACK {number:02} AUDIO",f"    INDEX 00 {msf(sectors)}"])
        sectors+=entry["pregap"]
        lines.append(f"    INDEX 01 {msf(sectors)}")
        sectors+=entry["sectors"]
    with (work/"disc.bin").open("r+b") as sparse:
        sparse.truncate(sectors*2352)
    (work/"disc.cue").write_text("\n".join(lines)+"\n")


def render(work, scene, gibson=False, report=False, assisted=False, dark=False, flashlight=False, benson=False, hospital_drive=False, crash=False, stairway=False, skeleton=False, ceiling_win=False, mika_hits=None, quiz=False, departure=False, church_entry=False, performance=None):
    source=Path(os.environ.get("SNATCHER_TRACK1",UNCUT/"private/extracted/segacd-usa/_track01.raw"))
    lba=json.loads((ROOT/"tools/retail-extents.json").read_text())["SP06.BIN"]["lba"]
    with source.open("rb") as original, (work/"disc.bin").open("w+b") as copy:
        remaining=56014*2352
        while remaining:
            buf=original.read(min(1048576,remaining))
            if not buf: raise ValueError("Incomplete retail data track")
            copy.write(buf)
            remaining-=len(buf)
        copy.seek(lba*2352+16)
        payload=bytearray(copy.read(2048))
        if payload[49:62]!=bytes.fromhex("25 3d 0901 25 4a 001e 25 04 0037 25"):
            raise ValueError("Unexpected New Game initializer")
        # Ask the original VM to load A0, start its plaza controller, and wait.
        # Story scripts in the actual Saturn package come from the stock disc.
        program=bytes.fromhex("25 3d")+struct.pack(">H",scene)+bytes.fromhex("25 00 23 0022 0000 4a 7000")
        if scene==0x2200:
            block=json.loads((ROOT/"tools/retail-extents.json").read_text())["SP29.BIN"]["lba"]
            copy.seek(block*2352+16);story=copy.read(2048)
            if story[5:9]!=bytes.fromhex("25 3d 2200"): raise ValueError("Unexpected SP29 opening")
            program=story[5:0x49]+story[0x4d:0x55]
            if hospital_drive:
                program+=story[0xd2:0x168]
            program+=bytes.fromhex("4a 7000")
            if crash:
                # Join SP29's original track 11 shot routines in their call order.
                program=(bytes.fromhex("25 3d 2201 25 4a 0060")+story[0x439:0x449]+story[0x454:0x45c]
                         +story[0x460:0x4a0]+story[0x4a4:0x4b6]+bytes.fromhex("4a 7000"))
        if scene==0x0a00:
            program=bytes.fromhex("25 3d 0a00 25 4a 0096 25 00 23 0030 0000 25 45 0030 25 4a 0060 "
                "25 00 23 0032 0000 25 00 23 0030 0002 25 4a 0080 25 00 23 0030 0005 "
                "25 45 0030 25 4a 0060 25 00 23 0032 0005 25 00 23 0030 0002 4a 7000")
        if scene==0x1b05:
            block=json.loads((ROOT/"tools/retail-extents.json").read_text())["SP27.BIN"]["lba"]
            copy.seek(block*2352+16)
            story=copy.read(2048)
            if story[0x34d:0x351]!=bytes.fromhex("25 3d 1b05"):
                raise ValueError("Unexpected Napoleon reveal scene")
            program=bytes.fromhex("25 3d 1b00 25 4a 0050")+story[0x34d:0x351]
            if benson:
                # Show and hide the patient record first. Its ink palette stays
                # loaded while actor 16 fills in the name during the deduction.
                program+=(bytes.fromhex("25 4a 00c0")+story[0x38f:0x396]+bytes.fromhex("25 4a 00c0")+
                          story[0x4cb:0x4d8]+bytes.fromhex("25 4a 0050 25")+story[0x584:0x58a]+story[0x5d8:0x6b4])
            else:
                program+=story[0x355:0x3d8]
            program+=bytes.fromhex("4a 7000")
        if scene in (3,0x0100,0x0102):
            program=bytes.fromhex("25 3d")+struct.pack(">H",scene)+bytes.fromhex("4a 7000")
        if scene==0x0101:
            program=bytes.fromhex("25 3d 0100 25 4a 0078 25 00 23 0010 0000 "
                                  "25 4a 0056 25 45 0010 25 3d 0102 25 45 001f 4a 7000")
        if scene in (0x1a02,0x1a07,0x1a08):
            program=bytes.fromhex("25 3d 1a00 25 4a 003c 25 3d")+struct.pack(">H",scene)
            program+=bytes.fromhex("25 00 23 001e 0000 25 45 001e")
            if scene!=0x1a02:
                program+=bytes.fromhex("25 4a 00b4 25 00 23 0020 0000")
            program+=bytes.fromhex("4a 7000")
        if scene==0x1d04:
            program=bytes.fromhex("25 3d 1d04 25 4a 00b4 25 00 23 0010 0000 25 45 0010 "
                                  "25 3d 1d05 25 45 0010 25 4a 0080 4a 7000")
        if scene in (0x1d0a,0x1d0b,0x1d0d):
            program=bytes.fromhex("25 3d 1d04 25 00 23 0010 0000 25 45 0010 25 3d 1d05 25 45 0010 25 4a 0050 25 00 23 0023 0000 25 4a 0050 25 3d")+struct.pack(">H",scene)+bytes.fromhex("25 4a 00c0 4a 7000")
        if scene==0x1d03:
            block=json.loads((ROOT/"tools/retail-extents.json").read_text())["SP30.BIN"]["lba"]
            copy.seek((block+1)*2352+16)
            story=copy.read(2048)
            if story[0x10e:0x112]!=bytes.fromhex("25 3d 1d03"):
                raise ValueError("Unexpected SP30 return to the operating room")
            program=story[0x10e:0x126]+bytes.fromhex("25 4a 0060")+story[0x151:0x175]+bytes.fromhex("25 4a 0100 4a 7000")
        if scene==0x1d01:
            program=bytes.fromhex("25 3d 1d01 25 4a 0100 25 00 23 0010 0000 25 4a 0120 25 00 23 0011 0000 25 4a 0120 4a 7000")
        if scene==0x0a02:
            rooms=(0x0a00,0x0a03,0x0a02,0x0b00,0x0b01,0x0c00,0x0c03,0x0d00,0x0d01,0x0e01,0x0e02)
            program=b"".join(bytes.fromhex("25 3d")+struct.pack(">H",room)+bytes.fromhex("25 4a 0400")
                             for room in rooms)+bytes.fromhex("4a 7000")
        if scene==0x1602:
            # Use the original Act 3 entry after the end-of-act save.
            program=bytes.fromhex("2c 21 005d 0004")
        if scene==0x1500:
            program=bytes.fromhex("2c 21 005a 0ed4")
        if scene==0x1506:
            program=bytes.fromhex("25 3d 1506 25 4a 0100 2c 21 005a 0dbd")
        if scene==0x0a02 and assisted:
            program=bytes.fromhex("25 3d 0a02 25 4a 0060 2c 21 005a 0b5f")
        if scene in (0x1200,0x1202,0x1301):
            program=bytes.fromhex("2c 21 005a")+struct.pack(">H",{0x1200:4,0x1202:0x23b,0x1301:0x36a}[scene])
        if scene in (0x2300,0x2301):
            entry=0x0e04 if scene==0x2301 else 0x0db5 if assisted else 0x0c91
            program=bytes.fromhex("2c 21 0059")+struct.pack(">H",entry)
        if scene in (0x2401,0x2402,0x2404):
            entry={0x2401:0x068a,0x2402:0x06db,0x2404:0x08ab}[scene]
            program=bytes.fromhex("2c 21 0059")+struct.pack(">H",entry)
        if scene==0x2400:
            # Enter SP32 normally. At its first menu select the lamp routine.
            program=bytes.fromhex("2c 21 0059 0008")
            block=json.loads((ROOT/"tools/retail-extents.json").read_text())["SP32.BIN"]["lba"]
            copy.seek(block*2352+16)
            page=bytearray(copy.read(2048))
            if page[0x98:0x9a]!=bytes.fromhex("30 26"):
                raise ValueError("Unexpected SP32 dark tunnel menu")
            page[0x98:0x9c]=bytes.fromhex("30 2b 0292")
            copy.seek(block*2352)
            copy.write(mode1_sector(page,block))
        if scene==0x1f10:
            # The hospital confrontation starts at SP31 routine 02A4.
            program=bytes.fromhex("2c 21 0058 02a4")
        if scene==0x1e03:
            # Follow the retail "Reconstruct Corpse" choice into SP31.
            block=json.loads((ROOT/"tools/retail-extents.json").read_text())["SP30.BIN"]["lba"]
            copy.seek((block+1)*2352+16+0x73f)
            program=copy.read(6)
            if program!=bytes.fromhex("2c 21 0058 0004"):
                raise ValueError("Unexpected SP31 reconstruction entry")
        if scene==0x1d0c:
            program=bytes.fromhex("25 3d 1d0c 25 4a 0180 25 00 23 0011 0000 25 4a 0180 4a 7000")
        if skeleton:
            block=json.loads((ROOT/"tools/retail-extents.json").read_text())["SP30.BIN"]["lba"]
            copy.seek((block+1)*2352+16+0x61)
            attack=copy.read(11)
            if attack!=bytes.fromhex("25 00 23 001c 0000 25 45 001c"):
                raise ValueError("Unexpected SP30 skeleton attack")
            program=bytes.fromhex("25 3d 1d02 25 4a 00c0")+attack+bytes.fromhex("25 4a 0100 4a 7000")
        if stairway:
            program=program[:-3]+bytes.fromhex("25 42 23 000a 0001 25 00 23 001a 0000 25 4a 00b4 "
                "25 42 23 000a 0000 25 00 23 0015 0000 25 45 0015 25 4a 0078 "
                "25 00 23 001b 0000 25 45 001b 25 4a 0078 25 3d 1d0e 25 4a 02bc 4a 7000")
        if flashlight:
            # SP26 turns on Metal Gear's light and starts Q3 palette actor 26.
            program=program[:-3]+bytes.fromhex("25 42 23 000a 0001 25 00 23 001a 0000 25 4a 00f0 4a 7000")
        if scene in (0x1c06,0x1c07):
            block=json.loads((ROOT/"tools/retail-extents.json").read_text())["SP28.BIN"]["lba"]
            copy.seek(block*2352+16)
            story=copy.read(2048)
            if story[0x447:0x44b]!=bytes.fromhex("25 3d 1c07") or story[0x473:0x477]!=bytes.fromhex("25 3d 1c06"):
                raise ValueError("Unexpected SP28 shower sequence")
            program=bytes.fromhex("25 3d 1c05 25 4a 0050 25 04 01cf 25 46")+story[0x447:0x466]+story[0x473:0x530]
            if scene==0x1c06:
                program+=bytes.fromhex("25 4a 0050 25 00 23 0029 0000 25 4a 0002 25 00 23 0016 0002 25 4a 0050 "
                    "25 00 23 0028 0002 25 00 23 0027 0000 25 45 0027 25 4a 00f0 "
                    "25 00 23 0028 0005 25 45 0028 25 4a 0080 "
                    "25 00 23 002a 0000 25 4a 0080 25 00 23 0024 0000 25 4a 0080 "
                    "25 00 23 0023 0000 25 4a 0080 25 00 23 0021 0000 25 4a 0080 "
                    "25 00 23 0022 0000 25 4a 0080 25 00 23 002c 0000 25 4a 0080")
            program+=bytes.fromhex("4a 7000")
        if scene in (0x1c00,0x1c04):
            # SP28's city view, window light, and door controllers.
            program=bytes.fromhex("25 3d 1c00 25 4a 0078 25 3d 1c03 25 4a 0050 "
                                  "25 00 23 0015 0000 25 45 0015 25 4a 0050 "
                                  "25 00 23 0010 0000 25 45 0010 25 3d 1c04 25 4a 0050 "
                                  "25 3d 1c05 4a 7000")
        if scene==0x2101:
            # SP34 plays Mika's call from the turbocycle. Reuse the sequence
            # from the verified disc, including the voiced caller changes.
            block=json.loads((ROOT/"tools/retail-extents.json").read_text())["SP34.BIN"]["lba"]
            copy.seek(block*2352+16+0x6b)
            call=copy.read(0xb5-0x6b)
            if call[:4]!=bytes.fromhex("25 3d 2101"): raise ValueError("Unexpected SP34 call")
            program=bytes.fromhex("25 3d 2100 25 4a 003c")+call+bytes.fromhex("4a 7000")
        if scene==0x1102:
            # SP16 transfers to SP20 at root 4. Run the original film script.
            program=bytes.fromhex("2c 21 004d 0004")
        if scene==0x1600:
            program=bytes.fromhex("25 3d 1904 25 4a 0050 25 3d 1601 25 04 0037 25 46 "
                                  "25 00 23 0012 0000 25 4a 0064 25 3d 1600 25 4a 00c8 "
                                  "25 00 23 001a 0000 25 4a 0050 25 3d 1102 4a 7000")
        if scene==0x1601:
            program=bytes.fromhex("25 3d 1904 25 4a 0050 25 3d 1601 25 04 0037 25 46 "
                                  "25 00 23 0012 0000 25 4a 0064 25 3d 1600 4a 7000")
        if scene==0x0604:
            # Start from the hostage room so F4 actors and voice 53 are resident.
            program=bytes.fromhex(
                "25 3d 0601 25 4a 0050 25 3d 0602 25 4a 0014 25 04 0035 25 46 25 45 001f "
                "25 3d 0604 25 4a 0050 25 0d 0007 25 45 000f 25 3d 0605 25 45 000f "
                "25 3d 0607 25 45 000f 25 3d 0606 25 45 000f 25 3d 0608 25 45 000f "
                "25 3d 0609 25 48 25 3d 060a 25 4a 00c8 25 00 23 0015 0000 "
                "25 4a 0050 25 3d 1904 4a 7000")
        if scene==0x0602:
            program=bytes.fromhex("25 3d 0601 25 4a 0050 25 3d 0603 25 4a 0080 25 00 23 0011 0000 25 4a 0080 25 3d 0602 25 4a 0014 25 04 0035 25 46 25 45 001f 25 3d 0604 4a 7000")
        if scene==0x0600:
            program=bytes.fromhex("25 3d 0600 25 4a 0050 25 00 23 0012 0000 25 45 0012 25 4a 0050 25 3d 0601 4a 7000")
        if scene==0x050a:
            program=bytes.fromhex("25 3d 050a 25 04 0033 25 46 25 45 0008 4a 7000")
        if scene==0x0508:
            program=bytes.fromhex("25 3d 0508 25 00 23 0019 0000 25 45 0019 25 4a 0050 25 3d 0509 25 4a 0050 25 00 23 0010 0000 25 4a 00b4 25 00 23 0011 0000 25 45 0011 4a 7000")
        if scene==0x0502:
            light_command=bytes.fromhex("25 00 23 0015 0000") if dark else b""
            helper=bytes.fromhex("25 00 23 0011 0000") if assisted else b""
            resident=b"" if assisted else bytes.fromhex("25 00 23 0015 0000")
            program=(bytes.fromhex("25 3d 0502 25 4a 0050")+light_command+
                     bytes.fromhex("25 4a 0050 25 00 23 0010 0000")+helper+
                     bytes.fromhex("25 45 0010 25 4a 0040 25 3d 0504")+resident+
                     bytes.fromhex("25 45 001f 4a 7000"))
        if scene==0x1703:
            # SP14 dispatches the doorway actor and waits for actor 19.
            program=bytes.fromhex("25 3d 1703 25 45 0013 25 4a 0028 25 3d 1704 4a 7000")
        if gibson:
            # Set up the retail exterior, load voice bank 17, then run the
            # entrance actors and the two original completion waits.
            program=bytes.fromhex("25 3d 0700 25 4a 005a 25 04 0011 25 46 25 4a 0014 "
                                  "25 00 23 0010 0000 25 00 23 0011 0000 25 00 23 0012 0000 "
                                  "25 45 0010 25 3d 0704 25 45 0020 4a 7000")
        if scene==0x0702:
            # SP25 starts only Gillian at the door on his second visit.
            program=bytes.fromhex("25 3d 0702 25 4a 005a 25 04 0011 25 46 25 4a 0014 "
                                  "25 00 23 0010 0000 25 45 0010 25 3d 0705 25 45 0020 4a 7000")
        if report:
            from prepare_report import report_program
            program=report_program()
        if scene==0x1c06:
            # The isolated list sequence skips dialogue dismissals. Suppress
            # the stale Gillian mouth sprite in this extraction only.
            first=0x150ac
            lba_p=json.loads((ROOT/"tools/retail-extents.json").read_text())["DATA_P0.BIN"]["lba"]+first//2048
            copy.seek(lba_p*2352+16)
            page=bytearray(copy.read(2048))
            for index in range(3):
                off=first%2048+index*10
                if page[off:off+10]!=struct.pack(">5H",0,0,0x0d00,0x2438+8*index,0):
                    raise ValueError("Unexpected mouth sprite")
                page[off+8:off+10]=bytes.fromhex("ff00")
            copy.seek(lba_p*2352);copy.write(mode1_sector(page,lba_p))
        payload[49:49+len(program)]=program
        copy.seek(lba*2352)
        copy.write(mode1_sector(payload,lba))
    (work/"disc.cue").write_text('FILE "disc.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n')
    if scene in (0x1602,0x1500,0x1301,0x1f10,0x0604,0x1102,0x2200):
        add_retail_toc(work)
    flags=shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","libpng"],text=True))
    subprocess.run(["cc","-O2","-I"+str(UNCUT/"tools/harness"),"-I"+str(SONIC/".deps/beetle-saturn/libretro-common/include"),
                    "-I"+str(ROOT/"src"),ROOT/"tools"/("render_credits.c" if performance and performance[0]==331080 else "render_crash.c" if crash else "render_flashlight.c" if flashlight else "render_briefing.c" if scene in (0x1602,0x1500,0x1506,0x0a02,0x1200,0x1202,0x1301,0x2300,0x2301,0x2401,0x2402,0x2404,0x1f10,0x1102,0x2200) else "render_report.c" if report else "render_plaza.c"),*flags,"-o",work/"render"],check=True)
    env={k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env["SNATCHER_PAD"]="genesis3"
    if scene in (0x0508,0x050a,0x0600,0x0602,0x0604,0x1601,0x1600): env["SNATCHER_SCENE_FIRST"]="13600"
    pad=UNCUT/"tests/scenarios/early-game.pad"
    if scene in (0x1202,0x1301): env["SNATCHER_SCENE_PORTRAITS"]="1"
    if scene in (0x1200,0x1202):
        # Advance the three SP33 lines and capture the original arrival at reception.
        approach=pad.read_text()
        pad=work/"entry.pad"
        pad.write_text(approach+"\n"+"".join(f"{f} {f+2} 100\n" for f in range(14300,14846,90)))
    if scene==0x1506 or (scene==0x0a02 and assisted):
        if scene==0x1506: env["SNATCHER_SCENE_PORTRAITS"]="1"
        else: env["SNATCHER_CEILING_PATTERNS"]="1"
        approach=pad.read_text()
        pad=work/"entry.pad"
        actions=[(f,f+2,0x100) for f in range(13800,14301 if ceiling_win else 14201,90)]
        if mika_hits is not None:
            from prepare_mika import combat_input
            actions.extend(combat_input(mika_hits))
        if ceiling_win:
            env.update(SNATCHER_SCENE_PORTRAITS="1")
            # Draw and aim up on the original Sega CD after its encounter starts.
            for f in range(14334,14850,75):
                actions.append((f,f+2,2))
                for shot in range(f+8,f+73,12):
                    actions.extend([(shot,shot+3,16),(shot+4,shot+6,0x110)])
        pad.write_text(approach+"\n"+"".join(f"{a} {b} {m:x}\n" for a,b,m in actions))
    if scene==0x2300 and assisted: env["SNATCHER_TAXI_PATTERNS"]="1"
    if scene in (0x1500,0x1602): env["SNATCHER_SCENE_PORTRAITS"]="1"
    if scene==0x1102: env.update(SNATCHER_SCENE_FIRST="14350",SNATCHER_FULL_SCREEN="1")
    if scene in (0x0604,0x2402,0x2404): env["SNATCHER_SCENE_PORTRAITS"]="1"
    if scene in (3,0x0100,0x0101,0x0102): env["SNATCHER_SCENE_FIRST"]="13600"
    if scene in (0x1a02,0x1a07,0x1a08): env["SNATCHER_SCENE_FIRST"]="13600"
    if scene==0x2101: env.update(SNATCHER_SCENE_FIRST="13600",SNATCHER_SCENE_PORTRAITS="1")
    if scene==0x0502: env["SNATCHER_SCENE_FIRST"]="13650"
    if scene==0x1703: env["SNATCHER_SCENE_FIRST"]="13671"
    if scene==0x0702: env["SNATCHER_SCENE_FIRST"]="13800"
    if scene in (0x1c00,0x1c04): env["SNATCHER_SCENE_FIRST"]="13600" if scene==0x1c00 else "14220"
    if scene==0x1c06: env.update(SNATCHER_SCENE_FIRST="19800",SNATCHER_SCENE_PORTRAITS="1")
    if scene==0x1c07: env.update(SNATCHER_SCENE_FIRST="13600",SNATCHER_SCENE_PORTRAITS="1")
    if scene in (0x1602,0x1500,0x1506,0x0a02,0x1200,0x1202,0x1301,0x2300,0x2301,0x2400,0x2401,0x2402,0x2404,0x1f10,0x1e03,0x1d01,0x1d03,0x1d04,0x1d0c,0x1d0a,0x1d0b,0x1d0d): env["SNATCHER_SCENE_FIRST"]="13600"
    if scene in (0x0a00,0x1b05,0x2200): env["SNATCHER_SCENE_FIRST"]="13600"
    if gibson: env["SNATCHER_SCENE_FIRST"]="13843"
    if mika_hits is not None:
        env["SNATCHER_SCENE_FIRST"]="18485"
        if not mika_hits: env["SNATCHER_MIKA_PATTERNS"]="1"
    if quiz:
        env["SNATCHER_SCENE_FIRST"]="63800"
        pad=ROOT/"tools/act3-quiz.pad"
    if departure or church_entry or performance:
        env["SNATCHER_SCENE_FIRST"]="110300"
        pad=work/"departure.pad"
        # Acknowledge the parking lot dialogue and select the church.
        pad.write_text((ROOT/"tools/act3-quiz.pad").read_text()+
                       "".join(f"{f} {f+3} 100\n" for f in range(110012,115613,160)))
    if church_entry or performance:
        env["SNATCHER_SCENE_FIRST"]="121840"
        with pad.open("a") as controls:
            controls.write((ROOT/"tools/church-entry.pad").read_text())
            if performance:
                investigation=(ROOT/"tools/culturing-room.pad").read_text()
                if performance[0]>=167600:
                    investigation="".join(row for row in investigation.splitlines(True)
                                          if int(row.split()[0])<164275)
                    investigation+=(ROOT/"tools/final-battles.pad").read_text()
                    if performance[0]==172415:
                        investigation+="172419 172422 2\n172438 172441 100\n"
                    else:
                        env["SNATCHER_FINAL13_PATTERNS"]="1"
                if performance[0]==165501:
                    investigation+="165512 165515 100\n"
                if performance[0] >= 324800:
                    investigation += (ROOT/"tools/farewell.pad").read_text()
                controls.write(investigation)
                env["SNATCHER_SCENE_FIRST"]=str(performance[0])
                if performance[0]==152800:
                    env["SNATCHER_SWARM_PATTERNS"]="1"
    subprocess.run([work/"render",UNCUT/".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib",
                    UNCUT/"private/bios",work,work/"disc.cue",("14000" if assisted else "14761") if scene==0x2300 else str({0:19563,1:18918,3:20209}[mika_hits]) if mika_hits is not None else str(performance[1]) if performance else "139300" if church_entry else "115640" if departure else "88652" if quiz else "64100" if scene==0x1602 else "28000" if scene==0x1500 else "18485" if scene==0x1506 else "16680" if scene==0x0a02 and ceiling_win else "14200" if scene==0x0a02 and assisted else "24240" if scene==0x0a02 else "14846" if scene==0x1200 else "19635" if scene==0x1202 else "29820" if scene==0x1301 else "15890" if scene==0x2301 else "17827" if scene==0x2404 else "17500" if scene==0x2401 else "18067" if scene==0x2402 else "23404" if scene==0x2400 else "39761" if scene==0x1f10 else "26459" if scene==0x1e03 else "16100" if scene==0x1d03 else "15000" if stairway else "20300" if crash else "25600" if hospital_drive else "22500" if scene==0x2200 else "14900" if scene==0x0a00 else "25000" if scene==0x1b05 else "32416" if scene==0x1102 else "14468" if scene==0x1600 else "14158" if scene==0x1601 else "24246" if scene==0x0604 else "14800" if scene in (0x0508,0x050a,0x0600,0x0602) else "15000" if scene in (3,0x0100,0x0101,0x0102) else "14700" if scene in (0x1a02,0x1a07,0x1a08) else "16400" if scene==0x2101 else "14200" if scene==0x0502 else "13735" if scene==0x1703 else "17251" if report else "14780" if flashlight else "14450" if scene in (0x1d01,0x1d03,0x1d04,0x1d0c,0x1d0a,0x1d0b,0x1d0d) else "21620" if scene==0x1c06 else "20500" if scene==0x1c07 else "14180" if scene==0x1c00 else "14298" if scene==0x1c04 else "14100" if scene==0x0702 else "14072" if gibson else "28300",work/"end.png",
                    pad],cwd=work,env=env,check=True)

def prepare_act3_title(work, cd):
    from prepare_freddy import pack_section
    clip=pack_section((work/"frames.raw").read_bytes(),(work/"tiles.raw").read_bytes(),
                      13771,13826,13600,13826,pack_tiles,692)
    if hashlib.sha256(clip).hexdigest()!="62b4a0745dc4d3c8a79d5efc4ec0a520a26431bd9f1ce217aa7998c3b94507b2":
        raise ValueError("Unexpected Act 3 title animation")
    (cd/"ACT3IN.BIN").write_bytes(clip)
    from prepare_street import pack_street
    city=pack_street(work,14482,14683,692)
    if hashlib.sha256(city).hexdigest()!="d7d204c179338477e3f1947ea2ec9f1ed4d0fbd3275d2ccf723b0522f625e31b":
        raise ValueError("Unexpected Act 3 city pan")
    (cd/"ACT3CITY.BIN").write_bytes(city)
    for name,first,last,sha in (
        ("ACT3LAMP",14683,18299,"971bd8fac2eaec83299f75a14646668df9f8ca350bfbc5e64ee9aca2c1a3052e"),
        ("ACT3FADE",18300,18440,"1dd5e39da39f3358b969efaf60cd5ba0c2979c6bf34b68ccfd0a6a03ceca9897"),
    ):
        clip=pack_section((work/"frames.raw").read_bytes(),(work/"tiles.raw").read_bytes(),
                          first,last,13600,last,pack_tiles,692)
        if hashlib.sha256(clip).hexdigest()!=sha:
            raise ValueError(f"Unexpected Act 3 skyline animation in {name}")
        (cd/(name+".BIN")).write_bytes(clip)


def pack_scene(work,scene):
    raw=(work/"frames.raw").read_bytes()
    bank=(work/"tiles.raw").read_bytes()
    if len(raw)%768 or len(bank)%128: raise ValueError("Truncated plaza graphics")
    rows=[raw[i:i+768] for i in range(0,len(raw),768)]
    if scene==3:
        # The sign cycles every 80 frames behind Napoleon. Preserve his
        # independent gestures across sixteen sign cycles.
        rows=rows[69:69+1280]
        initial=b"".join(bank[128*k:128*(k+1)] for k, in struct.iter_unpack(">H",rows[0]))
        if len(rows)!=1280 or hashlib.sha256(initial).hexdigest()!="39526647c792a74095b3b3452979cd0e6b32d8779f9ca831843d449aeb6ecf0e":
            raise ValueError("Unexpected Santa Claus scene")
        return pack_tiles(rows,bank,0)
    if scene==0x0100:
        # Include the neon sign and its independent light cycles.
        if rows[441:462]!=rows[1305:1326]: raise ValueError("Oleen sign loop differs")
        return pack_tiles(rows[46:1306],bank,442-46)
    loop=(960,985)[scene]
    end=loop+13277
    if len(rows)<end+151 or rows[loop-1:loop+151]!=rows[end-1:end+151]:
        raise ValueError("Plaza loop continuity differs from retail")
    initial=b"".join(bank[128*k:128*(k+1)] for (k,) in struct.iter_unpack(">H",rows[0]))
    expected=("b5d83c54c84f9b3433ed8e939020688b81bf54c5402b632b8ecc0384600666b4",
              "3f2d0af2dddfe34468e641622f194342f97dd8a2d073aa1f4912231f62be4f64")
    if hashlib.sha256(initial).hexdigest()!=expected[scene]:
        raise ValueError("Unexpected initial plaza viewport")

    return pack_tiles(rows[:end],bank,loop)

def pack_tiles(rows,bank,loop,limit=0x60000,keyframes=(),cells=None):
    patterns,colors,recipes={}, {},bytearray()
    color_words=bytearray()
    for offset in range(0,len(bank),128):
        tile=struct.unpack_from(">64H",bank,offset)
        palette=tuple(dict.fromkeys(tile))
        if len(palette)>16:
            # A tile can combine sprites from several Sega CD palette banks.
            recipes.extend(struct.pack(">HH",0xffff,len(color_words)//2))
            color_words.extend(bank[offset:offset+128])
            continue
        if palette not in colors:
            colors[palette]=len(color_words)//2
            color_words.extend(struct.pack(">"+str(len(palette))+"H",*palette))
        pixels=bytes(palette.index(a)*16+palette.index(b) for a,b in zip(tile[::2],tile[1::2]))
        recipes.extend(struct.pack(">HH",patterns.setdefault(pixels,len(patterns)),colors[palette]))

    patches,steps={},[]
    previous=None
    for i,row in enumerate(rows):
        if i in keyframes: previous=None
        if row!=previous or i==loop:
            delta=b"".join(struct.pack(">H",pos//2)+row[pos:pos+2] for pos in range(0,len(row),2)
                           if (cells is None or pos//2 in cells) and (previous is None or row[pos:pos+2]!=previous[pos:pos+2]))
            if i==loop: loop_step=len(steps)
            steps.append([1,patches.setdefault(delta,len(patches))])
        else: steps[-1][0]+=1
        previous=row

    updates=bytearray()
    ranges=bytearray()
    for delta in patches:
        ranges.extend(struct.pack(">HH",len(updates)//4,len(delta)//4))
        updates.extend(delta)
    sections=(b"".join(struct.pack(">HH",*s) for s in steps),ranges,updates,recipes,
              b"".join(patterns),color_words)
    cursor=8+4*len(sections)
    offsets=[]
    for section in sections:
        offsets.append(cursor)
        cursor+=len(section)
    if cursor>limit: raise ValueError("Animation exceeds its Saturn RAM bank")
    return struct.pack(">IHH6I",cursor,len(steps),loop_step,*offsets)+b"".join(sections)

def pack_tunnel(work):
    from prepare_freddy import pack_section
    frames=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    for name,first,last,loop,digest in (
        ("TUNDARK",13700,13700,13700,"1ef86c3eaaad5dc0d4892e1949bf78bf64c7a365ae2ed24160b4f0f95a204f27"),
        ("TUNLAMP",18835,18883,18876,"85fc87788a74d266c075fa45ce76e508353f728aa276460b5502edd5b71a8d04"),
        ("TUNIDLE",19069,23404,19069,"b1ac00192ee73a1a2a52e93d3d479d1258ddb5cdaf450827869b7ee4a489a946")):
        clip=pack_section(frames,tiles,first,last,13600,loop,pack_tiles)
        if hashlib.sha256(clip).hexdigest()!=digest:
            raise ValueError(f"Unexpected SP32 graphics for {name}")
        (ROOT/"cd"/(name+".BIN")).write_bytes(clip)


def pack_reconstruction(work):
    from prepare_freddy import pack_section
    frames=(work/"frames.raw").read_bytes()
    bank=(work/"tiles.raw").read_bytes()
    # The Sega CD starts these clips at the waveform onset of voices 608..645.
    onsets=(
        13829, 14112, 14242, 14859, 14974, 15102, 16196,
        16737, 17299, 17664, 18363, 18527, 18663, 18951,
        19101, 19399, 19539, 19870, 20581, 20747, 20883,
        21190, 21338, 21637, 21779, 22116, 22855, 23023,
        23154, 23489, 23663, 23979, 24174, 24322, 24608,
        24743, 25076, 25791,
    )
    cuts=[(frame,f"QRC{cue}") for cue,frame in enumerate(onsets,608)]
    cuts.extend(zip((13774,18920,21160,23943,26134),("QRCIN3","QRCIN4","QRCIN5","QRCIN6","QRCIN7")))
    cuts.sort()
    digest=hashlib.sha256()
    for (first,name),(stop,_) in zip(cuts,cuts[1:]+[(26459,"")]):
        clip=pack_section(frames,bank,first,stop-1,13600,stop-1,pack_tiles)
        (ROOT/"cd"/(name+".BIN")).write_bytes(clip)
        digest.update(clip)
    if digest.hexdigest()!="61434a4d38d9cbc0571c2b5f300d767bc0c7185ec062a5ce95974c29ac7e4861":
        raise ValueError("Unexpected SP31 reconstruction graphics")

def pack_hospital_entry(work):
    raw=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    rows=[raw[i:i+768] for i in range(0,len(raw),768)]
    if len(rows)!=1401 or rows[441:450]!=rows[1335:1344]:
        raise ValueError("Unexpected Oleen waiting room sequence")
    # The door covers the street, which dissolves before the room is revealed.
    from prepare_freddy import pack_section
    for name,first,last,loop in (("OLEDOOR",163,267,267),("OLEIN",268,349,349),("OLEROOM",350,1335,442)):
        (ROOT/"cd"/(name+".BIN")).write_bytes(pack_section(raw,tiles,first,last,0,loop,pack_tiles,limit=0x100000 if name=="OLEDOOR" else 0x60000))

def pack_flashlight(work):
    maps=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    def picture(frame):
        cells=struct.unpack_from(">384H",maps,768*(frame-13600))
        return b"".join(tiles[c*128+y*16:c*128+y*16+16]
                        for row in range(16) for y in range(8) for c in cells[row*24:row*24+24])
    solid=list(struct.unpack(">24576H",picture(14714)))
    mask=bytes(solid[(41+y)*192+73+x]!=0x8000 for y in range(47) for x in range(47))
    if sum(mask)!=1255: raise ValueError("Unexpected retail flashlight aperture")
    source=Path(os.environ.get("SNATCHER_SOURCE",UNCUT/"private/extracted/segacd-usa"))
    sub=(source/"SUBCODE.BIN").read_bytes()
    if hashlib.sha256(sub).hexdigest()!="37d2bb27883acfedd6b05585fa5189c832bc6c94d37b3f5cf7c9a241142c88ac":
        raise ValueError("Unexpected flashlight hotspot table source")
    data=picture(14616)+picture(14620)+mask+sub[0x109e8-0xd400:0x10cb8-0xd400]
    if hashlib.sha256(data).hexdigest()!="c31e56680868eb56bc910ba5581a31cde9ab2651458c31232bbea28c3ba2ac41":
        raise ValueError("Unexpected flashlight room layers or hotspot data")
    (ROOT/"cd/QLIGHT.BIN").write_bytes(data)

def pack_queens_room(work,room,digest):
    from prepare_freddy import pack_section
    clip=pack_section((work/"frames.raw").read_bytes(),(work/"tiles.raw").read_bytes(),
                      14065,14118,13600,14118,pack_tiles)
    if hashlib.sha256(clip).hexdigest()!=digest:
        raise ValueError(f"Unexpected Queens Hospital room {room}")
    (ROOT/"cd"/f"QROOM{room}.BIN").write_bytes(clip)

def pack_queens_entry(work):
    from prepare_gibson import pack_door_clips
    middle="79bf34aa246f3564aca47b112af8188b3968cf6ed113564da60fd8be80b9a094"
    clips=[(252,418,"QDOOR.BIN","169c629f75746f85fde1b11dfcf1a5f20b201a55b70178d934b6a0bb1e1f61cf",middle),
           (417,482,"QENTRY.BIN",middle,"0a8e215aa586d7f96a4cceb4120191c3d8f3e63d605caa102b59c4526511d6c1")]
    pack_door_clips((work/"frames.raw").read_bytes(),(work/"tiles.raw").read_bytes(),clips,ROOT/"cd")

def pack_apartment(work,scene):
    from prepare_freddy import pack_section
    from prepare_gibson import pack_door_clips
    maps=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    if scene==0x1c00:
        neon=pack_section(maps,tiles,13673,13805,13600,13805,pack_tiles)
        if hashlib.sha256(neon).hexdigest()!="87caeffbfa204967d89ba3c6833d955541bfe566f2966c6d7957cb8b66db9b3f":
            raise ValueError("Unexpected apartment skyline")
        (ROOT/"cd"/"APTNEON.BIN").write_bytes(neon)
        clips=[(348,356,"APTLIGHT.BIN","8ef0ddb7a5eff414abd1e18bd05de49643b6662c41b7f94fc8de8b2ce3cc7862","8ef0ddb7a5eff414abd1e18bd05de49643b6662c41b7f94fc8de8b2ce3cc7862"),
               (466,577,"APTDOOR.BIN","8ef0ddb7a5eff414abd1e18bd05de49643b6662c41b7f94fc8de8b2ce3cc7862","d79b8c36166bf5376bbff05bac9ba00bf43097614ac30a7e16a074728e26e67a")]
    else:
        clips=[(14,79,"APTROOM.BIN","d79b8c36166bf5376bbff05bac9ba00bf43097614ac30a7e16a074728e26e67a","d6f9da7bd04ff04c0f9bddc4994e3952699baa0815d3110ce7c7f4e84a8d92cf")]
    pack_door_clips(maps,tiles,clips,ROOT/"cd")

def pack_benson(work):
    from prepare_freddy import pack_section
    raw=(work/"frames.raw").read_bytes()
    bank=(work/"tiles.raw").read_bytes()
    # Five letter entries, the two portraits, then the fade to black.
    clips=((14336,14623,14584),(14628,14748,14710),(14753,14880,14841),
           (14885,15011,14971),(15016,15650,15611),(15655,15893,15854),
           (15898,19858,19819),(19863,19912,19912))
    for i,(first,last,loop) in enumerate(clips):
        data=pack_section(raw,bank,first,last,13600,loop,pack_tiles)
        (ROOT/"cd"/f"BENSON{i}.BIN").write_bytes(data)

def pack_chase(work):
    from prepare_briefing import timed_bank
    from prepare_freddy import pack_section
    raw=(work/"frames.raw").read_bytes()
    bank=(work/"tiles.raw").read_bytes()
    clock={f:(track,lba,status) for f,track,lba,status in
           (map(int,line.split()) for line in (work/"transport.tsv").read_text().splitlines())}
    def clip(first,last):
        return pack_section(raw,bank,first,last,13600,last,pack_tiles,384,0x100000)
    (ROOT/"cd/CHASEIN.BIN").write_bytes(clip(13670,13689))
    (ROOT/"cd/CHASE10.BIN").write_bytes(timed_bank(clip,clock,10,129476,(13690,21343)))
    (ROOT/"cd/CARDEST.BIN").write_bytes(clip(21367,21368))

def pack_hospital_drive(work):
    from prepare_freddy import pack_section
    raw=(work/"frames.raw").read_bytes()
    bank=(work/"tiles.raw").read_bytes()
    # SP29 starts the engine, switches to the road, then plays voices 560–564.
    for name,first,last in (
        ("CARACCEL",21442,22441),("CARROAD",22443,22510),
        ("ROAD560",22511,22702),("ROAD561",22703,22964),("ROAD562",22965,23134),
        ("ROAD563",23135,23426),("ROAD564",23427,23559),
        ("COCKPIT",23560,23631),("CAB565",23632,23809),("CAB566",23810,24099),
        ("CAB567",24100,24352),("CAB568",24353,24620),("CAB569",24621,24900),
        ("CABIDLE",25300,25500),
    ):
        loop=first if name=="CABIDLE" else last
        clip=pack_section(raw,bank,first,last,13600,loop,pack_tiles)
        (ROOT/"cd"/(name+".BIN")).write_bytes(clip)

def pack_operating_return(work):
    from prepare_freddy import pack_section
    raw=(work/"frames.raw").read_bytes()
    bank=(work/"tiles.raw").read_bytes()
    for name,first,last,digest in (
        ("QTALK",13685,14110,"9d10d0cd00efb79031abbeb3510dd6fca76d12561044e0d8bf82690e230c6b40"),
        ("QREACH",14231,14256,"fd347a75ad9a4c3417489e261eb142125a64fe4b045b068de090fe8466aeda41"),
        ("QFALL",14383,14410,"f6ced5d6a0b93226760c224c0f85b5d980076286607d5949353efde18e118c3f"),
    ):
        clip=pack_section(raw,bank,first,last,13600,last,pack_tiles)
        if hashlib.sha256(clip).hexdigest()!=digest: raise ValueError(f"Unexpected {name} frames")
        (ROOT/"cd"/(name+".BIN")).write_bytes(clip)

def pack_basement_lab(work):
    from prepare_freddy import pack_section
    raw=(work/"frames.raw").read_bytes()
    bank=(work/"tiles.raw").read_bytes()
    for name,start,end,loop,digest in (
        ("QLAB",13672,13722,13707,"b0c7d779466266ba234cecbc39cefab4d0d44f5653e755bd40b72fa792375dd1"),
        ("QLABOUT",14054,14090,14090,"7088de1872a8979885e8396439d6cef5d98b7dc4df7aa7d4eb20ebc21f50d875"),
    ):
        clip=pack_section(raw,bank,start,end,13600,loop,pack_tiles)
        if hashlib.sha256(clip).hexdigest()!=digest: raise ValueError(f"Unexpected {name} frames")
        (ROOT/"cd"/(name+".BIN")).write_bytes(clip)

def pack_operating_head(work):
    from prepare_freddy import pack_section
    raw=(work/"frames.raw").read_bytes()
    bank=(work/"tiles.raw").read_bytes()
    clip=pack_section(raw,bank,13671,13811,13600,13811,pack_tiles)
    if hashlib.sha256(clip).hexdigest()!="7da0667d0e1d459c47916aa8198732c8a7639d53a9d911dd92669b6d6e590ac4":
        raise ValueError("Unexpected operating room head animation")
    (ROOT/"cd"/"QHEAD.BIN").write_bytes(clip)
    green=pack_section(raw,bank,13923,13997,13600,13997,pack_tiles)
    if hashlib.sha256(green).hexdigest()!="d598b52ef9c3887728912ce4373dbe71d74f6d6c591928c8f15975470f1e564a":
        raise ValueError("Unexpected fluid under the severed head")
    (ROOT/"cd"/"QGREEN.BIN").write_bytes(green)

def pack_skeleton(work):
    from prepare_gibson import pack_door_clips
    clips=[(271,302,"QATTACK.BIN",
            "0eb27bac4701758626f2d5409e2968ebd10cfa6fd6b4792580cfe0f04c21b720",
            "b986b881b435c4ad3f2ab16aadd04355cc7d9748fee90199a1dff7c9210cf229")]
    pack_door_clips((work/"frames.raw").read_bytes(),(work/"tiles.raw").read_bytes(),clips,ROOT/"cd")

def pack_stairway(work):
    from prepare_freddy import pack_section
    raw=(work/"frames.raw").read_bytes()
    bank=(work/"tiles.raw").read_bytes()
    for name,first,last,loop in (
        ("QBUTTON",14463,14538,14519),("QHATCH",14633,14728,14709),
        ("QSTAIRS",14820,14910,14855),
    ):
        clip=pack_section(raw,bank,first,last,13600,loop,pack_tiles)
        (ROOT/"cd"/(name+".BIN")).write_bytes(clip)

def pack_chief_picture(work):
    from prepare_freddy import pack_section
    raw=(work/"frames.raw").read_bytes()
    bank=(work/"tiles.raw").read_bytes()
    for name,first,last in (("CHOFFICE",13656,13656),("CHPHOTO",13803,13810),("CHFRAME",14032,14041)):
        clip=pack_section(raw,bank,first,last,13600,last,pack_tiles)
        (ROOT/"cd"/(name+".BIN")).write_bytes(clip)

def pack_napoleon(work):
    from prepare_freddy import pack_section
    raw=(work/"frames.raw").read_bytes()
    bank=(work/"tiles.raw").read_bytes()
    # SP27 starts the second pose when actor 17 receives action 2.
    for name,first,last,loop,digest in (
        ("NAPSHOW",13757,16950,16693,"ff91fb1057ccc7a2e7de10b7bbe112f8058190841d899ebab231f8e461439c03"),
        ("NAPTALK",17038,24800,24518,"d707e243b9bac0ae309826e3f41242a041fe28bdc1564c7211f90dcd71c2f486"),
    ):
        clip=pack_section(raw,bank,first,last,13600,loop,pack_tiles)
        if hashlib.sha256(clip).hexdigest()!=digest:
            raise ValueError("Unexpected Napoleon animation: "+name)
        (ROOT/"cd"/(name+".BIN")).write_bytes(clip)

def pack_call(work,scene):
    from prepare_freddy import pack_section
    raw=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    sections={
        0x1a02:(("NAPCALL",13714,13756,13740),),
        0x1a07:(("MASKON",13714,13927,13767),("MASKOFF",13954,14679,14007)),
        0x1a08:(("JAMIE",13714,14679,13767),),
    }[scene]
    for name,first,stop,loop in sections:
        a=(loop-13601)*768
        b=(stop-13601)*768
        if raw[a:a+16*768]!=raw[b:b+16*768]: raise ValueError("Caller loop differs")
        (ROOT/"cd"/(name+".BIN")).write_bytes(pack_section(raw,tiles,first,stop-1,13600,loop,pack_tiles))

def pack_jamie(work):
    from functools import partial
    from prepare_freddy import pack_section
    maps=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    # Frame positions from waveform matches against the retail voice sectors.
    groups=(("APTSHOW",13932,14535,464,(14031,14177)),
            ("APTTALK",14536,20200,467,(14660,14846,15159,15333,15626,15905,16174,
                16463,16671,16838,16970,17241,17702,17963,18079,18308,18597,19612,19809)))
    for name,first,last,cue,starts in groups:
        keys=tuple(frame-first for frame in starts)
        clip=pack_section(maps,tiles,first,last,13600,last,
                          partial(pack_tiles,keyframes=keys),692,0xa0000)
        count=struct.unpack_from(">H",clip,4)[0]
        position=0
        positions={}
        for index,(ticks,_) in enumerate(struct.iter_unpack(">HH",clip[32:32+4*count])):
            positions[position]=index
            position+=ticks
        header=struct.pack(">HH",cue,len(starts))+b"".join(struct.pack(">HH",k,positions[k]) for k in keys)
        if len(header)+len(clip)>0xa0000: raise ValueError("Apartment film exceeds low work RAM")
        (ROOT/"cd"/(name+".BIN")).write_bytes(header+clip)

def pack_hospital_list(work):
    from functools import partial
    from prepare_freddy import pack_section
    raw=(work/"frames.raw").read_bytes()
    bank=(work/"tiles.raw").read_bytes()
    maps=b"".join(raw[i:i+768] for i in range(0,len(raw),1384))
    def row(frame):
        return struct.unpack_from(">384H",maps,(frame-19800)*768)
    # The paper scrolls behind its underline. Evidence appears in independent
    # areas, so a new item must preserve any clues the player already found.
    segments=((41,20005,20081),(39,20082,20432),(40,20642,20803),
              (42,20932,20932),(36,21058,21058),(35,21185,21185),
              (33,21312,21312),(34,21439,21439),(44,21567,21615))
    for actor,first,last in segments:
        cells=None
        if actor in (39,40): cells={i for i in range(384) if i%24>=12}
        elif actor!=41:
            before=row(first-1)
            cells={i for f in range(first,last+1) for i,tile in enumerate(row(f)) if tile!=before[i]}
        if cells is not None and not cells: raise ValueError(f"Missing list actor {actor}")
        clip=pack_section(maps,bank,first,last,19800,last,partial(pack_tiles,cells=cells),limit=0x25000)
        (ROOT/"cd"/f"LIST{actor}.BIN").write_bytes(clip)

def pack_mika_call(work):
    from prepare_freddy import pack_section
    raw=(work/"frames.raw").read_bytes()
    tiles=(work/"tiles.raw").read_bytes()
    # Genesis Plus GX frame positions for the incoming picture and for
    # streamed voices 762 through 767. Each voice starts its own picture clip.
    cuts=(13722,13868,14250,14460,14721,14809,15064,16100)
    bank=bytearray(4*(len(cuts)-1))
    for i,(first,stop) in enumerate(zip(cuts,cuts[1:])):
        bank.extend(bytes((-len(bank))%4))
        struct.pack_into(">I",bank,4*i,len(bank))
        bank.extend(pack_section(raw,tiles,first,stop-1,13600,stop-1,pack_tiles,692))
    if len(bank)>0x25000: raise ValueError("Cockpit call exceeds scene RAM")
    (ROOT/"cd/MIKACALL.BIN").write_bytes(bank)

if __name__=="__main__":
    for scene,room,digest in ((0x1d0a,1,"ccf1e6a25a2b8d3359f6fffb3cb9c8eeaae04016a04545704bfbaeda0ad6fd83"),
                              (0x1d0b,2,"b5ae127a38bfc4cdd24a613de0e8d766586ac72620b1027392b37ddd30980571"),
                              (0x1d0d,3,"65c25ead241d7606a897aae9830883c0d73f6f41b81776f51e08506ff717d53a")):
        with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
            work=Path(tmp)
            render(work,scene,flashlight=room==3)
            if room==3: pack_flashlight(work)
            pack_queens_room(work,room,digest)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1d04)
        pack_queens_entry(work)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x2101)
        pack_mika_call(work)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x2200)
        pack_chase(work)
        render(work,0x2200,hospital_drive=True)
        pack_hospital_drive(work)
        from prepare_crash import pack_crash
        render(work,0x2200,crash=True)
        pack_crash(work,ROOT/"cd")
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x0a00)
        pack_chief_picture(work)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1b05)
        pack_napoleon(work)
        render(work,0x1b05,benson=True)
        pack_benson(work)
    for scene in (0x1a02,0x1a07,0x1a08):
        with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
            work=Path(tmp)
            render(work,scene)
            pack_call(work,scene)
    for scene,name in ((0,"PLAZA.BIN"),(1,"PLAZAB.BIN"),(3,"SANTA.BIN"),(0x0100,"OLEEN.BIN")):
        with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
            work=Path(tmp)
            render(work,scene)
            (ROOT/"cd"/name).write_bytes(pack_scene(work,scene))
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x0101)
        pack_hospital_entry(work)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1703)
        raw=(work/"frames.raw").read_bytes()
        if len(raw)!=65*768: raise ValueError("Incomplete Ivan doorway scene")
        rows=[raw[i:i+768] for i in range(0,len(raw),768)]
        clip=pack_tiles(rows,(work/"tiles.raw").read_bytes(),len(rows)-1)
        if hashlib.sha256(clip).hexdigest()!="366787508226ac037689a43904868bdb546909af148a0a8474fbb81c0fbd9b94":
            raise ValueError("Unexpected Ivan doorway animation")
        (ROOT/"cd"/"IVANDOOR.BIN").write_bytes(clip)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1e03)
        pack_reconstruction(work)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x2400)
        pack_tunnel(work)
    from prepare_freddy import pack_section
    for scene,name,first,last,loop,digest in (
        (0x2401,"TUNEXIT",13683,17500,13707,"dcc8a90d52bba2237c285afb036d79c83f7ec0e390cf450b3bd71208b817ce98"),
        (0x2402,"TUNWALK",13668,14150,14150,"d500e45a24faaf648d4906b6299a614e002a62a7c136a5c69b610d9bc5d026b3"),
    ):
        with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
            work=Path(tmp)
            render(work,scene)
            raw=(work/"frames.raw").read_bytes()
            tiles=(work/"tiles.raw").read_bytes()
            viewport=raw
            if scene==0x2402:
                # Retail voice onsets anchor each pair of speaking portraits to its line.
                starts=(13964,14200,14454,14674,14966,15347,15897,16513,17057,17477,17667,18067)
                combined=hashlib.sha256()
                for voice,(begin,end) in enumerate(zip(starts,starts[1:]),677):
                    shot=pack_section(raw,tiles,begin,end-1,13600,end-1,pack_tiles,692)
                    combined.update(shot)
                    (ROOT/"cd"/f"TUN{voice}.BIN").write_bytes(shot)
                if combined.hexdigest()!="c99749ba7cf4c7e5b3ca14ba199f9635042bfdc1d226d7c30ae8fac152c6de23":
                    raise ValueError("Unexpected SP32 corridor portraits")
                viewport=b"".join(raw[i:i+768] for i in range(0,len(raw),692*2))
            clip=pack_section(viewport,tiles,first,last,13600,loop,pack_tiles)
            if hashlib.sha256(clip).hexdigest()!=digest:
                raise ValueError(f"Unexpected tunnel exit graphics for {name}")
            (ROOT/"cd"/(name+".BIN")).write_bytes(clip)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x2301)
        raw=(work/"frames.raw").read_bytes()
        tiles=(work/"tiles.raw").read_bytes()
        starts=(13843,13958,14191,14913,15161,15453,15657,15853)
        cuts=[("TAXIWON",13766,13842),("TAXIOUT",15853,15890)]
        cuts.extend((f"CAB{702+i}",a,b-1) for i,(a,b) in enumerate(zip(starts,starts[1:])))
        digest=hashlib.sha256()
        for name,first,last in cuts:
            clip=pack_section(raw,tiles,first,last,13600,last,pack_tiles)
            digest.update(clip)
            (ROOT/"cd"/(name+".BIN")).write_bytes(clip)
        if digest.hexdigest()!="cafca328379bdceb415c15d2479af36ff61b4a99288760646824434fcc37f11f":
            raise ValueError("Unexpected taxi victory animation")
    for name,turn,first,last,loop,digest in (
        ("TAXIRIDE",False,13681,14761,13900,"c6829d5ae05848c7dc834dda0dc0f53a91e9a0a9330799e847dbefba6a37aac0"),
        ("TAXITURN",True,13725,13898,13896,"88b8438a0182a9e5057c41b6296a308eb3893a7e5af113af1c9c0f0451b31594"),
    ):
        with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
            work=Path(tmp)
            render(work,0x2300,assisted=turn)
            if turn:
                patterns=(work/"TFIGHT.BIN").read_bytes()
                if hashlib.sha256(patterns).hexdigest()!="c300caf189a10d6c3283602b55a35e8b9f108d7fc7562a7c96b9806ecc54c95e":
                    raise ValueError("Unexpected taxi fight patterns or colors")
                (ROOT/"cd"/"TFIGHT.BIN").write_bytes(patterns)
            clip=pack_section((work/"frames.raw").read_bytes(),(work/"tiles.raw").read_bytes(),
                              first,last,13600,loop,pack_tiles)
            if hashlib.sha256(clip).hexdigest()!=digest:
                raise ValueError(f"Unexpected taxi animation for {name}")
            (ROOT/"cd"/(name+".BIN")).write_bytes(clip)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x2404)
        raw=(work/"frames.raw").read_bytes()
        tiles=(work/"tiles.raw").read_bytes()
        cuts=[("TUNLADR",13681,13870),("TUNHIDE",14438,14475),("TUNBATH",14585,14672)]
        for first_voice,starts in (
            (690,(13871,13968,14117,14306,14438)),
            (694,(14673,15083,15284,15705,16168,16441,17145,17703,17827)),
        ):
            for voice,(first,end) in enumerate(zip(starts,starts[1:]),first_voice):
                cuts.append((f"TUN{voice}",first,end-1))
        digest=hashlib.sha256()
        for name,first,last in cuts:
            clip=pack_section(raw,tiles,first,last,13600,last,pack_tiles,692)
            digest.update(clip)
            (ROOT/"cd"/(name+".BIN")).write_bytes(clip)
        if digest.hexdigest()!="c6a966f89c43d23807bcf1f0dc106511f243756f4833a0817eea8996b923ffe6":
            raise ValueError("Unexpected SP32 ladder or bathroom graphics")
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1f10)
        from prepare_briefing import prepare_confrontation
        prepare_confrontation(work,ROOT/"cd",pack_tiles)
    from prepare_freddy import prepare
    prepare(ROOT,render,pack_tiles)
    from prepare_briefing import prepare_briefing
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1102)
        prepare_briefing(work,ROOT/"cd",pack_tiles)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1602)
        prepare_act3_title(work,ROOT/"cd")
        from prepare_act3 import prepare_room
        prepare_room(work,ROOT/"cd",pack_tiles)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1602,quiz=True)
        from prepare_act3 import prepare_quiz,prepare_track15
        prepare_quiz(work,ROOT/"cd",pack_tiles)
        prepare_track15(work,ROOT/"cd",pack_tiles)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1602,departure=True)
        from prepare_act3 import prepare_departure
        prepare_departure(work,ROOT/"cd",pack_tiles)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1602,church_entry=True)
        from prepare_act3 import prepare_church_entry
        prepare_church_entry(work,ROOT/"cd",pack_tiles)
    from prepare_act3 import CHURCH_PERFORMANCES, prepare_church_performance
    for first, last, cuts, digest in CHURCH_PERFORMANCES:
        with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
            work=Path(tmp)
            render(work,0x1602,performance=(first,last))
            prepare_church_performance(work,ROOT/"cd",pack_tiles,first,cuts,digest)
    from prepare_credits import prepare as prepare_credits
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work = Path(tmp)
        render(work, 0x1602, performance=(331080, 360500))
        prepare_credits(work, ROOT/"cd")
    from prepare_hq_return import prepare_rescue
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1500)
        prepare_rescue(work,ROOT/"cd",pack_tiles)
    from prepare_mika import prepare_mika
    prepare_mika(ROOT,render)
    from prepare_hq_return import prepare_hq_return,prepare_shutter,prepare_hall_track,prepare_hq_rooms,prepare_ceiling,prepare_ceiling_victory,prepare_lobby
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1506)
        prepare_lobby(work,ROOT/"cd",pack_tiles)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x0a02,assisted=True,ceiling_win=True)
        prepare_ceiling_victory(work,ROOT/"cd",pack_tiles)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x0a02,assisted=True)
        prepare_ceiling(work,ROOT/"cd",pack_tiles)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x0a02)
        prepare_hq_rooms(work,ROOT/"cd",pack_tiles)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1301)
        prepare_hall_track(work,ROOT/"cd",pack_tiles)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1202)
        prepare_shutter(work,ROOT/"cd",pack_tiles)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1200)
        prepare_hq_return(work,ROOT/"cd",pack_tiles)
    from prepare_street import pack_street
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1600)
        street=pack_street(work,14231,14467)
        if hashlib.sha256(street).hexdigest()!="706284a487292b493e9e2cc2dfd1d048a5240e3dc28526b1b147aa4cd1f1cb3b":
            raise ValueError("Unexpected Act 2 skyline animation")
        (ROOT/"cd"/"STREET.BIN").write_bytes(street)
    from prepare_gibson import pack_gibson
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0,gibson=True)
        pack_gibson(work,ROOT/"cd")
        render(work,0x0702)
        pack_gibson(work,ROOT/"cd",second_visit=True)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1c07)
        pack_jamie(work)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1c06)
        pack_hospital_list(work)
    for scene in (0x1c00,0x1c04):
        with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
            work=Path(tmp)
            render(work,scene)
            pack_apartment(work,scene)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1d0d,stairway=True)
        pack_stairway(work)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1d0d,skeleton=True)
        pack_skeleton(work)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1d01)
        pack_operating_head(work)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1d0c)
        pack_basement_lab(work)
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0x1d03)
        pack_operating_return(work)
    from prepare_report import pack_report
    with tempfile.TemporaryDirectory(dir=ROOT/"build") as tmp:
        work=Path(tmp)
        render(work,0,report=True)
        pack_report(work,ROOT/"cd")
