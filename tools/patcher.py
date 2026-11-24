"""Build the native Saturn prototype from a verified US retail input."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
UNCUT = ROOT.parent / "snatcher-uncut"
SONIC = ROOT.parent / "sonic-cd-saturn"
def timecode(sector):
    minute, rest = divmod(sector, 75 * 60)
    second, frame = divmod(rest, 75)
    return f"{minute:02}:{second:02}:{frame:02}"


def append_audio(result, tracks):
    """Preserve the source's stored sectors and INDEX 01 for each track."""
    from player_install import digest
    image = result / "snatcher-saturn.bin"
    cue = result / "snatcher-saturn.cue"
    sheet = cue.read_text().rstrip().splitlines()
    receipts = []
    reference = json.loads((ROOT / "tools/retail-audio.json").read_text())
    with image.open("ab") as output:
        for track in tracks:
            start = output.tell() // 2352
            stored = track.end - track.start
            stored_gap = track.indices[1] - track.start
            # Split audio files can omit INDEX 00 and PREGAP together.
            # Their playable samples still start at the retail INDEX 01.
            gap = 0 if stored_gap else reference[str(track.number)]["pregap"]
            if gap:
                output.write(bytes(gap * 2352))
            sha = hashlib.sha256()
            with track.file.open("rb") as source:
                source.seek(track.start * 2352)
                remaining = stored * 2352
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError(f"Source truncated at track {track.number}")
                    output.write(chunk)
                    sha.update(chunk)
                    remaining -= len(chunk)
            index = start + gap + track.indices[1] - track.start
            sheet.append(f"  TRACK {track.number:02} AUDIO")
            if index > start:
                sheet.append(f"    INDEX 00 {timecode(start)}")
            sheet.append(f"    INDEX 01 {timecode(index)}")
            receipts.append(dict(track=track.number, index01=index, stored_start=start+gap,
                                 stored_sectors=stored, stored_sha256=sha.hexdigest()))
            if gap:
                receipts[-1]["generated_pregap_sectors"] = gap
    for row in receipts:
        if digest(image, start=row["stored_start"]*2352,
                  length=row["stored_sectors"]*2352) != row["stored_sha256"]:
            raise ValueError(f"Output audio mismatch at track {row['track']}")
    cue.write_text("\n".join(sheet) + "\n")
    return receipts


def verify_audio(tracks):
    from player_install import digest
    manifest = json.loads((ROOT / "tools/retail-audio.json").read_text())
    for track in tracks:
        reference = manifest[str(track.number)]
        start = track.indices[1]
        sectors = track.end-start
        if sectors != reference["sectors"] or digest(track.file, start=start*2352,
                length=sectors*2352) != reference["sha256"]:
            raise ValueError(f"US retail audio checksum mismatch at track {track.number:02}")
        stored_gap = start-track.start
        if stored_gap and (stored_gap != reference["pregap"] or digest(track.file,
                start=track.start*2352, length=stored_gap*2352) != reference["pregap_sha256"]):
            raise ValueError(f"US retail pregap mismatch at track {track.number:02}")
        if track.pregap and track.pregap != reference["pregap"]:
            raise ValueError(f"US retail pregap length mismatch at track {track.number:02}")


def restore_art(first, work, extracted, registry, bar_background, lisa_art):
    from choice_install import install
    from patch_choices import SOURCE
    from disc_files import read_extent

    original = work / "track01.bin"
    remaining = SOURCE["track1_bytes"]
    with first.file.open("rb") as src, original.open("xb") as dst:
        src.seek(first.start * 2352)
        while remaining:
            chunk = src.read(min(1048576, remaining))
            if not chunk:
                raise ValueError("Truncated source track for artwork restoration")
            dst.write(chunk)
            remaining -= len(chunk)
    registry = registry or UNCUT / "build/m9/release-v1/profiles.json"
    if not registry.is_file():
        raise ValueError("Supply the Uncut v0.11.0-rc1 profiles.json with --uncut-registry")
    restored = work / "uncut-art"
    components=[]
    if bar_background:
        components.append(("DATA_O0.BIN","e3f95f273eb6128a3b0121dc110d00235326b1cc22c88c13eb204f269a8e5389"))
    if lisa_art:
        components.append(("DATA_F0.BIN","2cde7098a488559cf2ee2959f60c548ccf71a0de7c9d2da97037668bfbded306"))
    profile=f"x{(0x800 if bar_background else 0) | (0x400 if lisa_art else 0):03x}"
    receipt=install(original,None,restored,registry=registry,profile_id=profile)
    expected={"x800":"66a22a20f8fe210b4b7ac5b07b267f5a99e42828730988ac74c315692c2a3d4d",
              "x400":"bdf1c11f948c43249e36e4cead71075684faa5f7ffac461f91b1ae2cb1c518ee",
              "xc00":"355797d67929de4930e59c33e592753291efa844c1d7986dc16cd92654ff6354"}
    if receipt["target_track1_sha256"]!=expected[profile]:
        raise ValueError("Unexpected Uncut artwork track")
    extents=json.loads((ROOT/"tools/retail-extents.json").read_text())
    for filename,expected_module in components:
        row=extents[filename]
        module=read_extent(restored/original.name,row["lba"],row["size"])
        if hashlib.sha256(module).hexdigest()!=expected_module:
            raise ValueError(f"Uncut artwork verification failed for {filename}")
        (extracted/filename).write_bytes(module)


