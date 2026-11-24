"""Record two cold boots on the US retail game and compare the checkpoints."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path, algorithm="sha256"):
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def record(uncut, output):
    cue = uncut / "private/discs/segacd-usa/Snatcher.cue"
    bios = uncut / "private/bios"
    manifest = json.loads((uncut / "config/input-manifest.json").read_text())
    expected = {row["path"]: row["sha1"] for row in manifest["inputs"]}
    for path in (cue, cue.with_suffix(".bin"), bios / "bios_CD_U.bin"):
        if digest(path, "sha1") != expected[str(path.relative_to(uncut / "private"))]:
            raise ValueError(f"Retail input hash mismatch: {path.name}")
    route = output / "opening.pad"
    early = (uncut / "tests/scenarios/early-game.pad").read_text().rstrip()
    presses = [f"{i} {i+2} 100" for i in range(15030, 28000, 60)]
    route.write_text(early + "\n" + "\n".join(presses) + "\n")
    runner = uncut / "build/harness/runner"
    core = uncut / ".deps/genesis-plus-gx/genesis_plus_gx_libretro.dylib"
    environment = {k: v for k, v in os.environ.items() if not k.startswith("SNATCHER_")}
    receipts = []
    for i in (1, 2):
        run = output / f"run-{i}"
        run.mkdir()
        env = dict(environment, SNATCHER_AUDIO=str(run / "opening.wav"),
                   SNATCHER_CAPTURE_EVERY="600", SNATCHER_CAPTURE_PREFIX=str(run / "frame"),
                   SNATCHER_STOP_ON_MENU_AFTER="15000")
        with (run / "core.log").open("w") as log:
            proc = subprocess.run([runner, core, bios, run, cue, "28000", run / "menu.png",
                                   route, "-", run / "menu.state"], env=env,
                                  stdout=subprocess.PIPE, stderr=log, check=True, text=True)
        report = json.loads(proc.stdout)
        if not report["stopped_on_menu"]:
            raise ValueError(f"Investigation menu was not detected: {run}")
        report["captures"] = {p.name: digest(p) for p in sorted(run.glob("*.png"))}
        report["audio_sha256"] = digest(run / "opening.wav")
        for name, buttons in {"enter": "60 62 100", "look": "10 12 20\n60 62 100"}.items():
            pad = output / f"{name}.pad"
            pad.write_text(buttons + "\n")
            screenshot = run / f"{name}.png"
            with (run / f"{name}.log").open("w") as log:
                subprocess.run([runner, core, bios, run, cue, "300", screenshot,
                                pad, run / "menu.state"], env=environment, stdout=log,
                               stderr=subprocess.STDOUT, check=True)
            report["captures"][screenshot.name] = digest(screenshot)
        if len({report["captures"][name] for name in ("menu.png", "enter.png", "look.png")}) != 3:
            raise ValueError("Expected distinct reception branch screens")
        receipts.append(report)
    if receipts[0] != receipts[1]:
        raise ValueError(f"Retail captures differ: {output}")
    result = dict(core_sha256=digest(core), runner_sha256=digest(runner),
                  route_sha256=digest(route), cold_boot_runs=2, result=receipts[0])
    (output / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    print(output, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uncut", type=Path, default=ROOT.parent / "snatcher-uncut")
    args = parser.parse_args()
    (ROOT / "build").mkdir(exist_ok=True)
    record(args.uncut.resolve(), Path(tempfile.mkdtemp(prefix="retail-", dir=ROOT / "build")))
