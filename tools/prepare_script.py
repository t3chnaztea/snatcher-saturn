"""Prepare retail story expression operands and font data for the SH-2."""
import json
import hashlib
import os
from pathlib import Path
import struct
import sys

root = Path(__file__).resolve().parents[1]
uncut = Path(os.environ.get("SNATCHER_UNCUT", root.parent / "snatcher-uncut"))
source = Path(os.environ.get("SNATCHER_SOURCE", uncut / "private/extracted/segacd-usa"))
sys.path.insert(0, str(uncut / "tools"))
from scd_semantics import Decoder, dispatch, inspect
from scd_text import pool, speakers
from patch_profiles import DATE_TEXT_ROWS
from source_text_recipe import apply

def verified(name, sha256):
    data = (source / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError(f"Unexpected retail module: {name}")
    return data

def compile_story(script, table):
    decoder = Decoder(script, table)
    layout = inspect(script, decoder.table)
    if layout["errors"]:
        raise ValueError(layout["errors"])
    nodes = bytearray(8 * layout["parsed_until"])
    for node in layout["nodes"]:
        pos = node["offset"]
        expression = decoder.expression(pos)
        values = [0, 0, 0]
        modes = 0
        for arg in expression["arguments"]:
            slot = arg["slot"]
            values[slot] = arg.get("value", arg["offset"])
            if arg["kind"] == "expression":
                modes |= 1 << slot
            elif arg["mode"] == 1:
                modes |= 8 << slot
        struct.pack_into(">BB3H", nodes, pos * 8, node["opcode"] + 1, modes, *values)
    text = script[0x3800:]
    return struct.pack(">II", len(nodes), len(text)) + nodes + text


def database_text(name, data):
    expected = {"SP04.BIN": "d04dcebff3ff9e9c93977bfb28d063997cb1431a2bf93506957009a0a0e463cc",
                "SP05.BIN": "feb7c373d1254f1327f8e23b249dce7b0b61b447ed40450dc418dc81de59fe74"}
    if name not in expected:
        return data
    records, _ = pool(data)
    patched = bytearray(data)
    recipe = json.loads((uncut / "patches/text/m3.json").read_text())
    for row in recipe["rows"]:
        if row["id"] not in DATE_TEXT_ROWS:
            continue
        for edit in row["edits"]:
            if edit["file"] == name:
                record = records[edit["string_id"]]
                start, size = record["offset"], record["length"]
                patched[start:start+size] = apply(edit, data[start:start+size])
    if hashlib.sha256(patched).hexdigest() != expected[name]:
        raise ValueError(f"Database chronology differs from the accepted Uncut module: {name}")
    return patched


out = root / "build"
cd = root / "cd"
cd.mkdir(exist_ok=True)
sub = verified("SUBCODE.BIN", "37d2bb27883acfedd6b05585fa5189c832bc6c94d37b3f5cf7c9a241142c88ac")
table = dispatch(source)
manifest = json.loads((root / "tools/retail-extents.json").read_text())
for number in range(39):
    name = f"SP{number:02}.BIN"
    data = (source / name).read_bytes()
    if hashlib.sha1(data).hexdigest() != manifest[name]["sha1"]:
        raise ValueError(f"Unexpected script data: {name}")
    if os.environ.get("SNATCHER_DATABASE_DATES", "0") == "1":
        data = database_text(name, data)
    (cd / name).write_bytes(compile_story(data, table))
(out / "font.bin").write_bytes(sub[0x777c:0x777c+816+102])
names = speakers(source)
(out / "names.bin").write_bytes(b"".join(bytes.fromhex(x["raw"])[1:].ljust(24, b"\xff") for x in names))
