"""Compare two mixed-mode Saturn builds that differ only in the Lisa art setting."""
import argparse
import hashlib
import tempfile
from pathlib import Path

from disc_files import unpack
from player_install import digest


def audio_fingerprints(layout):
    return [(track.number, track.indices[1]-track.start,
             digest(track.file, start=2352*track.start, length=2352*(track.end-track.start)))
            for track in layout.tracks[1:]]


def verify(base_cue, restored_cue):
    with tempfile.TemporaryDirectory() as tmp:
        base, base_layout = unpack(base_cue, Path(tmp)/"base")
        restored, restored_layout = unpack(restored_cue, Path(tmp)/"restored")
    if base.keys()!=restored.keys():
        raise ValueError("Saturn filesystem entries differ")
    changed={name for name in base if base[name]!=restored[name]}
    if changed!={"A.BIN","DATA_F0.BIN"}:
        raise ValueError(f"Unexpected Lisa option changes: {sorted(changed)}")
    if hashlib.sha1(base["DATA_F0.BIN"]).hexdigest()!="3fc135ea71b8c27bcbcf8a4300b78348d43cbbf1":
        raise ValueError("Unexpected US retail apartment artwork")
    if hashlib.sha256(restored["DATA_F0.BIN"]).hexdigest()!="2cde7098a488559cf2ee2959f60c548ccf71a0de7c9d2da97037668bfbded306":
        raise ValueError("Unexpected Uncut apartment artwork")
    audio=audio_fingerprints(base_layout)
    if len(audio)!=20 or audio!=audio_fingerprints(restored_layout):
        raise ValueError("The audio tracks differ")
    print(f"Verified {len(base)} disc files and 20 audio tracks. Only DATA_F0.BIN and its compiled transfer data changed.")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_cue",type=Path)
    parser.add_argument("restored_cue",type=Path)
    args=parser.parse_args()
    verify(args.base_cue,args.restored_cue)
