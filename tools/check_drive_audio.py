"""Compare a Saturn recording with a stereo CD track from the US disc."""
import argparse
import json
from pathlib import Path
import wave

import numpy as np
from check_voice import locate

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("recording", type=Path)
parser.add_argument("source_bin", type=Path, help="verified US retail single-BIN source")
parser.add_argument("--track",type=int,choices=[6,7,8,9,18,19,20],default=20)
args = parser.parse_args()
rate = 44100
index01 = {6:(19,45,39),7:(20,57,56),8:(23,44,33),9:(27,18,73),18:(43,44,66),19:(44,32,1),20:(51,34,48)}
minute,second,frame = index01[args.track]
start_sector = (minute*60+second)*75+frame
with args.source_bin.open("rb") as stream:
    stream.seek(start_sector * 2352)
    track = np.frombuffer(stream.read({6:70,7:164,8:212,9:85,18:45,19:420,20:30}[args.track] * rate * 4), "<i2").reshape(-1, 2)
with wave.open(str(args.recording)) as stream:
    if (stream.getframerate(), stream.getnchannels(), stream.getsampwidth()) != (rate, 2, 2):
        raise ValueError("Expected 44.1 kHz stereo PCM")
    recording = np.frombuffer(stream.readframes(stream.getnframes()), "<i2").reshape(-1, 2)

# Locate one anchor in the entire capture. Every subsequent stereo window
# must occur at the same relative time, including the final spoken passage.
anchor = 4 * rate
width = 4096
anchor_width = rate // 3 if args.track in (8, 9) else width
position, _ = locate(recording[::8, 0].astype(float), track[anchor:anchor+anchor_width:8, 0].astype(float))
coarse = position * 8 - anchor
begin = coarse + anchor - 128
lag, _ = locate(recording[begin:begin+anchor_width+256, 0].astype(float),
                track[anchor:anchor+anchor_width, 0].astype(float))
aligned = coarse + lag - 128
scores = []
seconds=(1,2,3,4,5,6,7,8,10,15,20,25,28) if args.track==20 else (1,2,3,4,5,6,7,8,10,12,16,20,24,28,32,36,40,44,48,52,56,60,64,68)
if args.track in (7,8,9,18,19):
    final={7:162,8:210,9:83,18:44,19:418}[args.track]
    seconds=(*range(2,final-2,4),final)
for second in seconds:
    sample = second * rate
    begin = coarse + sample - 128
    segment = recording[begin:begin+width+256]
    if begin < 0 or len(segment) != width + 256:
        raise ValueError(f"Missing audio at {second}s")
    for channel in range(2):
        source_window = track[sample:sample+width, channel]
        if not np.any(source_window):
            output = recording[aligned+sample:aligned+sample+width, channel]
            if len(output) != width or np.any(output):
                raise ValueError(f"Expected silence at {second}s on channel {channel}")
            scores.append(dict(second=second, channel=channel, silence=True, start_sample=aligned))
            continue
        lag, score = locate(segment[:, channel].astype(float), source_window.astype(float))
        scores.append(dict(second=second, channel=channel, correlation=round(score, 4),
                           start_sample=coarse+lag-128))
print(json.dumps(scores, indent=2))
if min(s["correlation"] for s in scores if "correlation" in s) < 0.8 or np.ptp([s["start_sample"] for s in scores]) > 35:
    raise SystemExit(f"Track {args.track} windows differ in content or timing")
