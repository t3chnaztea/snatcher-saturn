"""Compile reception transfer and sprite lists from the verified retail module."""
import hashlib
import json
import os
from pathlib import Path
import sys
import struct

ROOT = Path(__file__).resolve().parents[1]
UNCUT = Path(os.environ.get("SNATCHER_UNCUT", ROOT.parent / "snatcher-uncut"))
sys.path.insert(0, str(UNCUT / "tools"))
import scd_gfx as gfx

source = Path(os.environ.get("SNATCHER_SOURCE", UNCUT / "private/extracted/segacd-usa"))
out = ROOT / "build"
out.mkdir(exist_ok=True)
cd = ROOT / "cd"
cd.mkdir(exist_ok=True)
manifest = json.loads((ROOT / "tools/retail-extents.json").read_text())

def array(declaration, rows):
    return declaration + " = {\n" + "".join(
        "    {" + ", ".join(map(str, row)) + "},\n" for row in rows) + "};\n"

def sprite_rows(objects):
    return [(s["x"], s["y"], s["width"], s["height"], s["tile"])
            for obj in reversed(objects.values()) for s in obj["sprites"]]

def compile_animation(data, commands, objects, object_id):
    obj = objects[object_id]
    script = obj["script"]
    # Start after the initial pause and its displayed frame. Stop at the
    # animation's own signal to the story interpreter.
    if data[script] != 0x93 or data[script+4] >= 128:
        raise ValueError("Expected a paused sprite animation")
    steps, headers = [], []
    affected = list(obj["sprites"])
    for pc in range(script+8, len(data)-3, 4):
        op, arg, high, low = data[pc:pc+4]
        if op == 0x98:
            break
        if op == 0x9d:  # FM sound effect is not yet synthesized.
            continue
        if op >= 128 and op != 0x97:
            raise ValueError(f"Unsupported animation instruction {op:#x}")
        visible = objects.copy()
        if op == 0x97:
            del visible[object_id]
        else:
            # Decode this frame using the same sprite table as the initializer.
            frame_data = bytearray(data)
            frame_data[script:script+4] = bytes((op, 0, 0, 0))
            frame = next(o for o in gfx.sprite_frames(frame_data, commands)
                         if o["object"] == object_id)
            visible[object_id] = frame
            affected.extend(frame["sprites"])
        rows = sprite_rows(visible)
        name = f"motion_{object_id}_{pc}"
        headers.append(array(f"static const struct sprite {name}[]", rows))
        steps.append((name, len(rows), max(1, high*256+low)))
    else:
        raise ValueError("Animation has no script completion signal")
    bounds = (max(0, min(s["x"] for s in affected)), max(0, min(s["y"] for s in affected)),
              min(256, max(s["x"]+8*s["width"] for s in affected)),
              min(224, max(s["y"]+8*s["height"] for s in affected)))
    headers.append(array("static const struct motion_step door_steps[]", steps))
    headers.append("static const struct motion door = {" + ", ".join(map(str,
                   (object_id, *bounds, "door_steps", len(steps), 0))) + "};\n")
    return "".join(headers)

def triggered_frames(data, commands, objects, actor, start, symbol, extra=()):
    obj = objects[actor]
    script = obj["script"]
    steps, headers = [], []
    pc = script+start
    while data[pc] < 128:
        frame, mode, hi, lo = data[pc:pc+4]
        if mode or not (hi or lo):
            raise ValueError(f"Unexpected {symbol} frame")
        patched = bytearray(data)
        patched[script:script+4] = bytes((frame,0,hi,lo))
        part = next(o for o in gfx.sprite_frames(patched,commands) if o["object"] == actor)
        parts = dict(sorted({**dict(extra), actor:part}.items()))
        name = f"{symbol}_{len(steps)}"
        rows = sprite_rows(parts)
        headers.append(array(f"static const struct sprite {name}[]",rows))
        steps.append((name,len(rows),hi*256+lo))
        pc += 4
    if data[pc] != 0x98:
        raise ValueError(f"Missing {symbol} completion signal")
    return "".join(headers)+array(f"static const struct motion_step {symbol}[]",steps)

def compile_loop(data, commands, objects, tag, animated, frame_count, loop_start=0):
    steps, headers = [], []
    affected = []
    for pos in range(0, frame_count*4, 4):
        updated = objects.copy()
        frame_data = bytearray(data)
        delays = []
        for object_id in animated:
            obj = objects[object_id]
            start = obj["script"]
            op, mode, hi, lo = data[start+pos:start+pos+4]
            if op >= 128 or mode or data[start+frame_count*4:start+(frame_count+1)*4] != bytes((0x81, loop_start, 0, 0)):
                raise ValueError("Unexpected sprite loop")
            frame_data[start:start+4] = bytes((op, 0, hi, lo))
            delays.append(hi*256+lo)
        if len(set(delays)) != 1 or not delays[0]:
            raise ValueError("Invalid sprite loop delays")
        for obj in gfx.sprite_frames(frame_data, commands):
            if obj["object"] in animated:
                if tag == "0f00":
                    # Overlapping pieces of Metal Gear's head use SAT list priority.
                    obj["sprites"].reverse()
                updated[obj["object"]] = obj
                affected.extend(obj["sprites"])
        rows = sprite_rows(updated)
        name = f"walk_{tag}_{pos}"
        headers.append(array(f"static const struct sprite {name}[]", rows))
        steps.append((name, len(rows), delays[0]))
    left = min(s["x"] for s in affected)
    top = min(s["y"] for s in affected)
    right = max(s["x"]+8*s["width"] for s in affected)
    bottom = max(s["y"]+8*s["height"] for s in affected)
    headers.append(array(f"static const struct motion_step walk_steps_{tag}[]", steps))
    headers.append(f"static const struct motion walk_{tag} = {{0, {left}, {top}, {right}, {bottom}, walk_steps_{tag}, {frame_count}, {loop_start}}};\n")
    return "".join(headers)

