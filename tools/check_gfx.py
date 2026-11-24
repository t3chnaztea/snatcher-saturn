"""Check the portable graphics decoder against Uncut's retail extraction."""
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT.parent / "snatcher-uncut/private"
with tempfile.TemporaryDirectory() as tmp:
    library = Path(tmp) / "gfx.so"
    subprocess.run(["cc", "-shared", "-fPIC", "-O2", ROOT / "src/gfx.c", "-o", library], check=True)
    unpack = ctypes.CDLL(str(library)).gfx_unpack
    unpack.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    unpack.restype = ctypes.c_size_t
    blocks = 0
    modules = 0
    for manifest in sorted((PRIVATE / "work/gfx/segacd").glob("*/manifest.json")):
        record = json.loads(manifest.read_text())
        data = (PRIVATE / "extracted/segacd-usa" / record["file"]).read_bytes()
        assert hashlib.sha1(data).hexdigest() == record["sha1"], manifest
        for stream in record["streams"]:
            if stream.get("compression") != "scd-lz":
                continue
            raw = data[stream["offset"]:stream["end"]]
            capacity = stream["decoded_size"]
            dst = ctypes.create_string_buffer(capacity)
            assert unpack(raw, len(raw), dst, capacity) == len(raw), stream
            assert hashlib.sha1(dst.raw).hexdigest() == stream["sha1"], stream
            assert not unpack(raw, len(raw)-1, dst, capacity), stream
            if capacity:
                assert not unpack(raw, len(raw), dst, capacity-1), stream
            blocks += 1
        modules += 1
    if not blocks:
        raise RuntimeError("Missing Uncut graphics extraction")
    print(f"{blocks} compressed blocks verified across {modules} module manifests")
