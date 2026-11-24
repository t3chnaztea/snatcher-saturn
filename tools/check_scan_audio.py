"""Check the forensic dialogue order and the continuous Saturn microscope sound."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import wave

from check_voice import np, resource, SOURCE, RATE
from disc_files import unpack

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("replay",type=Path,help="output of check_microscope.py")
parser.add_argument("--disc",type=Path,required=True)
args=parser.parse_args()
receipt=json.loads((args.replay/"receipt.json").read_text())
with args.disc.with_suffix(".bin").open("rb") as f:
    if hashlib.file_digest(f,"sha256").hexdigest()!=receipt["bin_sha256"]:
        parser.error("Replay and disc hashes differ")
with tempfile.TemporaryDirectory() as tmp:
    files,_=unpack(args.disc.resolve(),Path(tmp)/"disc")
    packed=np.frombuffer(files["FM2.BIN"],np.uint8)
    levels=np.stack([packed>>4,packed&15],axis=1).ravel().astype(float)
    levels[levels>=8]-=16
    fm=np.interp(np.arange(2*len(levels))/2,np.arange(len(levels)),levels*256)

def match(audio,reference):
    width=len(reference)
    size=1<<(len(audio)+width-2).bit_length()
    reference=reference-reference.mean()
    dots=np.fft.irfft(np.fft.rfft(audio,size)*np.fft.rfft(reference[::-1],size),size)[width-1:len(audio)]
    sums=np.r_[0.,np.cumsum(audio)]
    squares=np.r_[0.,np.cumsum(audio*audio)]
    variance=squares[width:]-squares[:-width]-(sums[width:]-sums[:-width])**2/width
    scores=dots/np.sqrt(np.maximum(1.,variance)*(reference@reference))
    peak=int(scores.argmax())
    return peak,float(scores[peak])

def speech(audio,cue):
    location=resource(cue)
    with (SOURCE/"PCMLD_01.BIN").open("rb") as f:
        f.seek(location["sector"]*2048)
        raw=np.frombuffer(f.read(location["sectors"]*2048).split(b"\xff",1)[0],np.uint8)
    pcm=np.where(raw&128,(raw&127).astype(float),-(raw&127).astype(float))
    quarters=np.array_split(np.arange(0,len(pcm)-3500,256),4)
    anchors=[]
    track=audio[::4]
    for positions in quarters:
        pos=int(max(positions,key=lambda n:np.var(pcm[n:n+3500])))
        ref=np.interp(np.arange(0,3500,RATE/44100),np.arange(3500),pcm[pos:pos+3500])[::4]
        i,_=match(track,ref)
        anchors.append((pos,ref,i*4/44100-pos/RATE))
    # Repeated pitches can produce a stronger peak at a different syllable.
    # Establish the onset independently with three anchors before looking for
    # all four waveforms at their source-sample offsets in the mixed audio.
    onset=float(np.median([rough for _,_,rough in anchors]))
    aligned=sum(abs(rough-onset)<.08 for _,_,rough in anchors)
    hits=[]
    for pos,ref,_ in anchors:
        guess=round((onset+pos/RATE)*44100/4)
        first=max(0,guess-220)
        last=min(len(track),guess+len(ref)+221)
        if last-first<len(ref):
            return dict(onset=onset,windows=hits,passed=False)
        i,c=match(track[first:last],ref)
        hits.append(dict(sample=pos,onset=(first+i)*4/44100-pos/RATE,correlation=c))
    times=[h["onset"] for h in hits]
    return dict(onset=float(np.median(times)),windows=hits,
                passed=aligned>=3 and max(times)-min(times)<.08 and min(h["correlation"] for h in hits)>.2)

results={}
cases = {"hair":(150,151,152,153),"skin":(154,151,155,156),"organic":(157,151,158,159,160)}
for scan in receipt["scans"]:
    cues = cases[scan]
    results[scan]={}
    for system in ["saturn","retail"]:
        with wave.open(str(args.replay/scan/system/"mix.wav")) as wav:
            if wav.getframerate()!=44100 or wav.getnchannels()!=2 or wav.getsampwidth()!=2:
                raise ValueError("Expected stereo 44.1 kHz PCM")
            frame=(16000 if scan=="organic" else 11900) if system=="saturn" else {"hair":280,"skin":480,"organic":680}[scan]
            total_frames=(20800 if scan=="organic" else 17000) if system=="saturn" else 4500
            wav.setpos(frame*wav.getnframes()//total_frames)
            audio=np.frombuffer(wav.readframes(wav.getnframes()-wav.tell()),"<i2")[::2].astype(float)
        voices=[speech(audio,cue) for cue in cues]
        ordered=all(a["onset"]<b["onset"] for a,b in zip(voices,voices[1:]))
        result=dict(voices=dict(zip(cues,voices)),ordered=ordered)
        if system=="saturn":
            end=round(voices[1]["onset"]*44100)
            i,_=match(audio[:end:2],fm[:44100:2])
            onset=i*2
            windows={}
            for seconds in ((0,2,5,10,20) if scan=="organic" else (0,2,5,10,20,30,40)):
                source=seconds*44100
                first=max(0,onset+source-300)
                ref=fm[source:source+22050:2]
                _,score=match(audio[first:onset+source+22050+300:2],ref)
                windows[seconds]=round(score,4)
            result["fm_onset_seconds"]=onset/44100
            result["fm_windows"]=windows
        results[scan][system]=result
(args.replay/"scan-audio.json").write_text(json.dumps(results,indent=2)+"\n")
for name,r in results.items():
    print(name,r["saturn"]["fm_windows"])
    if not all(s["ordered"] and all(v["passed"] for v in s["voices"].values()) for s in r.values()):
        raise SystemExit("A dialogue cue failed the source comparison")
    if min(r["saturn"]["fm_windows"].values())<.22:
        raise SystemExit("A microscope sound window fell below the comparison threshold")