def compile_palette_cycles(data, commands, transfers, objects, tag):
    # Map visible palette indices to pixels once. Sprites can obscure a
    # cycling background tile, so compose them before collecting offsets.
    tiles = bytearray(65536)
    for address, offset, _ in transfers:
        decoded, _ = gfx.decode(data, offset+2, gfx.u16(data, offset))
        tiles[address:address+len(decoded)] = decoded
    indices = [(i, i, i) for i in range(64)]
    image = gfx.draw_sprites(gfx.compose(tiles, indices), tiles, indices, list(objects.values()))
    pixels = image.getchannel("R").tobytes()
    headers, cycles = [], []
    for cmd in commands:
        start = cmd["body"]
        if cmd["op"] != 0 or data[start] != 6:
            continue
        index = data[start+2]//2
        if data[start+3] or gfx.u16(data, start+cmd["length"]-2) != 0xffff:
            raise ValueError("Expected single-color palette animation")
        positions = [i for i, color in enumerate(pixels) if color == index]
        colors = []
        for p in range(start+4, start+cmd["length"]-2, 4):
            word = gfx.u16(data, gfx.u32(data, p)-gfx.BASE)
            r, g, b = (((word >> shift) & 7)*255//7*31//255 for shift in (1,5,9))
            colors.append(0x8000 | b<<10 | g<<5 | r)
        if not colors or (not positions and tag not in ("070b","070c","070d")):
            raise ValueError("Empty visible palette animation")
        name = f"cycle_{tag}_{index}"
        for suffix, values in [("pixels", positions), ("colors", colors)]:
            headers.append(f"static const uint16_t {name}_{suffix}[] = {{" +
                           ", ".join(map(hex, values)) + "};\n")
        if tag in ("070b","070c","070d") and index!=31:
            raise ValueError("Unexpected garden lights palette index")
        cycles.append((name+"_pixels", len(positions), name+"_colors", len(colors), data[start+1]+1))
    headers.append(array("static const struct palette_cycle cycles_"+tag+"[]", cycles))
    return "".join(headers), len(cycles)


def compile_scene(command, module, program):
    data = (source / module).read_bytes()
    expected_sha1=manifest[module]["sha1"]
    if module=="DATA_F0.BIN" and os.environ.get("SNATCHER_LISA_ART")=="1":
        expected_sha1="1c5a5b79dea056a4b763ac7b60e27506759ccd95"
    if module=="DATA_O0.BIN" and os.environ.get("SNATCHER_BAR_BACKGROUND")=="1":
        expected_sha1="dd00a9e6444f4d94bbbc5a83681d3a3127b8a24d"
    if hashlib.sha1(data).hexdigest() != expected_sha1:
        raise ValueError(f"Unexpected retail module: {module}")
    (cd / module).write_bytes(data)
    seqs = gfx.sequences(data)
    selected = [seqs[0]] if not program else [seqs[0], seqs[program]]
    if command in (0x0c01,0x0c02,0x0c05):
        # Jordan opens a sprite-only terminal. H04 program zero is the
        # physical computer room and its tilemaps are cleared on entry.
        selected=[seqs[program]]
    streams, errors = gfx.resources(data, selected)
    if errors: raise ValueError(errors)
    transfers, objects, colors = [], {}, None
    for seq in selected:
        batch = [(r["vram"], st["offset"], st["end"] - st["offset"])
                 for st in streams for r in st["references"] if r["sequence"] == seq["index"]]
        if any(addr in (0xc000, 0xe000) for addr, _, _ in batch):
            transfers = [t for t in transfers if not (0xc000 <= t[0] < 0xd000 or 0xe000 <= t[0] < 0xf000)]
            objects.clear()
        transfers.extend(batch)
        colors, _ = gfx.palette(data, seq["commands"], colors)
        objects.update((o["object"], o) for o in gfx.sprite_frames(data, seq["commands"]))
    dispatch = ""
    if command in (0x1e00,0x1e01,0x1e02):
        from prepare_club import actors
        cast=(16,17,18) if program==0 else (16,18 if program==1 else 17,*range(19,28))
        dispatch+=actors(data,selected[-1]["commands"],objects,f"morgue{program}",gfx,array,sprite_rows,cast)
    if command in (0x1b02,0x1b03,0x1b04):
        from prepare_club import actors
        dispatch+=actors(data,selected[-1]["commands"],objects,program,gfx,array,sprite_rows)
    if command==0x0503:
        actor=objects[19]
        dispatch+=array("static const struct sprite hotel_map[]",sprite_rows({19:actor}))
        pc=actor["script"]
        transfer=pc+gfx.u16(data,pc+10)
        map_colors,_=gfx.palette(data,[dict(op=0,body=transfer,offset=transfer,length=10)],colors)
        packed=[0x8000|(b*31//255<<10)|(g*31//255<<5)|(r*31//255) for r,g,b in map_colors]
        dispatch+="static const uint16_t hotel_map_palette[]={"+", ".join(map(hex,packed))+"};\n"
    if command==0x0500:
        dispatch+=array("static const struct sprite hotel_cars[]",sprite_rows({i:objects[i] for i in (17,18)}))
        from prepare_club import actors
        dispatch+=actors(data,selected[-1]["commands"],objects,"freddy",gfx,array,sprite_rows,(16,19))
    if command==0x1d02:
        dispatch+=array("static const struct sprite operating_skeleton[]",sprite_rows({18:objects[18]}))
        commands=selected[-1]["commands"]
        for actor,velocity in ((19,-128),(20,128)):
            record=next(p for c in commands if c["op"]==2 for p in range(c["body"],c["body"]+c["length"],12) if data[p]==actor)
            pc=record+12+struct.unpack_from(">h",data,record+10)[0]
            if data[pc+8:pc+24]!=struct.pack(">BBh",0x8e,1,velocity)+bytes.fromhex("97000030 8e010000 98000000"):
                raise ValueError("Unexpected operating room camera movement")
        dispatch+="enum { operating_pan_pixels=24 };\n"
    if command==0x0505:
        for actor in (16,17):
            dispatch+=array(f"static const struct sprite bathroom_{actor}[]",sprite_rows({actor:objects[actor]}))
        cmd=selected[-1]["commands"]
        record=next(p for c in cmd if c["op"]==2 for p in range(c["body"],c["body"]+c["length"],12) if data[p]==18)
        pc=record+12+int.from_bytes(data[record+10:record+12],"big",signed=True)
        if data[pc+8:pc+24]!=bytes.fromhex("8e01ff80 97000040 8e010000 98000000"):
            raise ValueError("Unexpected bathroom camera movement")
        dispatch+=f"enum {{ bathroom_pan_ticks={gfx.u16(data,pc+14)} }};\n"
    if command==0x0502:
        door=sprite_rows({22:objects[22]})
        dispatch+=array("static const struct sprite freddy_door[]",door)
        controller=next(p for cmd in selected[-1]["commands"] if cmd["op"]==2
                        for p in range(cmd["body"],cmd["body"]+cmd["length"],12) if data[p]==21)
        pc=controller+12+int.from_bytes(data[controller+10:controller+12],"big",signed=True)
        event=pc+gfx.u16(data,pc+2)
        grey,_=gfx.palette(data,[dict(op=0,body=event,offset=event,length=10)],colors)
        palette=[0x8000 | ((b*31//255)<<10) | ((g*31//255)<<5) | (r*31//255) for r,g,b in grey]
        dispatch+="static const uint16_t freddy_palette[]={"+", ".join(map(hex,palette))+"};\n"
        hand=objects[19]
        pc=hand["script"]
        if data[pc:pc+12]!=bytes.fromhex("00000011 9f130000 93000000"):
            raise ValueError("Unexpected Room 202 knock program")
        dispatch+=array("static const struct sprite freddy_knock[]",sprite_rows({19:hand}))
        dispatch+=f"enum {{ freddy_knock_delay={gfx.u16(data,pc+2)} }};\n"
    if command in (0x1704,0x1705,0x1706):
        from prepare_club import actors
        ids={4:(16,17,18,19),5:(16,),6:tuple(range(16,24))}[program]
        dispatch+=actors(data,selected[-1]["commands"],objects,f"ivan{program}",gfx,array,sprite_rows,ids)
    if command==0x1702:
        cmd=selected[-1]["commands"]
        pc=objects[25]["script"]
        event=pc+gfx.u16(data,pc+2)
        grey,_=gfx.palette(data,[dict(op=0,body=event,offset=event,length=10)],colors)
        vals=[0x8000 | ((b*31//255)<<10) | ((g*31//255)<<5) | (r*31//255) for r,g,b in grey]
        dispatch+="static const uint16_t ivan_palette[]={"+", ".join(map(hex,vals))+"};\n"
        rec=next(p for c in cmd if c["op"]==2 for p in range(c["body"],c["body"]+c["length"],12) if data[p]==28)
        pc=rec+12+int.from_bytes(data[rec+10:rec+12],"big",signed=True)
        opcodes=[data[pc+n] for n in range(0,20,4)]
        if opcodes!=[0x9c,0x97,0x9f,0x97,0x98] or data[pc+9]!=19:
            raise ValueError("Unexpected Room 301 knock program")
        dispatch+=f"enum {{ knock_before={gfx.u16(data,pc+6)}, knock_after={gfx.u16(data,pc+14)} }};\n"
    if command in (0x0500,0x1700,0x1701,0x1b02):
        from prepare_club import room_lights, actors
        if command==0x1700:
            dispatch+=actors(data,selected[-1]["commands"],objects,"ivan",gfx,array,sprite_rows,(16,))
        tiles=bytearray(65536)
        for address,offset,_ in transfers:
            raw,_=gfx.decode(data,offset+2,gfx.u16(data,offset))
            tiles[address:address+len(raw)]=raw
        pal=[0x8000 | ((b*31//255)<<10) | ((g*31//255)<<5) | (r*31//255) for r,g,b in colors]
        name,controller={0x0500:("FREDPAL.BIN",None),0x1b02:("CLUBPAL.BIN",27)}.get(command,("IVANPAL.BIN",18))
        (cd/name).write_bytes(room_lights(data,selected[-1]["commands"],controller,tiles,pal,gfx))
    if command == 0x0c01:
        for actor in (4,48,49):
            rows=sprite_rows({actor:objects[actor]})
            dispatch+=array(f"static const struct sprite jordan_result_{actor}[]",rows)
        pc=objects[48]["script"]
        off=pc+gfx.u16(data,pc+6)
        pal,_=gfx.palette(data,[dict(op=0,body=off,offset=off,length=10)],colors)
        values=[0x8000 | ((b*31//255)<<10) | ((g*31//255)<<5) | (r*31//255) for r,g,b in pal]
        dispatch+="static const uint16_t jordan_result_palette[]={"+", ".join(map(hex,values))+"};\n"
        rows=[]
        for actor in range(32,43):
            part=objects[actor]
            pc=part["script"]
            if data[pc]!=0x88: raise ValueError("Missing Jordan portrait palette")
            offset=pc+gfx.u16(data,pc+2)
            if data[offset:offset+4]!=bytes.fromhex("0100600f"):
                raise ValueError("Unexpected portrait color bank")
            palette,_=gfx.palette(data,[dict(op=0,body=offset,offset=offset,length=10)],colors)
            pal=[0x8000 | ((b*31//255)<<10) | ((g*31//255)<<5) | (r*31//255) for r,g,b in palette]
            name=f"jordan_{actor}"
            dispatch+=f"static const uint16_t {name}_palette[] = {{"+", ".join(map(hex,pal))+"};\n"
            tiles=sprite_rows({actor:part})
            dispatch+=array(f"static const struct sprite {name}_tiles[]",tiles)
            rows.append((name+"_tiles",len(tiles),name+"_palette"))
        dispatch+=array("static const struct jordan_portrait jordan_portraits[]",rows)
    if command == 0x0c02:
        from prepare_club import montage
        dispatch+=montage(data,objects,array,sprite_rows)
        dispatch+=array("static const struct sprite montage_cursor[]",sprite_rows({31:objects[31]}))
        dispatch+=array("static const struct sprite montage_scan[]",sprite_rows({61:objects[61]}))
        controller=next(p for cmd in selected[-1]["commands"] if cmd["op"]==2
                        for p in range(cmd["body"],cmd["body"]+cmd["length"],12) if data[p]==28)
        pc=controller+12+int.from_bytes(data[controller+10:controller+12],"big",signed=True)
        event=pc+gfx.u16(data,pc+6)
        offset=gfx.u32(data,event+2)-gfx.BASE
        if data[pc+4]!=0x8a or gfx.u16(data,event+6)!=0xc800 or gfx.u16(data,offset)!=2048:
            raise ValueError("Unexpected montage tilemap")
        _,end=gfx.decode(data,offset+2,2048)
        transfers.append((0xc800,offset,end-offset))
    if command == 0x0c05:
        from prepare_club import actors
        dispatch+=actors(data,selected[-1]["commands"],objects,program,gfx,array,sprite_rows,(32,33,34,35))
    if command == 0x1801:
        from prepare_shop import shopfront
        vram=bytearray(65536)
        for address,offset,_ in transfers:
            raw,_=gfx.decode(data,offset+2,gfx.u16(data,offset))
            vram[address:address+len(raw)]=raw
        (cd/"SHOPFX.BIN").write_bytes(shopfront(data,selected[-1]["commands"],objects,vram,gfx))
    if command == 0x1802:
        cmds=selected[-1]["commands"]
        controller=next(p for cmd in cmds if cmd["op"]==2
                        for p in range(cmd["body"],cmd["body"]+cmd["length"],12) if data[p]==37)
        pc=controller+12+int.from_bytes(data[controller+10:controller+12],"big",signed=True)
        if data[pc+4]!=0x88: raise ValueError("Missing Plato shop palette")
        palette=pc+gfx.u16(data,pc+6)
        colors,_=gfx.palette(data,[dict(op=0,body=palette,offset=palette,length=10)],colors)
        for actor in (32,33):
            dispatch+=array(f"static const struct sprite shop_mask_{actor}[]",sprite_rows({actor:objects[actor]}))
    if command == 0x1908:
        cmds = selected[-1]["commands"]
        frames = []
        # These two lights change only a handful of pixels over the wreck.
        # Compile their transparent pixels out of the SH-2 drawing loop.
        from PIL import Image
        vram = bytearray(65536)
        for address,offset,_ in transfers:
            raw,_ = gfx.decode(data,offset+2,gfx.u16(data,offset))
            vram[address:address+len(raw)] = raw
        light_frames = []
        for number in range(18):
            actor = 16 if number < 3 else 20 if number == 3 else 17 if number < 8 else 18 if number < 13 else 19
            pc = objects[actor]["script"]
            patched = bytearray(data)
            patched[pc:pc+4] = bytes((number, 0, 0, 1))
            part = next(o for o in gfx.sprite_frames(patched, cmds) if o["object"] == actor)
            rows = sprite_rows({actor: part})
            name = f"john_pose_{number}"
            dispatch += array(f"static const struct sprite {name}[]", rows)
            frames.append((name, len(rows), 0))
            if number >= 8:
                indices = [(i,i,i) for i in range(64)]
                layer = gfx.draw_sprites(Image.new("RGB",(256,136),(255,255,255)),vram,indices,[part])
                dots = [(i, v) for i,v in enumerate(layer.getchannel("R").get_flattened_data()) if v != 255]
                symbol = f"john_light_{number}"
                dispatch += array(f"static const struct light_pixel {symbol}[]", dots)
                light_frames.append((symbol,len(dots)))
        dispatch += array("static const struct light_frame john_lights[]", light_frames)
        dispatch += array("static const struct motion_step john_poses[]", frames)
        # Object 16 moves the inspection arm from its off-screen position.
        pc = objects[16]["script"]
        steps = []
        vx = vy = effect = 0
        for offset in range(pc+4, pc+68, 4):
            op, arg, hi, lo = data[offset:offset+4]
            value = int.from_bytes(data[offset+2:offset+4], "big", signed=True)
            if op == 0x86: vx = value
            elif op == 0x87: vy = value
            elif op == 0x9d: effect = arg
            elif op == 0x98: break
            elif op < 3 and arg == 0:
                steps.append((op, hi*256+lo, vx, vy, effect))
                effect = 0
            else: raise ValueError("Unexpected Little John inspection-arm command")
        if op != 0x98 or not steps: raise ValueError("Missing inspection-arm completion")
        dispatch += array("static const struct arm_step john_arm[]", steps)
        objects = {}
    if command == 0x0f03:
        cmds = selected[-1]["commands"]
        # The second palette command addresses the fade buffer at byte 0x80.
        colors,_ = gfx.palette(data,[c for c in cmds if c["op"] == 0 and data[c["body"]+2] < 128])
        controller = next(p for c in cmds if c["op"] == 2
                          for p in range(c["body"],c["body"]+c["length"],12) if data[p] == 21)
        start = controller+12+int.from_bytes(data[controller+10:controller+12],"big",signed=True)
        from PIL import ImageChops
        from struct import pack
        tiles = bytearray(65536)
        for address,offset,_ in transfers:
            raw,_ = gfx.decode(data,offset+2,gfx.u16(data,offset))
            tiles[address:address+len(raw)] = raw
        def phone_picture():
            return gfx.draw_sprites(gfx.compose(tiles,colors),tiles,colors,list(objects.values()))
        previous = phone_picture()
        pixels = bytearray()
        maps = []
        for pc in range(start,len(data)-3,4):
            if data[pc] == 0x80: break
            if data[pc] != 0x8a: continue
            event = start+gfx.u16(data,pc+2)
            offset = gfx.u32(data,event+2)-gfx.BASE
            addr = gfx.u16(data,event+6)
            size = gfx.u16(data,event+10)
            if addr != 0xe000 or gfx.u16(data,offset) != size or data[pc+4] != 0x97:
                raise ValueError("Invalid videophone tile transfer")
            raw,_ = gfx.decode(data,offset+2,size)
            tiles[addr:addr+size] = raw
            current = phone_picture()
            box = ImageChops.difference(current,previous).getbbox()
            left,top,right,bottom = box or (0,0,0,0)
            maps.append((len(pixels)//2,left,top,right-left,bottom-top,gfx.u16(data,pc+6)))
            if box:
                for r,g,b in current.crop(box).get_flattened_data():
                    pixels.extend(pack(">H",0x8000 | r*31//255 | (g*31//255)<<5 | (b*31//255)<<10))
            previous = current
        if not maps: raise ValueError("Missing videophone transition")
        if len(pixels)>0x20000: raise ValueError("Phone frames exceed the scene buffer")
        (cd/"PHONE.BIN").write_bytes(pixels)
        dispatch += f"enum {{ phone_bytes = {len(pixels)} }};\n"
        dispatch += array("static const struct map_step phone_connection[]",maps)
    if command == 0x0f00:
        cmds = selected[-1]["commands"]
        head = bytearray(data)
        pc = objects[16]["script"]
        head[pc:pc+4] = data[pc+12:pc+16]
        resting = next(o for o in gfx.sprite_frames(head,cmds) if o["object"] == 16)
        dispatch += triggered_frames(data,cmds,objects,17,0,"antenna",((16,resting),))
    if command == 0x2000:
        dispatch += triggered_frames(data,selected[-1]["commands"],objects,16,8,"canopy")
    scroll = 0
    if module == "DATA_D2.BIN":
        # The title's SAT chain on a fresh backup selects only NEW GAME.
        title = objects[16]
        if command in (0xd201,0xd202):
            frame_data=bytearray(data)
            pc=title["script"]
            frame_data[pc:pc+4]=bytes((command-0xd201,0,0,1))
            title=next(o for o in gfx.sprite_frames(frame_data,selected[-1]["commands"]) if o["object"]==16)
        objects = {16:title}
    if command == 0x800:
        # Object 16 pauses on a hidden frame (0x97) before its palette effect.
        objects = {i: o for i, o in objects.items() if data[o["script"]+4] != 0x97}
    if command in (0x900, 0x902):
        objects = {i: o for i, o in objects.items() if not data[o["record"]+1] & 2}
    factory_entrance = command in (0x1900,0x1901)
    if command==0xa01 or factory_entrance:
        # The room initializer contains two non-display objects. One fades in
        # the room palette. The other positions the background for the office.
        controls = {}
        for cmd in selected[-1]["commands"]:
            if cmd["op"] == 2:
                for offset in range(cmd["body"], cmd["body"] + cmd["length"], 12):
                    controls[data[offset]] = offset+12+int.from_bytes(data[offset+10:offset+12], "big", signed=True)
        pal_script = controls[16] if factory_entrance else controls[15]
        scroll_script = controls[16] if factory_entrance else controls[25]
        transfer = pal_script + (8 if factory_entrance else 4)
        if data[transfer] != 0x88 or data[scroll_script:scroll_script+2] != bytes((0x8d, 1)):
            raise ValueError("Missing room initialization commands")
        event = pal_script + gfx.u16(data, transfer+2)
        start, length = data[event+2]//2, data[event+3]+1
        ptr = gfx.u32(data, event+4)-gfx.BASE
        for i in range(length):
            word = gfx.u16(data, ptr+2*i)
            colors[start+i] = tuple(((word >> bit) & 7)*255//7 for bit in (1,5,9))
        scroll = -int.from_bytes(data[scroll_script+2:scroll_script+4], "big", signed=True)
        # The chief sits at the desk after the introductory voice exchange.
        objects = {18: objects[18]} if command==0xa01 else {}
    # Active sprites on Mika's first tour of each room.
    tour_objects = {0x0500: (), 0x0502: (), 0x0503: (21,), 0x0504: (), 0x0505: (), 0x0506: (), 0x0507: (), 0x050b: (), 0x0601: (31,), 0x0603: (), 0x0700: (), 0x0701: (), 0x0704: (23,25,34), 0x0706: (23,25,34),
                    0x1e00: (19,20,21,22), 0x1e01: (), 0x1e02: (),
                    0x1d02: (), 0x1d04: (19,20,21), 0x1d05: (), 0x1d07: (), 0x1d08: (), 0x1d06: (19,20,21),
                    0x1c01: (23,), 0x1c03: (), 0x1c04: (23,), 0x1c05: (), 0x0702: (), 0x0703: (), 0x0705: (34,), 0x0707: (34,),
                    0x0709: (16,17,19,20,21,22,23), 0x070a: (), 0x070c: (16,17,18), 0x0708: tuple(range(16,22)), 0x070b: (), 0x070d: (), 0x0b00: (27,), 0x0b02: (16, 18, 27), 0x0c01: (16,17,18,19,20,21,22,24,25,26,27,31), 0x0c02: (16,24,25,26,27), 0x0c00: (), 0x0c04: (17, 18), 0x0c05: (16,17,18,19,20,21,22,24,25,26,27,31),
                    0x0d00: (), 0x0e00: (*range(32, 41), 56, 57), 0x0e01: (16, 18, 19),
                    0x0f02: (19, 21, 25, 26), 0x0f04: (17,18,21,26), 0x2000: (), 0x2001: (), 0x2003: (), 0x2100: (), 0x2102: (), 0x1800: (17,18,20,21,22,23,24,25), 0x1801: (17,18,20,21,22,23,24,25),
                    0x1700: (), 0x1701: (), 0x1702: (), 0x1704: (), 0x1705: (), 0x1706: (), 0x1707: (), 0x1708: (), 0x1802: (34,35,36), 0x1b00: (16,), 0x1b01: (16,), 0x1b02: (),
                    0x1b03: (18,), 0x1b04: (18,), 0x1905: (16,17), 0x1907: (), 0x1909: (), 0x1906: (16,17,19), 0x2905: ()}
    if command == 0x0f01:
        flash = objects.pop(16)
    if command == 0x0f02:
        walker = objects[31]
    if command==0x1909:
        cmds = selected[-1]["commands"]
        pc = objects[16]["script"]
        steps = []
        dispatch_shadow = ""
        sound = 0
        for offset in range(pc+4,pc+128,4):
            op,mode,hi,lo = data[offset:offset+4]
            if op==0x98: break
            if op==0x9f:
                sound=mode
                continue
            if mode or (op>=14 and op!=0x97): raise ValueError("Unknown doorway shadow animation")
            name="NULL"
            rows=[]
            if op!=0x97:
                frame=bytearray(data)
                frame[pc:pc+4]=bytes((op,0,0,1))
                actor=next(o for o in gfx.sprite_frames(frame,cmds) if o["object"]==16)
                name=f"shadow_pose_{offset}"
                rows=sprite_rows({16:actor})
                dispatch_shadow+=array(f"static const struct sprite {name}[]",rows)
            steps.append((name,len(rows),hi*256+lo,sound))
            sound=0
        if op!=0x98: raise ValueError("Missing shadow completion signal")
        dispatch+=dispatch_shadow+array("static const struct shadow_step shadow_steps[]",steps)
    if command==0x1907:
        drip=objects[16]
    if command == 0x0b00:
        figures = []
        for name, ids in (("harry", (22,24)), ("bottle", (25,)), ("bench", (29,)), ("hands", (31,))):
            rows = sprite_rows({i: objects[i] for i in ids})
            symbol = f"engineering_{name}"
            dispatch += array(f"static const struct sprite {symbol}[]", rows)
            figures.append((symbol,len(rows),0))
        dispatch += array("static const struct motion_step engineering_figures[]", figures)
    if command == 0x0d00:
        tour = sprite_rows({i: objects[i] for i in (16, 18)})
        dispatch += array("static const struct sprite detective_tour[]", tour)
        # The locker and drawer each use three actors: open, close, and hold.
        capsule = objects[21]
        pc = capsule["script"]
        if data[pc:pc+5] != bytes.fromhex("04000000 9d"):
            raise ValueError("Unexpected capsule inspection program")
        dispatch += array("static const struct sprite capsule_picture[]", sprite_rows({21: capsule}))
        dispatch += f"enum {{ capsule_effect = {data[pc+5]} }};\n"
        # The first four frames of the retail fixture table are the two
        # locker poses followed by the two drawer poses.
        poses = []
        for actor in (22, 24, 25, 27):
            obj = objects[actor]
            rows = sprite_rows({actor: obj})
            name = f"fixture_pose_{actor}"
            dispatch += array(f"static const struct sprite {name}[]", rows)
            poses.append((name, len(rows), 0))
        dispatch += array("static const struct motion_step fixture_poses[]", poses)
        programs = []
        for actor in range(22, 28):
            pc = objects[actor]["script"]
            steps = []
            for op, arg, value in struct.iter_unpack(">BBH", data[pc:pc+32]):
                if op not in (0, 1, 2, 3, 0x80, 0x81, 0x98, 0x9d):
                    raise ValueError("Unknown Detective's Room fixture instruction")
                steps.append((op, arg, value))
                if op in (0x80, 0x81):
                    break
            else:
                raise ValueError("Unterminated Detective's Room fixture")
            name = f"fixture_program_{actor}"
            dispatch += array(f"static const struct fixture_step {name}[]", steps)
            programs.append(name)
        dispatch += "static const struct fixture_step *const fixture_programs[] = {" + ", ".join(programs) + "};\n"
    if command in (0x1d04,0x1d05):
        actors = [(18,"queens_door")] if command==0x1d04 else [(32,"queens_switch1"),(33,"queens_switch2"),(34,"queens_switch3")]
        for actor,name in actors:
            dispatch += array("static const struct sprite "+name+"[]",sprite_rows({actor:objects[actor]}))
    if command==0x1c03:
        for actor,name in ((18,"apartment_door"),(21,"apartment_window")):
            dispatch+=array("static const struct sprite "+name+"[]",sprite_rows({actor:objects[actor]}))
    if command == 0x0700:
        door = objects[21]
        if data[door["script"]:door["script"]+8] != bytes.fromhex("000000f0 81000000"):
            raise ValueError("Unexpected Gibson house door actor")
        dispatch += array("static const struct sprite gibson_door[]", sprite_rows({21: door}))
        code,count = compile_palette_cycles(data,selected[-1]["commands"],transfers,{21:door},"gibson_door")
        if count != 1: raise ValueError("Unexpected Gibson house light cycle")
        dispatch += code
    if command == 0x0708:
        for actor in (22,23):
            dispatch += array(f"static const struct sprite study_item_{actor}[]",
                              sprite_rows({actor: objects[actor]}))
    if command in (0x070b,0x0603):
        group="garden" if command==0x070b else "hostage_floor"
        garden = []
        for actor in ((16,19,20,21,22,23) if command==0x070b else (17,18)):
            obj = objects[actor]
            pc = obj["script"]
            commands = []
            poses = {}
            while len(commands)<64:
                op,arg,value = struct.unpack_from(">BBH", data, pc+4*len(commands))
                commands.append((op,arg,value))
                if op<128 and op not in poses:
                    patched=bytearray(data)
                    patched[pc:pc+4]=bytes((op,0,0,1))
                    frame=next(o for o in gfx.sprite_frames(patched,selected[-1]["commands"])
                               if o["object"]==actor)
                    symbol=f"{group}_{actor}_{op}"
                    rows=sprite_rows({actor:frame})
                    dispatch+=array(f"static const struct sprite {symbol}[]",rows)
                    poses[op]=(symbol,len(rows),0)
                if op in (0x80,0x81): break
                if op>=128 and op not in (0x82,0x86,0x87,0x95,0x98,0x9f):
                    raise ValueError(f"Unknown garden actor opcode {op:#x}")
            else: raise ValueError("Unterminated garden sprite program")
            frames=[poses.get(i,("NULL",0,0)) for i in range(max(poses)+1)]
            dispatch+=array(f"static const struct motion_step {group}_poses_{actor}[]",frames)
            dispatch+=array(f"static const struct fixture_step {group}_code_{actor}[]",commands)
            garden.append((actor,f"{group}_code_{actor}",f"{group}_poses_{actor}"))
        dispatch+=array(f"static const struct garden_actor {group}_cast[]",garden)
    if command in tour_objects:
        objects = {i: objects[i] for i in tour_objects[command]}
    if command in (0x0704,0x0706):
        # Katrina's overlapping body tiles follow hardware sprite priority.
        for actor in objects.values():
            actor["sprites"].reverse()
    if command==0x2403:
        # Gillian and Metal Gear walk independently. The story controller later
        # stops Gillian, then starts the close-up of Metal Gear.
        commands=selected[-1]["commands"]
        poses=[]
        for frame in range(12):
            actor=19 if frame<6 else 20 if frame<10 else 18 if frame==10 else 16
            pc=objects[actor]["script"]
            patched=bytearray(data)
            patched[pc:pc+4]=bytes((frame,0,0,1))
            pose=next(o for o in gfx.sprite_frames(patched,commands) if o["object"]==actor)
            name=f"passage_pose_{frame}"
            rows=sprite_rows({actor:pose})
            dispatch+=array(f"static const struct sprite {name}[]",rows)
            poses.append((name,len(rows),0))
        dispatch+=array("static const struct motion_step passage_poses[]",poses)
        objects={}
    if command==0x2405:
        # SUBCODE installs the shared sight palette before the first target spawns.
        sub=(source/"SUBCODE.BIN").read_bytes()
        for i in range(1,16):
            word=gfx.u16(sub,19128+2*i)
            colors[i]=tuple(((word>>shift)&7)*255//7 for shift in (1,5,9))
        objects={}
    if command==0x1900:
        # Fight palette row zero is loaded separately from the hallway background.
        for i in range(1,16):
            word=gfx.u16(data,0xe208+2*i)
            colors[i]=tuple(((word>>shift)&7)*255//7 for shift in (1,5,9))
    sprites = sprite_rows(objects)
    palette = [0x8000 | (b*31//255)<<10 | (g*31//255)<<5 | (r*31//255) for r,g,b in colors]
    tag = f"{command:04x}"
    header = dispatch + array(f"static const struct transfer t{tag}[]", transfers)
    header += array(f"static const struct sprite s{tag}[]", sprites)
    header += f"static const uint16_t p{tag}[] = {{" + ", ".join(map(hex,palette)) + "};\n"
    if command == 0x0f01:
        pc = flash["script"]
        if data[pc:pc+8] != bytes.fromhex("97000008 9f3f0000"):
            raise ValueError("Missing blaster sound trigger")
        steps = []
        for n in range(9):
            step = data[pc+8+n*4:pc+12+n*4]
            if step[0] != n or step[1]:
                raise ValueError("Unexpected blaster flash animation")
            patched = bytearray(data)
            patched[pc:pc+4] = step
            actor = next(o for o in gfx.sprite_frames(patched,selected[-1]["commands"])
                         if o["object"] == 16)
            parts = dict(sorted({**objects,16:actor}.items()))
            name = f"blaster_flash_{n}"
            rows = sprite_rows(parts)
            header += array(f"static const struct sprite {name}[]", rows)
            steps.append((name,len(rows),gfx.u16(step,2)))
        if data[pc+44] != 0x80:
            raise ValueError("Missing blaster animation end")
        header += array("static const struct motion_step blaster_flash[]",steps)
    if command == 0x0f02:
        names = []
        for index, offset in enumerate((0, 4, 12, 16)):
            pc = walker["script"] + offset
            frame, mode, hi, lo = data[pc:pc+4]
            if mode or frame != 9+index:
                raise ValueError("Unexpected Metal Gear walking animation")
            patched = bytearray(data)
            patched[walker["script"]:walker["script"]+4] = data[pc:pc+4]
            part = next(o for o in gfx.sprite_frames(patched, selected[-1]["commands"])
                        if o["object"] == 31)
            name = f"navigator_pose_{index}"
            rows = sprite_rows({31: part})
            header += array(f"static const struct sprite {name}[]", rows)
            names.append((name, len(rows), hi*256+lo))
        header += array("static const struct motion_step navigator_walk[]", names)
        header += array("static const struct sprite office_partition[]", sprite_rows({25:objects[25]}))
        actor = objects[21]
        start = actor["script"]
        program = data[start:start+28]
        if (program[:8] != bytes.fromhex("00000000 93000000") or program[8] != 0
                or program[12:17] != bytes.fromhex("95080000 86") or program[20] != 0
                or program[24] != 0x80):
            raise ValueError("Unexpected Harry departure animation")
        velocity = int.from_bytes(program[17:20], "big", signed=True)
        header += array("static const struct sprite harry_body[]", sprite_rows({21: actor}))
        header += array("static const struct sprite empty_office[]",
                        sprite_rows({i: objects[i] for i in (25,26)}))
        header += (f"enum {{ harry_pause = {gfx.u16(program,2+8)}, "
                   f"harry_travel = {gfx.u16(program,2+20)}, harry_velocity = {velocity} }};\n")
    motion = "NULL"
    if command == 0x800:
        header += compile_animation(data, selected[-1]["commands"], objects, 17)
        motion = "&door"
    loop = "NULL"
    loops = {0x1b00: ((16,),27), 0x1b01: ((16,),27), 0x900: ((16, 17), 3), 0x902: ((16, 17), 3),
             0x0b00: ((27,), 4), 0x0b02: ((27,), 4), 0x0e01: ((19,), 4), 0x0f02: ((26,), 4), 0x0f04: ((26,), 4)}
    if command == 0x0f00:
        header += compile_loop(data, selected[-1]["commands"], objects, tag, (16,), 7, 3)
        loop = f"&walk_{tag}"
    if command==0x1907:
        pc=drip["script"]
        cmds=selected[-1]["commands"]
        steps=[]
        program=data[pc:pc+56]
        if program[:8]!=bytes.fromhex("97ff4080 00ff205a") or program[36:40]!=bytes.fromhex("9f160000") or program[-4]!=0x81:
            raise ValueError("Unexpected factory drip animation")
        for offset in range(0,52,4):
            frame,mode,hi,lo=program[offset:offset+4]
            if frame==0x9f: continue
            name="NULL"
            rows=[]
            if frame!=0x97:
                tmp=bytearray(data)
                tmp[pc:pc+4]=bytes((frame,0,0,1))
                part=next(o for o in gfx.sprite_frames(tmp,cmds) if o["object"]==16)
                name=f"factory_drip_{frame}"
                rows=sprite_rows({16:part})
                header+=array(f"static const struct sprite {name}[]",rows)
            steps.append((name,len(rows),hi if mode else hi*256+lo))
        header+=array("static const struct motion_step drip_steps[]",steps)
        header+="static const struct motion drip_loop={16,104,48,120,136,drip_steps,12,0};\n"
        loop="&drip_loop"
    if command in loops:
        header += compile_loop(data, selected[-1]["commands"], objects, tag, *loops[command])
        loop = f"&walk_{tag}"
    cycles, cycle_count = "NULL", 0
    if command in (0x1d04, 0x1d06, 0x0002, 0x0700, 0x0701, 0x0702, 0x0703, 0x070b, 0x070c, 0x070d, 0x0c04, 0x0e00, 0x1907):
        code, cycle_count = compile_palette_cycles(data, selected[-1]["commands"], transfers, objects, tag)
        header += code
        cycles = "cycles_"+tag
    if command == 0x1908:
        # The room starts both single-color cycles from invisible actor 21.
        cmds = selected[-1]["commands"]
        records = [p for c in cmds if c["op"] == 2
                   for p in range(c["body"], c["body"]+c["length"], 12)]
        record = next(p for p in records if data[p] == 21)
        pc = record+12+int.from_bytes(data[record+10:record+12], "big", signed=True)
        events = []
        for offset in (4, 8):
            if data[pc+offset] != 0x88: raise ValueError("Missing wreck palette cycle")
            start = pc+gfx.u16(data, pc+offset+2)
            end = start+4
            while gfx.u16(data,end) != 0xffff:
                end += 4
            events.append({"op":0,"body":start,"length":end+2-start})
        code, cycle_count = compile_palette_cycles(data, events, transfers, {}, tag)
        header += code
        cycles = "cycles_"+tag
    return header, f'{{0x{tag}, "{module}", t{tag}, {len(transfers)}, s{tag}, {len(sprites)}, p{tag}, {motion}, {scroll}, {loop}, {cycles}, {cycle_count}}}'

headers, entries = [], []
for command, module, program in [(0x0002,"DATA_A0.BIN",2),
                                 *((0x1e00 + program, "DATA_Q5.BIN", program) for program in (0,1,2)),
                                 *((0x1d00 + program, "DATA_Q3.BIN", program) for program in (2,4,5,6,7,8)),
                                 *((0x1c00 + program, "DATA_P0.BIN", program) for program in (1,3,4,5)),
                                 *((0x0700 + program, "DATA_G0.BIN", program) for program in range(14)),
                                 (0xd200,"DATA_D2.BIN",0),(0xd201,"DATA_D2.BIN",0),(0xd202,"DATA_D2.BIN",0),(0x802,"DATA_H08.BIN",1),(0x801,"DATA_H00.BIN",1),
                                 (0x800,"DATA_H00.BIN",0),(0x900,"DATA_H01.BIN",0),
                                 (0x902,"DATA_H01.BIN",2),(0xa00,"DATA_H02.BIN",0),
                                 (0xa01,"DATA_H02.BIN",1),(0xb00,"DATA_H03.BIN",0),(0xb02,"DATA_H03.BIN",2),
                                 (0xc00,"DATA_H04.BIN",0),(0xc01,"DATA_H04.BIN",1),(0xc02,"DATA_H04.BIN",2),(0xc04,"DATA_H04.BIN",4),(0xc05,"DATA_H04.BIN",5),(0xd00,"DATA_H05.BIN",0),
                                 (0xe00,"DATA_H06.BIN",0),(0xe01,"DATA_H06.BIN",1),(0xf00,"DATA_H07.BIN",0),(0xf01,"DATA_H07.BIN",1),(0xf02,"DATA_H07.BIN",2),
                                 (0xf03,"DATA_H07.BIN",3),(0xf04,"DATA_H07.BIN",4),
                                 (0x1b00,"DATA_O0.BIN",0),(0x1b01,"DATA_O0.BIN",1),(0x1b02,"DATA_O0.BIN",2),
                                 (0x1b03,"DATA_O0.BIN",3),(0x1b04,"DATA_O0.BIN",4),
                                 (0x0601,"DATA_F4.BIN",1),(0x0603,"DATA_F4.BIN",3),(0x0500,"DATA_F0.BIN",0),(0x0502,"DATA_F0.BIN",2),(0x0503,"DATA_F0.BIN",3),(0x0504,"DATA_F0.BIN",4),(0x0505,"DATA_F0.BIN",5),(0x0506,"DATA_F0.BIN",6),(0x0507,"DATA_F0.BIN",7),(0x050b,"DATA_F0.BIN",11),(0x1700,"DATA_I0.BIN",0),(0x1701,"DATA_I0.BIN",1),(0x1702,"DATA_I0.BIN",2),(0x1704,"DATA_I0.BIN",4),(0x1705,"DATA_I0.BIN",5),(0x1706,"DATA_I0.BIN",6),(0x1707,"DATA_I0.BIN",7),(0x1708,"DATA_I0.BIN",8),(0x1800,"DATA_J0.BIN",0),(0x1801,"DATA_J0.BIN",1),(0x1802,"DATA_J0.BIN",2),
                                 (0x2403,"DATA_U0.BIN",3),(0x2405,"DATA_U0.BIN",5),
                                 (0x1900,"DATA_K1.BIN",0),(0x1906,"DATA_K1.BIN",6),(0x2905,"DATA_Y05.BIN",5),(0x1908,"DATA_K1.BIN",8),(0x1909,"DATA_K1.BIN",9),(0x190a,"DATA_K1.BIN",10),(0x190e,"DATA_K1.BIN",14),
                                 (0x1902,"DATA_K1.BIN",2),(0x1907,"DATA_K1.BIN",7),(0x1901,"DATA_K1.BIN",1),(0x1905,"DATA_K1.BIN",5),(0x2000,"DATA_S0.BIN",0),(0x2001,"DATA_S0.BIN",1),(0x2003,"DATA_S0.BIN",3),(0x2100,"DATA_S1.BIN",0),(0x2102,"DATA_S1.BIN",2)]:
    header, entry = compile_scene(command, module, program)
    headers.append(header)
    entries.append(entry)
(out / "reception.h").write_text("".join(headers) + "static const struct scene scenes[] = {\n" +
                                 ",\n".join(entries) + "\n};\n")

# SP06 requests H01 program 1 without the preceding H01 program 0.
# It transfers one tile bank and instantiates the six-piece title sprite.
from PIL import Image
from struct import pack
# Compile the settled videophone panel after actor 31 loads the rear plane.
phone_module = (source/"DATA_M0.BIN").read_bytes()
if hashlib.sha1(phone_module).hexdigest() != manifest["DATA_M0.BIN"]["sha1"]:
    raise ValueError("Unexpected videophone module")
phone_program = gfx.sequences(phone_module)[0]
commands = phone_program["commands"]
vram = bytearray(65536)
streams, errors = gfx.resources(phone_module,[phone_program])
if errors: raise ValueError(errors)
for stream in streams:
    raw = gfx.stream_bytes(phone_module,stream)
    for reference in stream["references"]:
        addr = reference["vram"]
        vram[addr:addr+len(raw)] = raw
controller = next(p for cmd in commands if cmd["op"] == 2
                  for p in range(cmd["body"],cmd["body"]+cmd["length"],12) if phone_module[p]==31)
pc = controller+12+int.from_bytes(phone_module[controller+10:controller+12],"big",signed=True)
event = pc+gfx.u16(phone_module,pc+6)
offset = gfx.u32(phone_module,event+2)-gfx.BASE
addr, size = gfx.u16(phone_module,event+6), gfx.u16(phone_module,event+10)
if phone_module[pc+4]!=0x8a or addr!=0xc000 or gfx.u16(phone_module,offset)!=size:
    raise ValueError("Missing videophone background transfer")
vram[addr:addr+size] = gfx.decode(phone_module,offset+2,size)[0]
colors,_ = gfx.palette(phone_module,commands)
actors = [o for o in gfx.sprite_frames(phone_module,commands)
          if not phone_module[o["record"]+1]&2 and phone_module[o["script"]]!=0x93]
phone = gfx.draw_sprites(gfx.compose(vram,colors),vram,colors,actors).crop((32,8,224,136))
lamp = next(o for o in actors if o["object"]==26)
pc = lamp["script"]
if phone_module[pc+8:pc+20]!=bytes.fromhex("0c000008 0d000008 81020000"):
    raise ValueError("Unexpected videophone lamp sequence")
alternate = bytearray(phone_module)
alternate[pc:pc+4] = phone_module[pc+12:pc+16]
alternate_actors = [o for o in gfx.sprite_frames(alternate,commands)
                    if any(o["object"]==active["object"] for active in actors)]
blink = gfx.draw_sprites(gfx.compose(vram,colors),vram,colors,alternate_actors).crop((32,8,224,136))
from PIL import ImageChops
left,top,right,bottom=ImageChops.difference(phone,blink).getbbox()
(out/"videophone_art.h").write_text(f"enum {{ phone_lamp_x={left}, phone_lamp_y={top}, "
                                    f"phone_lamp_w={right-left}, phone_lamp_h={bottom-top} }};\n")
# Keep both lamp states resident while the data drive is reading speech.
(cd/"PHONEUI.BIN").write_bytes(b"".join(pack(">H",0x8000 | r*31//255 | (g*31//255)<<5 | (b*31//255)<<10)
                                      for image in (phone,blink) for r,g,b in image.get_flattened_data()))

# Napoleon's actor 31 transfers an initial tile list, a palette, and a second
# tile list. The mouth descriptor is the speaking pose from the retail SAT.
call_commands = gfx.sequences(phone_module)[1]["commands"]
call_objects = {o["object"]:o for o in gfx.sprite_frames(phone_module,call_commands)}
controller = next(p for cmd in call_commands if cmd["op"] == 2
                  for p in range(cmd["body"],cmd["body"]+cmd["length"],12) if phone_module[p]==31)
pc = controller+12+int.from_bytes(phone_module[controller+10:controller+12],"big",signed=True)
def caller_tiles(vram, pc, instruction):
    if phone_module[instruction]!=0x8a:
        raise ValueError("Missing caller tile transfer")
    table=pc+gfx.u16(phone_module,instruction+2)
    pos=table+2
    while gfx.u16(phone_module,pos)!=0xffff:
        offset=gfx.u32(phone_module,pos)-gfx.BASE
        dest,skip,size=struct.unpack_from(">HHH",phone_module,pos+4)
        data=gfx.decode(phone_module,offset+2)[0][skip:skip+size]
        if not data or dest+len(data)>len(vram):
            raise ValueError("Invalid caller tile transfer")
        vram[dest:dest+len(data)]=data
        pos+=10
idle_vram = vram.copy()
idle_colors = colors.copy()
for instruction in (pc,pc+24):
    caller_tiles(vram, pc, instruction)
palette=pc+gfx.u16(phone_module,pc+14)
colors,_=gfx.palette(phone_module,[dict(op=0,offset=palette,body=palette,length=10)],colors)
mouth={"sprites":[dict(x=96,y=80,width=4,height=4,tile=0x4400)]}
caller=[]
for phase in (12,13):
    data=bytearray(phone_module)
    addr=call_objects[26]["script"]
    data[addr]=phase
    objs={o["object"]:o for o in gfx.sprite_frames(data,call_commands)}
    sprites=[mouth,objs[32],objs[26],objs[27],objs[28]]
    caller.append(gfx.draw_sprites(gfx.compose(vram,colors),vram,colors,sprites).crop((32,8,224,136)))
rest=gfx.draw_sprites(gfx.compose(vram,colors),vram,colors,sprites[1:]).crop((32,8,224,136))
box=ImageChops.difference(rest,caller[-1]).getbbox()
x,y,right,bottom=box
with (out/"videophone_art.h").open("a") as art:
    art.write(f"enum {{ mouth_x={x}, mouth_y={y}, mouth_w={right-x}, mouth_h={bottom-y} }};\n")
    pixels=[0x8000 | r*31//255 | (g*31//255)<<5 | (b*31//255)<<10 for r,g,b in rest.crop(box).get_flattened_data()]
    art.write("static const uint16_t mouth_closed[]={"+",".join(map(str,pixels))+"};\n")
(cd/"PHONENAP.BIN").write_bytes(b"".join(pack(">H",0x8000 | r*31//255 | (g*31//255)<<5 | (b*31//255)<<10)
                                        for frame in caller for r,g,b in frame.get_flattened_data()))

# Katrina's apartment call uses M0 program five. Actor 32 blinks over
# the caller backdrop while actor 26 flashes the connection lamp.
commands=gfx.sequences(phone_module)[5]["commands"]
controller=next(p for c in commands if c["op"]==2
                for p in range(c["body"],c["body"]+c["length"],12) if phone_module[p]==31)
pc=controller+12+int.from_bytes(phone_module[controller+10:controller+12],"big",signed=True)
call_vram=idle_vram.copy()
caller_tiles(call_vram,pc,pc)
pos=pc+gfx.u16(phone_module,pc+14)
call_colors,_=gfx.palette(phone_module,[dict(op=0,body=pos,offset=pos,length=10)],idle_colors)
call_actors={o["object"]:o for o in gfx.sprite_frames(phone_module,commands)}
eye=call_actors[32]["script"]
if phone_module[eye:eye+20]!=bytes.fromhex("00ffa8e8 01000002 02000002 01000002 81000000"):
    raise ValueError("Unexpected Katrina blink program")
pictures=[]
for lamp in (12,13):
    for eyelid in (0,1,2):
        data=bytearray(phone_module)
        data[call_actors[26]["script"]]=lamp
        data[eye]=eyelid
        objs={o["object"]:o for o in gfx.sprite_frames(data,commands)}
        picture=gfx.draw_sprites(gfx.compose(call_vram,call_colors),call_vram,call_colors,
                                 [objs[i] for i in (32,26,27,28)]).crop((32,8,224,136))
        pictures.append(picture)
def rgb_word(rgb):
    r,g,b=rgb
    return 0x8000 | r*31//255 | (g*31//255)<<5 | (b*31//255)<<10
(cd/"PHONEKAT.BIN").write_bytes(b"".join(pack(">H",rgb_word(c)) for image in pictures[::3]
                                         for c in image.get_flattened_data()))
box=ImageChops.lighter(ImageChops.difference(pictures[0],pictures[1]),
                        ImageChops.difference(pictures[0],pictures[2])).getbbox()
l,t,r,b=box
with (out/"videophone_art.h").open("a") as art:
    art.write(f"enum {{ caller_eye_x={l},caller_eye_y={t},caller_eye_w={r-l},caller_eye_h={b-t} }};\n")
    art.write(array("static const uint16_t caller_eyelids[3][caller_eye_w*caller_eye_h]",
                    [[rgb_word(c) for c in im.crop(box).get_flattened_data()] for im in pictures[:3]]))

# Plato's Cavern uses M0 program 9. Actor 31 installs the no-video card.
store_commands = gfx.sequences(phone_module)[9]["commands"]
store_actors = {o["object"]: o for o in gfx.sprite_frames(phone_module,store_commands)}
controller = next(p for cmd in store_commands if cmd["op"] == 2
                  for p in range(cmd["body"], cmd["body"]+cmd["length"], 12) if phone_module[p]==31)
pc = controller+12+int.from_bytes(phone_module[controller+10:controller+12],"big",signed=True)
caller_tiles(idle_vram, pc, pc)
palette = pc+gfx.u16(phone_module,pc+14)
if phone_module[palette:palette+4]!=bytes.fromhex("0601400f"):
    raise ValueError("Unexpected no-video palette cycle")
store_frames = []
for lamp_phase in (12,13):
    data = bytearray(phone_module)
    data[store_actors[26]["script"]] = lamp_phase
    sprites = [o for o in gfx.sprite_frames(data,store_commands) if o["object"] in (26,27,28)]
    for phase in range(4):
        offset = gfx.u32(phone_module,palette+4+phase*4)-gfx.BASE
        colors = idle_colors.copy()
        for i in range(16):
            word = gfx.u16(phone_module,offset+2*i)
            colors[32+i] = tuple(((word>>shift)&7)*255//7 for shift in (1,5,9))
        image = gfx.draw_sprites(gfx.compose(idle_vram,colors),idle_vram,colors,sprites)
        store_frames.append([0x8000 | r*31//255 | (g*31//255)<<5 | (b*31//255)<<10
                             for r,g,b in image.crop((32,8,224,136)).get_flattened_data()])
# Each index describes one pixel across the entire 16-tick cycle.
sequences = {}
indices = bytearray()
for cycle in zip(*store_frames):
    indices.append(sequences.setdefault(cycle,len(sequences)+1))
with (cd/"PHONEOFF.BIN").open("wb") as store:
    # The lamp changes phase four ticks into each eight-tick palette cycle.
    for phase in (0,1,6,7,4,5,2,3):
        words = [0]+[cycle[phase] for cycle in sequences]
        store.write(pack(">256H",*(words+[0]*(256-len(words)))))
    store.write(indices)

# The M0 keyboard is a 32-column name table. Only nine rows are visible.
keyboard_tiles=gfx.decode(phone_module,0x1b86+2)[0]
keyboard_map=gfx.decode(phone_module,0x9ee4+2)[0]
keyboard_palette=(source/"SUBCODE.BIN").read_bytes()[0x3f96:0x3f9e]
def keyboard_color(word):
    red,green,blue=((word>>n)&7 for n in (1,5,9))
    return 0x8000 | red*255//7*31//255 | (green*255//7*31//255)<<5 | (blue*255//7*31//255)<<10
palette=[0x8000]*8+[keyboard_color(c) for (c,) in struct.iter_unpack(">H",keyboard_palette)]
def c_bytes(name, data):
    return "static const uint8_t "+name+"[]={\n"+ "".join(
        ",".join(map(str,data[i:i+32]))+",\n" for i in range(0,len(data),32))+"};\n"
indices=bytearray()
for y in range(72):
    for x in range(256):
        word=gfx.u16(keyboard_map,2*(y//8*32+x//8))
        u=(7-x%8) if word&0x800 else x%8
        v=(7-y%8) if word&0x1000 else y%8
        offset=32*((word&2047)-256)+v*4+u//2
        color=(keyboard_tiles[offset]>>(0 if u%2 else 4))&15
        if color>=len(palette): raise ValueError("Unexpected password keyboard color")
        if x%2: indices[-1]|=color
        else: indices.append(color<<4)
(out/"keyboard_art.h").write_text(c_bytes("keyboard_pixels",indices)+
    "static const uint16_t keyboard_colors[]={"+",".join(map(str,palette))+"};\n")

title_module = (source / "DATA_H01.BIN").read_bytes()
seq = gfx.sequences(title_module)[1]
tiles = bytearray(65536)
blocks, errors = gfx.resources(title_module, [seq])
if errors:
    raise ValueError(errors)
for block in blocks:
    payload = gfx.stream_bytes(title_module, block)
    for ref in block["references"]:
        offset = ref["vram"]
        tiles[offset:offset+len(payload)] = payload
sprites = gfx.sprite_frames(title_module, seq["commands"])
# The native palette animation selects this 16-color row for the settled title.
colors = []
for offset in range(0x2dba, 0x2dda, 2):
    word = gfx.u16(title_module, offset)
    colors.append(tuple(((word >> shift) & 7) * 255 // 7 for shift in (1, 5, 9)))
title = gfx.draw_sprites(Image.new("RGB", (256, 224)), tiles, colors, sprites)
bounds = title.getbbox()
pixels = title.crop(bounds)
header = pack(">4H", bounds[0], bounds[1], pixels.width, pixels.height)
(cd / "ACT1.BIN").write_bytes(header + b"".join(
    pack(">H", 0x8000 | (r*31//255) | (g*31//255)<<5 | (b*31//255)<<10)
    for r,g,b in pixels.get_flattened_data()))

# SUBCODE inventory program 9 draws the ID card using object 1. Zero in
# the packed sprite is transparent. Black palette entries remain opaque.
sub = (source / "SUBCODE.BIN").read_bytes()
positions = [struct.unpack_from(">hh", sub, 0x144c6-0xd400+4*i) for i in range(18)]
item_files = []
max_pixels = 0
for item, program in enumerate(gfx.sequence_table(sub, 0x146ce-0xd400)):
    filename = {9:"IDCARD.BIN", 11:"KEY.BIN", 12:"NOTE.BIN", 14:"BLASTER.BIN"}.get(item, f"ITEM{item:02}.BIN")
    item_files.append(filename)
    cmds = program["commands"]
    obj, = gfx.sprite_frames(sub, cmds, 0xd400)
    x, y = 128, 112
    vram = bytearray(65536)
    blocks, errors = gfx.resources(sub, [program], 0xd400)
    if errors:
        raise ValueError(errors)
    for block in blocks:
        raw = gfx.stream_bytes(sub, block)
        for ref in block["references"]:
            addr = ref["vram"]
            vram[addr:addr+len(raw)] = raw
    for sprite in obj["sprites"]:
        sprite["x"] += x-obj["initial_state"]["x"]
        sprite["y"] += y-obj["initial_state"]["y"]
    words = [0x000, 0xeee, 0x0ee, 0x86e, 0xee0, 0xe42, 0x4e0, 0x000]
    base = [tuple(((w >> shift) & 7)*255//7 for shift in (1,5,9)) for w in words]
    colors, _ = gfx.palette(sub, cmds, base+[(0,0,0)]*56, 0xd400)
    image = gfx.draw_sprites(Image.new("RGB", (256, 224)), vram, [(i,i,i) for i in range(64)], [obj])
    left, top, right, bottom = image.getbbox()
    indices = image.crop((left,top,right,bottom)).getchannel("R").tobytes()
    max_pixels = max(max_pixels, len(indices))
    asset = pack(">4H", left, top, right-left, bottom-top)
    for i in indices:
        r,g,b = colors[i]
        asset += pack(">H", (0x8000 | r*31//255 | (g*31//255)<<5 | (b*31//255)<<10) if i else 0)
    (cd / filename).write_bytes(asset)

(out / "item_art.h").write_text(
    array("static const int item_positions[][2]", positions) +
    "static const char *const item_files[] = {" + ", ".join(map(json.dumps, item_files)) + "};\n" +
    f"enum {{ item_pixels = {max_pixels} }};\n")

# Frame lists and actor programs used by the introductory joypad exercise.
data = (source / "DATA_H06.BIN").read_bytes()
cmds = gfx.sequences(data)[0]["commands"]
actors = {o["object"]:o for o in gfx.sprite_frames(data, cmds)}
header = []
factory = (source / "DATA_K1.BIN").read_bytes()
tunnel=(source/"DATA_U0.BIN").read_bytes()
tunnel_actors={o["object"]:o for o in gfx.sprite_frames(tunnel,gfx.sequences(tunnel)[5]["commands"])}
swarm=(source/"DATA_Y05.BIN").read_bytes()
swarm_actors={o["object"]:o for o in gfx.sprite_frames(swarm,gfx.sequences(swarm)[1]["commands"])}
corridor_actors={o["object"]:o for o in gfx.sprite_frames(swarm,gfx.sequences(swarm)[2]["commands"])}
corridor_fields=[corridor_actors.get(i) for i in range(32,41)]
swarm_fields=[swarm_actors.get(i) for i in range(32,41)]
swarm_tables=sorted({actor["frame_table"] for actor in swarm_fields if actor})
factory_actors = {o["object"]:o for o in gfx.sprite_frames(factory,gfx.sequences(factory)[0]["commands"])}
apartment=(source/"DATA_I0.BIN").read_bytes()
apartment_actors={o["object"]:o for o in gfx.sprite_frames(apartment,gfx.sequences(apartment)[2]["commands"])}
bath=(source/"DATA_F0.BIN").read_bytes()
bath_actors={o["object"]:o for o in gfx.sprite_frames(bath,gfx.sequences(bath)[7]["commands"])}
hostage=(source/"DATA_F4.BIN").read_bytes()
hostage_actors={o["object"]:o for o in gfx.sprite_frames(hostage,gfx.sequences(hostage)[1]["commands"])}
skeleton=(source/"DATA_Q3.BIN").read_bytes()
skeleton_commands=gfx.sequences(skeleton)[2]["commands"]
skeleton_actors={o["object"]:o for o in gfx.sprite_frames(skeleton,skeleton_commands)}
mika=(source/"DATA_H13.BIN").read_bytes()
mika_actors={o["object"]:o for o in gfx.sprite_frames(mika,gfx.sequences(mika)[0]["commands"])}
ceiling=(source/"DATA_H02.BIN").read_bytes()
ceiling_actors={o["object"]:o for o in gfx.sprite_frames(ceiling,gfx.sequences(ceiling)[2]["commands"])}
taxi=(source/"DATA_T0.BIN").read_bytes()
taxi_actors={o["object"]:o for o in gfx.sprite_frames(taxi,gfx.sequences(taxi)[0]["commands"])}
crawler_commands=gfx.sequences(skeleton)[3]["commands"]
crawler_actors={o["object"]:o for o in gfx.sprite_frames(skeleton,crawler_commands)}
# Q3 scrolls the operating table left 24 pixels before the second attack.
# Rebuild the uncovered background, then load the crawler's sprite patterns.
crawler_vram=bytearray(65536)
crawler_colors=None
for phase in (0,2,3):
    seq=gfx.sequences(skeleton)[phase]
    blocks,errors=gfx.resources(skeleton,[seq])
    if errors: raise ValueError(errors)
    for block in blocks:
        raw=gfx.stream_bytes(skeleton,block)
        for ref in block["references"]:
            address=ref["vram"]
            crawler_vram[address:address+len(raw)]=raw
    crawler_colors,_=gfx.palette(skeleton,seq["commands"],crawler_colors)
    if phase==2:
        background=gfx.compose(crawler_vram,crawler_colors).crop((56,8,248,136))
def saturn_color(rgb):
    r,g,b=rgb
    return 0x8000 | (r*31//255) | ((g*31//255)<<5) | ((b*31//255)<<10)
palette=[]
for start in (52086,51766,51798,51926):
    for word, in struct.iter_unpack(">H",skeleton[start:start+32]):
        palette.append(saturn_color(tuple(((word>>shift)&7)*255//7 for shift in (1,5,9))))
(cd/"QFIGHT.BIN").write_bytes(crawler_vram+struct.pack(">64H",*palette)+
                          struct.pack(">24576H",*(saturn_color(rgb) for rgb in background.get_flattened_data())))
for bank, frame_data, table, last in [
        ("mika_sight",mika,mika_actors[21]["frame_table"],14),
        ("ceiling",ceiling,ceiling_actors[24]["frame_table"],17),
        ("ceiling_sight",ceiling,ceiling_actors[21]["frame_table"],14),
        ("driver",taxi,taxi_actors[37]["frame_table"],11),
        ("driver_sight",taxi,taxi_actors[21]["frame_table"],14),
        ("crawler",skeleton,crawler_actors[38]["frame_table"],16),
        ("crawler_sight",skeleton,crawler_actors[21]["frame_table"],14),
        ("skeleton_attack",skeleton,skeleton_actors[24]["frame_table"],6),
        ("skeleton_sight",skeleton,skeleton_actors[21]["frame_table"],14),
        ("hostage",hostage,hostage_actors[31]["frame_table"],9),
        ("hostage_sight",hostage,hostage_actors[21]["frame_table"],14),
        ("lisa",bath,bath_actors[30]["frame_table"],26),
        ("lisa_sight",bath,bath_actors[21]["frame_table"],14),
        ("ivan",apartment,apartment_actors[36]["frame_table"],11),
        ("ivan_sight",apartment,apartment_actors[21]["frame_table"],14),
        ("field",data,actors[32]["frame_table"],69),
        ("sight",data,actors[21]["frame_table"],14),
        *((f"swarm{table}",swarm,table,max(
            [48] + [swarm[j] for actor in swarm_fields if actor and actor["frame_table"]==table
                    for pc in [actor["script"]] for j in range(pc+8,pc+4*(swarm[pc+7]+2),4)
                    if swarm[j]<128])) for table in swarm_tables),
        ("corridor",swarm,corridor_actors[24]["frame_table"],max(
            swarm[j] for a in corridor_fields if a for j in range(a["script"]+8,
            a["script"]+4*(swarm[a["script"]+7]+2),4) if swarm[j]<128)),
        ("swarm_sight",swarm,swarm_actors[21]["frame_table"],14),
        ("tunnel",tunnel,tunnel_actors[32]["frame_table"],34),
        ("tunnel_sight",tunnel,tunnel_actors[21]["frame_table"],14),
        ("insector",factory,factory_actors[33]["frame_table"],34),
        ("factory_sight",factory,factory_actors[21]["frame_table"],14)]:
    frames = []
    for frame in range(last+1):
        at = table + int.from_bytes(frame_data[table+2*frame:table+2*frame+2],"big",signed=True)
        count = (gfx.u16(frame_data,at)+1)&0xffff
        if count > 80 or at+2+count*8 > len(frame_data):
            raise ValueError("Invalid range frame")
        sprites = []
        for j in range(count):
            y, size, tile, x = struct.unpack_from(">hHHh", frame_data, at+2+j*8)
            sprites.append((x, y, 1+((size>>10)&3), 1+((size>>8)&3), tile))
        name = f"{bank}_{frame}"
        if sprites:
            header.append(array(f"static const struct sprite {name}[]", sprites))
        frames.append((name if sprites else "NULL", count))
    header.append(array(f"static const struct range_frame {bank}_frames[]", frames))
header.append("static const struct range_frame *const swarm_frames[9]={"+
              ", ".join(f"swarm{a['frame_table']}_frames" if a else "NULL" for a in swarm_fields)+"};\n")
header.append(f"#define swarm_attack_frames swarm{swarm_actors[24]['frame_table']}_frames\n")
header.append(array("static const int corridor_positions[9][2]",
                    [(a["initial_state"]["x"],a["initial_state"]["y"]) if a else (0,0) for a in corridor_fields]))
header.append(array("static const int swarm_positions[9][2]",
                    [(a["initial_state"]["x"],a["initial_state"]["y"]) if a else (0,0) for a in swarm_fields]))
header.append(array("static const int tunnel_positions[9][2]",
                    [(tunnel_actors[i]["initial_state"]["x"],tunnel_actors[i]["initial_state"]["y"]) for i in range(32,41)]))
header.append(array("static const int factory_positions[9][2]",
                    [(o["initial_state"]["x"],o["initial_state"]["y"]) if (o:=factory_actors.get(i)) else (0,0)
                     for i in range(32,41)]))
# SUBCODE draws the LIFE bar on plane A. Each lost life replaces three tiles.
hud = bytearray(65536)
for address in (0x11ed8,0x11ee6,0x11ef4):
    streams, _ = gfx.draw_resources(sub,address-0xd400,0xd400)
    block, = streams
    raw = gfx.stream_bytes(sub,block)
    dest = block["references"][0]["vram"]
    hud[dest:dest+len(raw)] = raw
for damage in range(7):
    if damage:
        dest = gfx.u16(sub,0x12ebc-0xd400+2*(6-damage))
        hud[dest:dest+6] = sub[0x12eb6-0xd400:0x12ebc-0xd400]
    rows = []
    for y in range(8):
        row = []
        for x in range(32,224):
            cell = gfx.u16(hud,0xe440+2*(x//8))
            column = (7-x%8) if cell&0x800 else x%8
            line = 7-y if cell&0x1000 else y
            byte = hud[(cell&2047)*32+4*line+column//2]
            row.append(((cell>>9)&48)+((byte>>(4 if column%2==0 else 0))&15))
        rows.append(row)
    header.append(array(f"static const uint8_t factory_life_{damage}[8][192]", rows))
header.append("static const uint8_t (*const factory_life[])[192] = {" +
              ", ".join(f"factory_life_{i}" for i in range(7))+"};\n")
(out / "range_art.h").write_text("".join(header))
# Each target template has two parameter words followed by its frame program.
header = []
for i in (26, 27):
    start = actors[i]["script"]
    header.append(f"static const uint8_t target_{i}[34][4] = {{\n" +
                  "".join("    {" + ", ".join(map(str, data[p:p+4])) + "},\n"
                          for p in range(start,start+34*4,4)) + "};\n")
for name, addr, size in [("field_weights",0x12010,32), ("kind_table",0x12c9a,4)]:
    raw = sub[addr-0xd400:addr-0xd400+size]
    header.append(f"static const uint8_t {name}[] = {{" + ", ".join(map(str,raw)) + "};\n")
for name, addr in [("first_delay",0x11f60), ("initial_speed",0x11f70), ("quota",0x11fa0)]:
    header.append(f"enum {{ {name} = {sub[addr-0xd400]} }};\n")
for name,stage,bank,cast in (("tunnel",8,tunnel,tunnel_actors),("swarm",12,swarm,swarm_actors),("corridor",13,swarm,corridor_actors)):
    fields=[cast[i]["script"] if i in cast else None for i in range(32,41)]
    for pc in sorted(v for v in set(fields) if v is not None):
        end=pc+(bank[pc+7]+2)*4
        header.append(array(f"static const uint8_t {name}_target_{pc}[][4]",
                            [list(bank[i:i+4]) for i in range(pc,end,4)]))
    header.append(f"static const uint8_t (*const {name}_targets[9])[4]={{"+
                  ", ".join(f"{name}_target_{pc}" if pc is not None else "NULL" for pc in fields)+"};\n")
    for key,addr in (("delay",0x11f60),("speed",0x11f70),("quota",0x11f80),
                     ("gun_quota",0x11f90),("limit",0x11fb0)):
        header.append(f"enum {{ {name}_{key}={sub[addr-0xd400+stage]} }};\n")
factory_fields = [factory_actors.get(32+i) for i in range(9)]
for pc in sorted({o["script"] for o in factory_fields if o}):
    end = pc+(factory[pc+7]+2)*4
    header.append(array(f"static const uint8_t factory_target_{pc}[][4]",
                        [list(factory[i:i+4]) for i in range(pc,end,4)]))
header.append("static const uint8_t (*const factory_targets[9])[4] = {" +
              ", ".join("NULL" if not o else f"factory_target_{o['script']}" for o in factory_fields)+"};\n")
for name, addr in [("factory_delay",0x11f60),("factory_speed",0x11f70),("factory_quota",0x11f80),
                   ("factory_limit",0x11fb0),("factory_health",0x11fd0)]:
    header.append(f"enum {{ {name} = {sub[addr-0xd400+1]} }};\n")
pc=hostage_actors[26]["script"]
end=pc+4*(hostage[pc+7]+2)
header.append(array("static const uint8_t hostage_target[][4]",
                    [list(hostage[p:p+4]) for p in range(pc,end,4)]))
for tag,addr in (("delay",0x11f60),("speed",0x11f70),("quota",0x11f80)):
    header.append(f"enum {{ hostage_{tag}={sub[addr-0xd400+4]} }};\n")
for actor in range(26,30):
    pc=bath_actors[actor]["script"]
    end=pc+4*(bath[pc+7]+2)
    header.append(array(f"static const uint8_t lisa_target_{actor}[][4]",
                        [list(bath[p:p+4]) for p in range(pc,end,4)]))
header.append("static const uint8_t (*const lisa_targets[])[4]={lisa_target_26,lisa_target_27,lisa_target_28,lisa_target_29};\n")
for tag,addr in (("hit",0x11f10),("draw",0x11f20),("shot",0x11f30),("attack",0x11f40),
                 ("delay",0x11f60),("speed",0x11f70),("quota",0x11f80),("gun_quota",0x11f90),("limit",0x11fb0)):
    header.append(f"enum {{ lisa_{tag}={sub[addr-0xd400+2]} }};\n")
pc=apartment_actors[36]["script"]
gates=list(apartment[pc:pc+8])
if gates!=[3,11,14,19,24,27,29,33]:
    raise ValueError("Unexpected Ivan combat program")
frames=[list(apartment[pc+4*i:pc+4*i+4]) for i in range(35)]
header.append(array("static const uint8_t ivan_target[][4]",frames))
for tag,addr in (("hit",0x11f10),("draw",0x11f20),("shot",0x11f30),("attack",0x11f40),("quota",0x11f80)):
    header.append(f"enum {{ ivan_{tag}={sub[addr-0xd400+3]} }};\n")
record=next(p for c in skeleton_commands if c["op"]==2 for p in range(c["body"],c["body"]+c["length"]-11,12) if skeleton[p]==33)
pc=record+12+struct.unpack_from(">h",skeleton,record+10)[0]
if skeleton[pc:pc+8]!=bytes.fromhex("02030609 0c0f1114"):
    raise ValueError("Unexpected skeleton eye target")
header.append(array("static const uint8_t skeleton_target[][4]",
                    [list(skeleton[p:p+4]) for p in range(pc,pc+22*4,4)]))
for tag,addr in (("delay",0x11f60),("speed",0x11f70),("quota",0x11f80)):
    header.append(f"enum {{ skeleton_{tag}={sub[addr-0xd400+5]} }};\n")
for tag,addr in (("hit",0x11f10),("draw",0x11f20),("shot",0x11f30),("attack",0x11f40),("delay",0x11f60),("quota",0x11f80),("gun_quota",0x11f90),("limit",0x11fb0)):
    header.append(f"enum {{ mika_{tag}={sub[addr-0xd400+10]} }};\n")
pc=ceiling_actors[33]["script"]
if ceiling[pc:pc+8]!=bytes.fromhex("02030609 0c0f1113"):
    raise ValueError("Unexpected ceiling target program")
header.append(array("static const uint8_t ceiling_target[][4]",
                    [list(ceiling[p:p+4]) for p in range(pc,pc+21*4,4)]))
for tag,addr in (("hit",0x11f10),("draw",0x11f20),("shot",0x11f30),("attack",0x11f40),("delay",0x11f60),("speed",0x11f70),("quota",0x11f80),("gun_quota",0x11f90),("limit",0x11fb0)):
    header.append(f"enum {{ ceiling_{tag}={sub[addr-0xd400+9]} }};\n")
pc=taxi_actors[37]["script"]
if taxi[pc:pc+8]!=bytes.fromhex("03070a0d 10131516"):
    raise ValueError("Unexpected taxi driver target")
header.append(array("static const uint8_t driver_target[][4]",
                    [list(taxi[p:p+4]) for p in range(pc,pc+23*4,4)]))
for tag,addr in (("hit",0x11f10),("draw",0x11f20),("shot",0x11f30),("attack",0x11f40),
                 ("delay",0x11f60),("speed",0x11f70),("quota",0x11f80),("gun_quota",0x11f90),("limit",0x11fb0)):
    header.append(f"enum {{ driver_{tag}={sub[addr-0xd400+7]} }};\n")
pc=crawler_actors[38]["script"]
if skeleton[pc:pc+8]!=bytes.fromhex("03080b0f 12151724"):
    raise ValueError("Unexpected crawling skeleton target")
header.append(array("static const uint8_t crawler_target[][4]",
                    [list(skeleton[p:p+4]) for p in range(pc,pc+38*4,4)]))
for tag,addr in (("delay",0x11f60),("speed",0x11f70),("quota",0x11f80)):
    header.append(f"enum {{ crawler_{tag}={sub[addr-0xd400+6]} }};\n")
(out / "range_program.h").write_text("".join(header))

from prepare_drive import compile_drive
compile_drive((source / "DATA_S1.BIN").read_bytes(), cd / "TRANSIT.BIN", transit=True)
compile_drive((source / "DATA_S0.BIN").read_bytes(), cd / "DRIVE.BIN")
for scan in ["hair","skin","organic"]:
    compile_drive((source/"DATA_K1.BIN").read_bytes(), cd/(scan.upper()+".BIN"), scan)

hq = (source/"DATA_H08.BIN").read_bytes()
city_sections = [compile_drive(hq,None,"return"+str(i)) for i in range(4)]
city_offsets = []
end = 16
for section in city_sections:
    city_offsets.append(end)
    end += len(section)
if end>0x100000:
    raise ValueError(f"Headquarters return exceeds low work RAM: {end}")
(cd/"RETURN.BIN").write_bytes(pack(">4I",*city_offsets)+b"".join(city_sections))
