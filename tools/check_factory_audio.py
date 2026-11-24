"""Compare factory dialogue and sound effects against the original disc audio."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import wave

from check_voice import capture, compare, np, resource, SOURCE
from disc_files import unpack

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("replay",type=Path,help="check_factory.py --interior output")
parser.add_argument("--disc",type=Path,required=True)
parser.add_argument("--gibson", action="store_true", help="check the three streamed cues after Look > Body")
args=parser.parse_args()
with args.disc.with_suffix(".bin").open("rb") as f:
    if hashlib.file_digest(f,"sha256").hexdigest()!=json.loads((args.replay/"receipt.json").read_text())["bin_sha256"]:
        parser.error("The replay was made from another BIN")
def validate_voice(id, recordings=None):
    row=resource(id)
    with (SOURCE/"PCMLD_01.BIN").open("rb") as f:
        f.seek(row["sector"]*2048)
        raw=f.read(row["sectors"]*2048).split(b"\xff",1)[0]
    codes=np.frombuffer(raw,np.uint8)
    mag=(codes&127).astype(float)
    pcm=np.where(codes&128,mag,-mag)
    positions=[int(max(group,key=lambda j:np.var(pcm[j:j+1600]))) for group in
               np.array_split(np.arange(0,len(pcm)-1600,200),10)]
    result={}
    for system,threshold in (("saturn",.85),("retail",.55)):
        try: result[system]=compare(recordings[system] if recordings else args.replay/system/"drive.wav",pcm,threshold,positions, stride=1 if recordings else 8)
        except ValueError as e: result[system]={"failed":str(e)}
    return str(id),result

if args.gibson:
    with tempfile.TemporaryDirectory() as tmp:
        recordings = {}
        for system, first_frame, end_frame in [("saturn", 31500, 32500), ("retail", 24100, 25100)]:
            recordings[system] = Path(tmp) / (system + ".wav")
            with wave.open(str(args.replay/system/"drive.wav"), "rb") as src:
                frames = int((args.replay/system/"frames.txt").read_text().splitlines()[-1].split()[0])
                src.setpos(first_frame * src.getnframes() // frames)
                with wave.open(str(recordings[system]), "wb") as dst:
                    dst.setparams(src.getparams())
                    dst.writeframes(src.readframes(end_frame * src.getnframes() // frames - src.tell()))
        cues = dict(validate_voice(i, recordings) for i in [36, 145, 144])
    (args.replay/"gibson-audio.json").write_text(json.dumps(cues, indent=2)+"\n")
    for system in ["saturn", "retail"]:
        print(system, {i:v[system].get("failed", v[system].get("onset_seconds")) for i,v in cues.items()})
    if any("failed" in cue["saturn"] for cue in cues.values()):
        raise SystemExit("Gibson audio failed the Saturn comparison")
    if any("failed" in cues[i]["retail"] for i in ["145", "144"]):
        raise SystemExit("Gibson dialogue failed the retail comparison")
    times = [cue["saturn"]["onset_seconds"] for cue in cues.values()]
    if times != sorted(times):
        raise SystemExit("Gibson cues played out of order")
    raise SystemExit(0)

with tempfile.TemporaryDirectory() as tmp:
    files,_=unpack(args.disc,Path(tmp)/"disc")
    effects={id:np.frombuffer(files[f"FM{id}.BIN"],">i2").astype(float) for id in (48,53)}

with ThreadPoolExecutor(3) as threads:
    voices=dict(threads.map(validate_voice,range(130,141)))
audio=capture(args.replay/"saturn/drive.wav")
checks={}
for id,pre,post in [(48,133,134),(53,None,137)]:
    # Bound the search to the script's sound wait. Full-length correlation
    # distinguishes the repeating tones within the same effect.
    end=round(voices[str(post)]["saturn"]["onset_seconds"]*44100)
    start=round(voices[str(pre)]["saturn"]["onset_seconds"]*44100) if pre else end-12*44100
    sample=effects[id]
    clip=audio[start:end]
    length=1<<(len(clip)+len(sample)-2).bit_length()
    cross=np.fft.irfft(np.fft.rfft(clip,length)*np.fft.rfft(sample[::-1],length),length)
    offset=int(cross[len(sample)-1:len(clip)].argmax())
    heard=clip[offset:offset+len(sample)]
    checks[str(id)]=dict(samples=len(sample),onset_seconds=(start+offset)/44100,
                         correlation=float(np.corrcoef(heard,sample)[0,1]))
receipt=dict(voices=voices,fm=checks)
(args.replay/"interior-audio.json").write_text(json.dumps(receipt,indent=2)+"\n")
for system in ("saturn","retail"):
    print(system,"voice failures",[id for id,v in voices.items() if "failed" in v[system]])
print("FM correlations",{k:round(v["correlation"],4) for k,v in checks.items()})
if any("failed" in v["saturn"] for v in voices.values()) or min(v["correlation"] for v in checks.values())<.97:
    raise SystemExit("Factory audio failed the Saturn comparison")
