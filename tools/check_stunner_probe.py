"""Check the probe's visible shot results with a Stunner on Beetle Saturn port 2."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

from PIL import Image


def run():
    root = Path(__file__).resolve().parents[1]
    sonic = Path(os.environ.get("SNATCHER_SONIC", root.parent / "sonic-cd-saturn")).resolve()
    uncut = Path(os.environ.get("SNATCHER_UNCUT", root.parent / "snatcher-uncut")).resolve()
    beetle = sonic / ".deps/beetle-saturn"
    core = beetle / "mednafen_saturn_libretro.dylib"
    disc = root / "build/stunner-probe/stunner-probe.cue"
    if not disc.is_file():
        raise SystemExit("Build the probe with bash tools/build_stunner_probe.sh")
    work = Path(tempfile.mkdtemp(prefix="stunner-probe-test-", dir=root / "build"))
    flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "libpng"], text=True))
    subprocess.run(["cc", "-O2", "-I" + str(uncut / "tools/harness"),
                    "-I" + str(beetle / "libretro-common/include"), root / "tools/lightgun_core.c",
                    *flags, "-o", work / "runner"], check=True)

    # Each row specifies the frontend aim, off-screen flag, expected field, and hold duration.
    cases = [(x, y, 0, row * 3 + col, 3) for row, y in enumerate((-18000, -6000, 6000))
             for col, x in enumerate((-12800, 0, 12800))]
    boundaries = [(-8300,-6000,3), (-4300,-6000,4), (4300,-6000,4), (8300,-6000,5),
                  (0,-14300,1), (0,-10000,4), (0,-2300,4), (0,2400,7),
                  (-24500,-6000,-1), (24500,-6000,-1), (0,-30000,-1), (0,18500,-1)]
    cases.extend((x, y, 0, field, 3) for x, y, field in boundaries)
    cases.extend([(0, -6000, 1, -1, 60), (0, -6000, 0, 4, 60)])
    frame = 2000
    events = []
    checks = []
    for shot, (x, y, offscreen, field, hold) in enumerate(cases):
        events.append(f"{frame} {frame + hold} {x} {y} {offscreen}\n")
        # The marker advances exactly once per shot, including while held.
        for check_frame in range(frame + 10, frame + max(hold + 11, 20), 10):
            checks.append((check_frame, shot, field))
        frame += (hold // 10 + 4) * 10
    (work / "gun.txt").write_text("".join(events))
    (work / "empty.pad").touch()
    env = {k: v for k, v in os.environ.items() if not k.startswith("SNATCHER_")}
    env.update(SNATCHER_GUN_INPUT=str(work / "gun.txt"), SNATCHER_PAD="generic",
               SNATCHER_CAPTURE_EVERY="10", SNATCHER_CAPTURE_PREFIX=str(work / "frame"))
    with (work / "core.log").open("w") as log:
        subprocess.run([work / "runner", core, sonic / "assets/private", work, disc, str(frame),
                        work / "end.png", work / "empty.pad"], env=env, stdout=log, stderr=log, check=True)
    results = []
    for frame, shot, field in checks:
        with Image.open(work / f"frame-{frame:06}.png") as capture:
            image = capture.convert("RGB")
        green = (0, 192, 56)
        fields = [i for i in range(9) if image.getpixel((80 + i % 3 * 64, 18 + i // 3 * 40)) == green]
        red = (248, 0, 0)
        # Beetle draws a blue gun cursor over the bitmap. Only the two
        # probe marker colors report a shot.
        markers = [(i, color) for i in range(10)
                   if (color := image.getpixel((75 + i * 18, 147))) in (red, green)]
        expected = [(shot % 10, red if field < 0 else green)]
        passed = fields == ([] if field < 0 else [field]) and markers == expected
        results.append(dict(frame=frame, shot=shot + 1, expected_field=field, fields=fields, passed=passed))
    receipt = dict(bin_sha256=hashlib.sha256(disc.with_suffix(".bin").read_bytes()).hexdigest(),
                   core_sha256=hashlib.sha256(core.read_bytes()).hexdigest(), shots=len(cases), checks=results)
    (work / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(work / "receipt.json")
    return all(row["passed"] for row in results)


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
