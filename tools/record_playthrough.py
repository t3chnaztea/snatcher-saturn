"""Record one cold-boot Beetle Saturn input replay with its audio and build hashes."""
import argparse
from array import array
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
uncut = root.parent/"snatcher-uncut"
sonic = root.parent/"sonic-cd-saturn"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("disc",type=Path)
parser.add_argument("pad",type=Path,help="zero-based first frame, last frame, hexadecimal mask per row")
parser.add_argument("frames",type=int)
parser.add_argument("output",type=Path,help="new recording directory")
parser.add_argument("--backup", type=Path, help="Start from this internal backup RAM on cold boot")
args = parser.parse_args()
disc = args.disc.resolve()
output = args.output.resolve()
if args.frames < 1 or output.exists():
    parser.error("Supply a positive frame count and a new output directory")

def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()

def prepare_input(source, destination, frames):
    # Overlapping inclusive ranges combine the same way as a physical pad.
    masks = array("H", [0]) * frames
    for number, line in enumerate(source.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            first, last, buttons = line.split()
            first, last, buttons = int(first), int(last), int(buttons, 16)
            if not (0 <= first <= last and 0 <= buttons <= 65535):
                raise ValueError()
        except ValueError:
            raise ValueError(f"Invalid input row {number} in {source}") from None
        for frame in range(first, min(last + 1, frames)):
            masks[frame] |= buttons
    with destination.open("wb") as output:
        masks.tofile(output)


core = sonic/".deps/beetle-saturn/mednafen_saturn_libretro.dylib"
with tempfile.TemporaryDirectory(dir=output.parent,prefix=".movie-") as tmp:
    tmp = Path(tmp)
    result = tmp/"result"
    result.mkdir()
    shutil.copyfile(args.pad,result/"playthrough.pad")
    prepare_input(result/"playthrough.pad", tmp/"input.bin", args.frames)
    cflags = shlex.split(subprocess.check_output(["pkg-config","--cflags","--libs","libpng"],text=True))
    subprocess.run(["cc","-std=gnu11","-O2","-I"+str(uncut/"tools/harness"),
                    "-I"+str(sonic/".deps/beetle-saturn/libretro-common/include"),
                    root/"tools/record_core.c",*cflags,"-o",tmp/"record"],check=True)
    audio = tmp/"audio.wav"
    save = tmp/"saves"
    save.mkdir()
    env = {k:v for k,v in os.environ.items() if not k.startswith("SNATCHER_")}
    read,write = os.pipe()
    env.update(SNATCHER_PAD="generic",SNATCHER_MOVIE_INPUT=str(tmp/"input.bin"),SNATCHER_MOVIE_FD=str(write),SNATCHER_AUDIO=str(audio))
    if args.backup:
        shutil.copyfile(args.backup,result/"starting-backup.bin")
        env.update(SNATCHER_BACKUP_INPUT=str(result/"starting-backup.bin"),
                   SNATCHER_BACKUP_OUTPUT=str(tmp/"ending-backup.bin"))
    with (result/"core.log").open("w") as log, os.fdopen(read,"rb") as video:
        proc = subprocess.Popen([tmp/"record",core,sonic/"assets/private",save,disc,str(args.frames),
                                 result/"final.png","-"],stdout=subprocess.PIPE,
                                stderr=log,env=env,pass_fds=(write,),text=True)
        os.close(write)
        try:
            fps = json.loads(proc.stdout.readline())["fps"]
            subprocess.run(["ffmpeg","-nostdin","-loglevel","error","-f","rawvideo","-pix_fmt","rgb24",
                            "-video_size","330x224","-framerate",str(fps),"-i","pipe:0","-c:v","libx264rgb",
                            "-preset","ultrafast","-crf","0",tmp/"video.mkv"],stdin=video,check=True)
            run = json.loads(proc.stdout.read())
            if proc.wait() or run["frames"] != args.frames:
                raise RuntimeError("Emulator stopped before recording completed")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    movie = result/"playthrough.mkv"
    subprocess.run(["ffmpeg","-nostdin","-loglevel","error","-i",tmp/"video.mkv","-i",audio,
                    "-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","flac",movie],check=True)
    info = json.loads(subprocess.check_output(["ffprobe","-v","error","-count_packets",
                      "-show_entries","stream=codec_type,nb_read_packets,sample_rate",
                      "-of","json",movie],text=True))["streams"]
    if len(info)!=2 or info[0]["codec_type"]!="video" or int(info[0]["nb_read_packets"])!=args.frames or info[1]["codec_type"]!="audio":
        raise ValueError("Incomplete movie streams")
    (result/"receipt.json").write_text(json.dumps(dict(frames=args.frames,fps=fps,cold_boot=True,
        state_loads=0,starting_backup_sha256=sha(result/"starting-backup.bin") if args.backup else None,core_sha256=sha(core),bin_sha256=sha(disc.with_suffix(".bin")),cue_sha256=sha(disc),
        input_sha256=sha(result/"playthrough.pad"),movie_sha256=sha(movie),streams=info),indent=2)+"\n")
    result.rename(output)
print(output)
