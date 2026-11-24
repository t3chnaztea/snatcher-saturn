"""Compare captured retail and Saturn output with the disc's streamed voices."""
import argparse
import json
from pathlib import Path
import sys
import wave
import numpy as np

root = Path(__file__).resolve().parents[1]
uncut = root.parent / "snatcher-uncut"
sys.path.insert(0, str(uncut / "tools"))
from scd_voice import resource, RATE, SOURCE


def capture(path):
    with wave.open(str(path)) as stream:
        rate = stream.getframerate()
        if stream.getnchannels() != 2 or stream.getsampwidth() != 2 or rate != 44100:
            raise ValueError(f"Unexpected WAV format: {path}")
        signal = np.frombuffer(stream.readframes(stream.getnframes()), "<i2")
    return signal.reshape(-1, 2)[:, 0].astype(float)


def locate(recording, template):
    template = template - template.mean()
    cross = np.correlate(recording, template, "valid")
    energy = np.r_[0., np.cumsum(recording * recording)]
    width = len(template)
    total = np.r_[0., np.cumsum(recording)]
    sums = total[width:] - total[:-width]
    denom = (energy[width:] - energy[:-width] - sums*sums/width) * (template @ template)
    scores = cross / np.sqrt(np.maximum(1., denom))
    best = scores.argmax()
    return int(best), float(scores[best])


def compare(path, reference, minimum, positions, stride=8):
    audio = capture(path)
    def window(start):
        points = reference[start:start+1600]
        return np.interp(np.arange(0, len(points), RATE / 44100), np.arange(len(points)), points)
    # A repeated vowel can give a stronger single-window match in another
    # line. Try independent anchors, requiring all ten windows at one onset.
    best_checks = []
    for anchor_pos in (positions[1], positions[5], positions[8]):
        target = window(anchor_pos)
        anchor, _ = locate(audio[::stride], target[::stride])
        guess = max(0, anchor * stride - 512)
        offset, _ = locate(audio[guess:anchor*stride+512+len(target)], target)
        start = guess + offset - round(anchor_pos*44100/RATE)
        checks = []
        for pos in positions:
            center = start + round(pos*44100/RATE)
            target = window(pos)
            slack = 130
            if center < slack or center+slack+len(target) > len(audio):
                break
            lag, score = locate(audio[center-slack:center+slack+len(target)], target)
            checks.append(dict(sample=pos, correlation=score, lag=lag-slack))
        if len(checks) == len(positions):
            if all(c["correlation"] >= minimum and abs(c["lag"]) < slack for c in checks):
                return dict(onset_seconds=start/44100, checks=checks)
            if not best_checks or min(c["correlation"] for c in checks) > min(c["correlation"] for c in best_checks):
                best_checks = checks
    worst = min(best_checks, key=lambda c: c["correlation"]) if best_checks else "outside capture"
    raise ValueError(f"{path}: no complete match, weakest window {worst}")


def voiced_windows(reference):
    # A pause can fill a whole chronological interval. A silent template
    # has zero energy and cannot identify any performance.
    candidates=[int(i) for i in np.arange(0,len(reference)-1600,200)
                if np.var(reference[i:i+1600])>=1]
    if len(candidates)<10:
        raise ValueError("Voice sample has fewer than ten usable waveform windows")
    return [int(max(group,key=lambda i:np.var(reference[i:i+1600])))
            for group in np.array_split(candidates,10)]


def stereo_balance(path, result):
    # Compare the channel levels only where source waveform matches establish
    # the same speech on both systems. The median limits background music bias.
    ratios = []
    with wave.open(str(path)) as stream:
        for check in result["checks"]:
            start = round(result["onset_seconds"]*44100) + round(check["sample"]*44100/RATE) + check["lag"]
            stream.setpos(start)
            pcm = np.frombuffer(stream.readframes(round(1600*44100/RATE)), "<i2").reshape(-1, 2)
            left, right = np.std(pcm, axis=0)
            if right <= 0:
                raise ValueError(f"Silent right channel: {path}")
            ratios.append(left/right)
    return float(np.median(ratios))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saturn", type=Path, help="saturn.wav from check_reception.py")
    parser.add_argument("retail", type=Path, help="opening.wav from retail_reference.py")
    parser.add_argument("--cue", type=int, default=55)
    parser.add_argument("--stereo", action="store_true", help="Also check relative left/right level against retail")
    args = parser.parse_args()
    row = resource(args.cue)
    if row["mode"] not in (2, 0x82):
        parser.error("Choose a streamed voice cue")
    with (SOURCE / "PCMLD_01.BIN").open("rb") as src:
        src.seek(row["sector"]*2048)
        raw = src.read(row["sectors"]*2048).split(b"\xff", 1)[0]
    signmag = np.frombuffer(raw, np.uint8)
    magnitude = (signmag & 127).astype(float)
    reference = np.where(signmag & 128, magnitude, -magnitude)
    if args.cue == 55:
        positions = (100, 3000, 10000, 18000, 24000, 32500, 34000, 50000, 61000, 66000)
    else:
        # Sample voiced material in ten successive parts of the performance.
        positions = voiced_windows(reference)
    report = dict(id=args.cue, samples=len(raw), rate=RATE,
                  saturn=compare(args.saturn, reference, 0.85, positions),
                  retail=compare(args.retail, reference, 0.55, positions))
    if args.stereo:
        for name, path in (("retail", args.retail), ("saturn", args.saturn)):
            report[name]["left_to_right"] = stereo_balance(path, report[name])
        retail_ratio = report["retail"]["left_to_right"]
        saturn_ratio = report["saturn"]["left_to_right"]
        if abs(saturn_ratio / retail_ratio - 1) > 0.05:
            raise ValueError(f"Channel balance differs: Saturn {saturn_ratio:.3f}, retail {retail_ratio:.3f}")
        print(f"Left/right amplitude: Saturn {saturn_ratio:.3f}, retail {retail_ratio:.3f}")
    (args.saturn.parent / ("voice-receipt.json" if args.cue == 55 else f"voice-{args.cue}-receipt.json")).write_text(json.dumps(report, indent=2)+"\n")
    print(f"{len(raw)} source samples; ten waveform matches on each platform.")
