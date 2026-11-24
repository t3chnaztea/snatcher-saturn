"""Render the factory emergency effect using the player's retail sound driver."""
from array import array
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys
import tempfile
import wave

root=Path(__file__).resolve().parents[1]
uncut=Path(os.environ.get("SNATCHER_UNCUT",root.parent/"snatcher-uncut")).resolve()
sonic=Path(os.environ.get("SNATCHER_SONIC",root.parent/"sonic-cd-saturn")).resolve()
source=Path(os.environ.get("SNATCHER_TRACK1",uncut/"private/extracted/segacd-usa/_track01.raw")).resolve(strict=True)
with tempfile.TemporaryDirectory(dir=root/"build") as temp:
    work=Path(temp)
    (work/"disc.bin").symlink_to(source)
    cue=work/"disc.cue"
    cue.write_text('FILE "disc.bin" BINARY\n  TRACK 01 MODE1/2352\n    INDEX 01 00:00:00\n')
    flags=shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","libpng"],text=True))
    subprocess.run(["cc","-O2","-I"+str(uncut/"tools/harness"),"-I"+str(sonic/".deps/beetle-saturn/libretro-common/include"),
                    root/"tools/render_fm.c",*flags,"-o",work/"render"],check=True)
    env={k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    env.update(SNATCHER_PAD="genesis3",SNATCHER_AUDIO=str(work/"fx.wav"))
    playback=subprocess.run([work/"render",uncut/".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib",
                             uncut/"private/bios",work,cue,"15800",work/"end.png"],
                            env=env,stdout=subprocess.PIPE,text=True,check=True)
    starts={int(i):int(n) for i,n in re.findall(r"^FM(\d+) (\d+)$",playback.stdout,re.M)}
    scan_stop=int(re.search(r"^FM61 (\d+)$",playback.stdout,re.M)[1])
    stops=[int(n) for n in re.findall(r"^FM255 (\d+)$",playback.stdout,re.M)]
    with wave.open(str(work/"fx.wav")) as w:
        if (w.getframerate(),w.getsampwidth(),w.getnchannels())!=(44100,2,2):
            raise ValueError("Expected a 44.1 kHz stereo render")
        for id,end in ((48,starts[53]),(53,starts[2]),(26,starts[8]),(8,starts[9]),(9,starts[10]),(10,starts[21]),(21,starts[33]),(33,starts[46]),(46,starts[13]),(13,starts[42]),(42,starts[6]),(6,starts[14]),(14,starts[69]),(35,starts[61]),(59,next(n for n in stops if n>starts[59])),(5,next(n for n in stops if n>starts[5]))):
            w.setpos(starts[id])
            raw=array("h",w.readframes(end-starts[id]))
            if sys.byteorder!="little": raw.byteswap()
            left=raw[::2]
            if left!=raw[1::2] or not any(left) or any(left[-4410:]):
                raise ValueError(f"FM{id} must be a complete mono effect with a silent tail")
            while left and left[-1]==0: left.pop()
            if id in (13,14):
                # The longer effects fit the PCM staging buffer at 22.05 kHz.
                padded=array("h",[0,0])+left+array("h",[0,0])
                left=array("h",(sum(a*b for a,b in zip(padded[i:i+5],(1,4,6,4,1)))//16
                                for i in range(0,len(left),2)))
            if len(left)*2>0x4e000:
                raise ValueError(f"FM{id} exceeds the Saturn staging buffer")
            if sys.byteorder=="little": left.byteswap()
            (root/f"cd/FM{id}.BIN").write_bytes(left.tobytes())
        # Both microscope sequences stop effect 2 explicitly. Render a full
        # minute from the original driver, including its attack and modulation.
        w.setpos(starts[2])
        duration = 64*44100
        if scan_stop-starts[2] < duration: raise ValueError("Short FM2 render")
        stereo=array("h",w.readframes(duration))
        if sys.byteorder!="little": stereo.byteswap()
        mono=stereo[::2]
        if mono!=stereo[1::2] or not all(any(mono[n:n+44100]) for n in range(0,duration,44100)):
            raise ValueError("Expected a continuous mono microscope effect")
        # This low-level effect fits in resident RAM at 22.05 kHz with two
        # signed samples per byte. Filter before decimation to avoid aliasing.
        padded=array("h",[0,0])+mono+array("h",[0,0])
        packed=bytearray()
        for i in range(0,len(mono),4):
            pair=0
            for offset in (0,2):
                a,b,c,d,e=padded[i+offset:i+offset+5]
                level=round((a+4*b+6*c+4*d+e)/4096)
                if not -8<=level<=7: raise ValueError("Microscope effect exceeds resident PCM range")
                pair=(pair<<4)|(level&15)
            packed.append(pair)
        (root/"cd/FM2.BIN").write_bytes(packed)

        # Both cues end on their own. Keep the two original FM channels.
        for cue,filename in ((69,"TRAVEL69.BIN"),(70,"APT70.BIN")):
            w.setpos(starts[cue])
            samples=array("h",w.readframes(next(stop for stop in stops if stop>starts[cue])-starts[cue]))
            if sys.byteorder!="little": samples.byteswap()
            if not any(samples) or any(samples[-8820:]):
                raise ValueError(f"Incomplete FM cue {cue}")
            end=len(samples)//2
            while end and not (samples[2*end-2] or samples[2*end-1]): end-=1
            count=(end+3)//4
            if not 0<count<=0xc000: raise ValueError(f"FM cue {cue} exceeds SCSP RAM")
            with (root/"cd"/filename).open("wb") as music:
                music.write(struct.pack(">I",count).ljust(2048,b"\0"))
                for channel in (0,1):
                    data=samples[channel::2]
                    # Apply a low-pass filter before decimating to 11.025 kHz.
                    kernel=(1,8,28,56,70,56,28,8,1)
                    padded=array("h",[0]*4)+data+array("h",[0]*4)
                    pcm=array("h",(sum(v*w for v,w in zip(padded[i:i+9],kernel))//256
                                   for i in range(0,end,4)))
                    if sys.byteorder=="little": pcm.byteswap()
                    music.write(pcm.tobytes())
                    music.write(bytes((-len(pcm)*2)%2048))

        # FM80 repeats after roughly 34.18 seconds. Retain its initial attack
        # and crossfade the final 16 ms into the first sustained phrase.
        loop_start, count, fade = 3300, 380100, 176
        w.setpos(starts[80])
        frames = array("h", w.readframes(count*4))
        if sys.byteorder != "little": frames.byteswap()
        if len(frames) != count*8: raise ValueError("Incomplete farewell music")
        with (root/"cd/FM80.BIN").open("wb") as out:
            for ch in (0,1):
                samples = array("h",[0]*4) + frames[ch::2] + array("h",[0]*4)
                kernel = (1,8,28,56,70,56,28,8,1)
                pcm = array("b")
                for i in range(0,count*4,4):
                    value = sum(v*k for v,k in zip(samples[i:i+9],kernel))
                    pcm.append(max(-128,min(127,round(value/16384))))
                for i in range(fade):
                    a,b = pcm[count-fade+i], pcm[loop_start-fade+i]
                    pcm[count-fade+i] = round((a*(fade-i)+b*i)/fade)
                out.write(pcm.tobytes())