def build(source, output, database_dates=False, bar_background=False, registry=None, lisa_art=False):
    sys.path.insert(0, str(UNCUT / "tools"))
    from player_install import inspect_input, digest
    if output.exists() or output.is_symlink():
        raise ValueError(f"Choose a new output directory: {output}")
    layout = inspect_input(source)
    if layout.tracks[1:]:
        verify_audio(layout.tracks[1:])
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".snatcher-") as tmp:
        work = Path(tmp)
        extracted = work / "modules"
        extracted.mkdir()
        with layout.tracks[0].file.open("rb") as track:
            for name, row in json.loads((ROOT / "tools/retail-extents.json").read_text()).items():
                sector, size = row["lba"], row["size"]
                track.seek(sector * 2352)
                payload = bytearray()
                while len(payload) < size:
                    raw = track.read(2352)
                    if len(raw) != 2352:
                        raise ValueError(f"Truncated sector for {name}")
                    payload.extend(raw[16:2064])
                del payload[size:]
                if hashlib.sha1(payload).hexdigest() != row["sha1"]:
                    raise ValueError(f"Retail resource checksum mismatch: {name}")
                (extracted / name).write_bytes(payload)
        if bar_background or lisa_art:
            restore_art(layout.tracks[0],work,extracted,registry,bar_background,lisa_art)
        shutil.copytree(ROOT / "src", work / "src")
        shutil.copyfile(ROOT / "Makefile", work / "Makefile")
        (work / "tools").mkdir()
        for name in ("build.sh", "prepare_reception.py", "prepare_script.py", "prepare_drive.py", "prepare_fm.py", "prepare_shop.py", "prepare_club.py", "render_fm.c", "prepare_plaza.py","prepare_street.py","prepare_hq_return.py","prepare_act3.py","act3-quiz.pad","church-entry.pad","culturing-room.pad","final-battles.pad","farewell.pad","prepare_mika.py","prepare_briefing.py","render_briefing.c","render_credits.c","prepare_credits.py","prepare_prologue.py","render_crash.c","prepare_crash.py","prepare_gibson.py","prepare_freddy.py", "prepare_report.py", "render_report.c", "render_plaza.c", "render_flashlight.c", "drive-motion.z", "transit-motion.z", "hair-motion.z", "skin-motion.z", "organic-motion.z", "return0-motion.z", "return1-motion.z", "return2-motion.z", "return3-motion.z", "prepare_voice.py", "retail-extents.json", "retail-audio.json"):
            shutil.copyfile(ROOT / "tools" / name, work / "tools" / name)
        env = dict(os.environ, SNATCHER_SOURCE=str(extracted), SNATCHER_UNCUT=str(UNCUT),
                   SNATCHER_LISA_ART=str(int(lisa_art)), SNATCHER_BAR_BACKGROUND=str(int(bar_background)), SNATCHER_SONIC=str(SONIC), SNATCHER_TRACK1=str(layout.tracks[0].file.resolve()), SNATCHER_DATABASE_DATES=str(int(database_dates)))
        subprocess.run(["bash", "tools/build.sh"], cwd=work, env=env, check=True)
        result = work / "dist/bin-cue"
        data_hash = digest(result / "snatcher-saturn.bin")
        tracks = append_audio(result, layout.tracks[1:])
        hashes = {p.name: digest(p) for p in sorted(result.iterdir())}
        receipt = dict(edition="US retail", options={"database_dates": database_dates, "bar_background": bar_background}, layout=layout.kind, source_track1_sha1=
                       "1f4164205ed736a0d9a03eb7972868e9aa737d35", saturn_track1_sha256=data_hash, audio_tracks=tracks, sha256=hashes)
        if lisa_art:
            receipt["options"]["lisa_art"]=True
        (result / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        if output.exists() or output.is_symlink():
            raise ValueError("Output appeared during the build")
        result.rename(output)
    print(output / "snatcher-saturn.cue")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="US retail BIN/CUE sheet or raw Track 1 BIN")
    parser.add_argument("output", type=Path, help="new output directory")
    parser.add_argument("--database-dates", action="store_true",
                        help="restore Uncut’s database chronology in the Saturn scripts")
    parser.add_argument("--bar-background", action="store_true",
                        help="use Uncut’s Outer Heaven background with US retail patrons")
    parser.add_argument("--lisa-art", action="store_true", help="restore Uncut artwork for Lisa after the apartment fight")
    parser.add_argument("--uncut-registry", type=Path, metavar="profiles.json",
                        help="path to the Uncut component registry for artwork options")
    args = parser.parse_args()
    if args.uncut_registry and not (args.bar_background or args.lisa_art):
        parser.error("--uncut-registry applies to --bar-background or --lisa-art")
    try:
        build(args.source.absolute(), args.output.absolute(), args.database_dates, args.bar_background, args.uncut_registry, args.lisa_art)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"{exc}\n")
