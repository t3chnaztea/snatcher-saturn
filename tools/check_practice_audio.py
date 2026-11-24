"""Match resident effects against Sega CD and Saturn audio recordings."""
import argparse
from pathlib import Path
import struct
import wave
import numpy as np

root = Path(__file__).resolve().parents[1]
source = root.parent / "snatcher-uncut/private/extracted/segacd-usa"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("wav", type=Path, nargs="+")
parser.add_argument("--cue", action="append", type=int, choices=[13,14,15,16,22,23,32,45,46,47,48,63])
args = parser.parse_args()
table = (source/"PCMLT_01.BIN").read_bytes()
def resident_bank(bank_id):
    _, mode, _, _, sector, count = struct.unpack_from(">4B2H",table,bank_id*8)
    if mode != 1:
        raise ValueError(f"Expected resident bank {bank_id}")
    with (source/"PCMLD_01.BIN").open("rb") as f:
        f.seek(sector*2048)
        return f.read(count*2048)

def locate(signal, window):
    window = window-window.mean()
    cross = np.correlate(signal, window, "valid")
    sums = np.r_[0., np.cumsum(signal)]
    power = np.r_[0., np.cumsum(signal*signal)]
    width = len(window)
    energy = power[width:]-power[:-width]-(sums[width:]-sums[:-width])**2/width
    correlations = cross/np.sqrt(np.maximum(1.,energy)*(window@window))
    index = np.argmax(correlations)
    return int(index), float(correlations[index])

for recording in args.wav:
    with wave.open(str(recording)) as stream:
        if (stream.getsampwidth(),stream.getnchannels(),stream.getframerate()) != (2,2,44100):
            raise ValueError(f"Unsupported audio format: {recording}")
        capture = np.frombuffer(stream.readframes(stream.getnframes()),"<i2").reshape(-1,2)[:,0].astype(float)
    for sound in args.cue or range(13,17):
        bank = resident_bank({22:6,23:7,32:16,45:28,46:28,47:28,48:28,63:32}.get(sound,1))
        _, _, _, _, pitch, addr = struct.unpack_from(">4BHI",table,0x4000+16*sound)
        start = addr-0x65000+16
        pcm = np.frombuffer(bank[start:bank.index(255,start)],np.uint8).astype(float)
        pcm = np.where(pcm>=128,pcm-128,-pcm)
        rate = 16276*pitch/1024
        offsets = np.arange(512)*rate/44100
        def window(pos):
            return np.interp(pos+offsets,np.arange(len(pcm)),pcm)
        # Compare high-energy sections of the source. Hit and fire sounds
        # often overlap, which can obscure the quieter sample windows.
        positions = sorted(range(600, min(len(pcm)-400,16000), 800),
                           key=lambda pos: np.std(window(pos)), reverse=True)
        # Each hit reuses its native sound unit. Try early windows too if
        # another hit cut off the highest-energy part of this sample.
        matches = 0
        for anchor_pos in dict.fromkeys(positions[:3] + sorted(positions)[:3]):
            if not np.var(window(anchor_pos)):
                continue
            anchor, first = locate(capture,window(anchor_pos))
            if first < .8:
                continue
            scores = []
            for pos in positions:
                predicted = anchor+round((pos-anchor_pos)*44100/rate)
                if predicted < 12 or predicted+524 > len(capture):
                    continue
                if not np.var(window(pos)):
                    continue
                _, strength = locate(capture[predicted-12:predicted+524],window(pos))
                scores.append(strength)
            matches = max(matches,sum(s >= .8 for s in scores))
            if matches >= 3:
                break
        print(f"{recording}, cue {sound}: {matches}/{len(positions)} source windows")
        if matches < 3:
            raise SystemExit(f"Insufficient PCM match for effect {sound} in {recording}")
