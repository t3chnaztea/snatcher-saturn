"""Compare the three memory-chip voices and the inspection-arm sound with US disc audio."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import wave

from check_voice import capture, compare, np, resource, SOURCE
from disc_files import unpack

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("replay", type=Path, help="output of check_factory.py --chip")
parser.add_argument("--disc", type=Path, required=True)
args = parser.parse_args()
receipt = json.loads((args.replay/"receipt.json").read_text())
with args.disc.with_suffix(".bin").open("rb") as f:
    if hashlib.file_digest(f, "sha256").hexdigest() != receipt["bin_sha256"]:
        parser.error("Replay and disc hashes differ")

def window(system, start, stop, output):
    path = args.replay/system
    count = int((path/"frames.txt").read_text().splitlines()[-1].split()[0])
    with wave.open(str(path/"drive.wav")) as source:
        length = source.getnframes()
        first, end = start*length//count, stop*length//count
        source.setpos(first)
        with wave.open(str(output), "wb") as dest:
            dest.setparams(source.getparams())
            dest.writeframes(source.readframes(end-first))

def effect_score(signal, pattern):
    pattern = pattern - pattern.mean()
    width = len(pattern)
    size = 1 << (len(signal)+width-2).bit_length()
    product = np.fft.irfft(np.fft.rfft(signal,size)*np.fft.rfft(pattern[::-1],size),size)
    energy = np.r_[0.,np.cumsum(signal**2)]
    total = np.r_[0.,np.cumsum(signal)]
    variance = energy[width:]-energy[:-width]-(total[width:]-total[:-width])**2/width
    scores = product[width-1:len(signal)]/np.sqrt(np.maximum(variance,1)*(pattern@pattern))
    return round(float(scores.max()),4)

result = {}
with tempfile.TemporaryDirectory() as scratch:
    tmp = Path(scratch)
    files, _ = unpack(args.disc.resolve(),tmp/"disc")
    for system, start, end in [("retail",30400,31500),("saturn",35300,36500)]:
        clip = tmp/(system+".wav")
        window(system,start,end,clip)
        signal = capture(clip)
        voices = {}
        for cue in (141,142,143):
            info = resource(cue)
            with (SOURCE/"PCMLD_01.BIN").open("rb") as f:
                f.seek(info["sector"]*2048)
                pcm = np.frombuffer(f.read(info["sectors"]*2048).split(b"\xff",1)[0],np.uint8)
            # The Sega CD uses sign-magnitude PCM.
            ref = np.where(pcm & 128, pcm.astype(float)-128, -pcm.astype(float))
            positions = [int(max(group,key=lambda j:np.var(ref[j:j+1600]))) for group in
                         np.array_split(np.arange(0,len(ref)-1600,200),10)]
            try: voices[cue] = compare(clip,ref,.85 if system=="saturn" else .55,positions,stride=1)
            except ValueError as e: voices[cue] = {"failed":str(e)}
        effects = {i:effect_score(signal,np.frombuffer(files[f"FM{i}.BIN"],">i2").astype(float))
                   for i in (8,9,10)}
        result[system] = dict(voices=voices, effects=effects)
(args.replay/"chip-audio.json").write_text(json.dumps(result,indent=2)+"\n")
for system, checks in result.items():
    print(system, "voice failures", [k for k,v in checks["voices"].items() if "failed" in v], "effects", checks["effects"])
if any("failed" in v for checks in result.values() for v in checks["voices"].values()):
    raise SystemExit("Memory-chip dialogue differs")
if min(result["saturn"]["effects"].values()) < .85:
    raise SystemExit("Inspection-arm sound differs")
