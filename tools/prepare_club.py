"""Read the club's sprite frames, their durations, and their priority from DATA_O0."""
import struct

def actors(data, commands, objects, stage, gfx, array, sprite_rows, ids=None):
    pieces=[]
    if ids is None:
        ids=(16,17,18,19,20,21,22,23) if stage==2 else (16,)
    for actor in ids:
        obj=objects[actor]
        pc=obj["script"]
        steps=[]
        poses={}
        eye = stage in ("morgue1", "morgue2") and actor == 16
        variants = {}
        dx = dy = 0
        for n in range(100):
            op,mode,word=struct.unpack_from(">BBH",data,pc+4*n)
            if op in (0x80,0x81):break
            if stage=="ivan4" and actor==19 and n==0 and (op,mode,word)==(0xab,255,0):
                # The following two frames loop back to command index one.
                steps.append((0x81,1,0))
                continue
            if eye and op in (0x84, 0x85):
                if op == 0x84:
                    dx = word - obj["initial_state"]["x"]
                else:
                    dy = word - obj["initial_state"]["y"]
                # Retain the slot because the source jump uses an instruction index.
                steps.append((op,mode,word))
                continue
            if stage == "morgue0" and op == 0x9d:
                steps.append((op,mode,word))
                continue
            pose = variants.setdefault((op,dx,dy),len(variants)) if eye and op<128 else op
            if op>=128 and op not in (0x93,0x95,0x97):raise ValueError("Unknown Outer Heaven sprite command")
            if op<128 and pose not in poses:
                changed=bytearray(data)
                changed[pc:pc+4]=bytes((op,0,0,1))
                frame=next(o for o in gfx.sprite_frames(changed,commands) if o["object"]==actor)
                name=f"club_{stage}_{actor}_{pose}"
                rows=sprite_rows({actor:frame})
                if eye:
                    rows=[(x+dx,y+dy,w,h,t) for x,y,w,h,t in rows]
                pieces.append(array(f"static const struct sprite {name}[]",rows))
                poses[pose]=(name,len(rows))
            steps.append((pose,mode,word))
        else:raise ValueError("Unterminated Outer Heaven sprite program")
        prefix=f"club_{stage}_{actor}"
        steps.append((op,mode,word))
        pieces.append(array(f"static const struct fixture_step {prefix}_code[]",steps))
        rows=[(*poses.get(i,("NULL",0)),0) for i in range(max(poses)+1)]
        pieces.append(array(f"static const struct motion_step {prefix}_poses[]",rows))
    pieces.append(array(f"static const struct garden_actor club_{stage}[]",
        [(actor,f"club_{stage}_{actor}_code",f"club_{stage}_{actor}_poses") for actor in ids]))
    return ''.join(pieces)


def montage(data, objects, array, sprite_rows):
    """Compile the 30 movable face parts from the H04 composite generator."""
    headers, parts = [], []
    for actor in [30, *range(32, 61)]:
        obj = objects[actor]
        start = obj["script"]
        steps = []
        for pc in range(start, start + 160, 4):
            op, mode, value = struct.unpack_from(">BBH", data, pc)
            if op < 128 and op != obj["frame"]:
                raise ValueError("A montage part changes its tile frame")
            if op >= 128 and op not in (0x81,0x84,0x85,0x86,0x87,0x93,0x98,0x9d):
                raise ValueError(f"Unexpected montage command {op:#x}")
            steps.append((op, mode, value))
            if op == 0x81:
                break
        else:
            raise ValueError("Unterminated montage movement")
        name = f"montage_{actor}"
        rows = sprite_rows({actor: obj})
        origin = obj["initial_state"]
        relative = [(x-origin["x"], y-origin["y"], w, h, tile) for x,y,w,h,tile in rows]
        headers.append(array(f"static const struct sprite {name}_tiles[]", relative))
        headers.append(array(f"static const struct fixture_step {name}_code[]", steps))
        parts.append((actor, name+"_tiles", len(rows), name+"_code"))
    headers.append(array("static const struct face_part montage_parts[]", parts))
    return "".join(headers)


def room_lights(data, commands, actor, tiles, initial, gfx):
    """Compile palette events started by an invisible scene controller."""
    delay=0
    if actor is None:
        offsets=[c["body"] for c in commands if c["op"]==0 and data[c["body"]]==6]
    else:
        record=next(p for cmd in commands if cmd["op"]==2
                    for p in range(cmd["body"],cmd["body"]+cmd["length"],12) if data[p]==actor)
        pc=record+12+struct.unpack_from(">h",data,record+10)[0]
        offsets=[]
        for p in range(pc,pc+48,4):
            op,mode,value=struct.unpack_from(">BBH",data,p)
            if op==0x97 and not offsets: delay+=value
            if op in (0x80,0x81): break
            if op==0x88: offsets.append(pc+value)
    events=[]
    changing=set()
    for off in offsets:
        if data[off]!=6: raise ValueError("Expected timed CRAM transfer")
        base=data[off+2]//2
        size=data[off+3]+1
        colors=[]
        for ptr in range(off+4,off+1024,4):
            if gfx.u16(data,ptr)==65535: break
            pos=gfx.u32(data,ptr)-gfx.BASE
            for j in range(size):
                word=gfx.u16(data,pos+j*2)
                r,g,b=(((word>>k)&7)*255//7*31//255 for k in (1,5,9))
                colors.append(0x8000|r|g<<5|b<<10)
        if not colors or len(colors)>80: raise ValueError("Unexpected lighting table")
        for j in range(size):
            if len(set(colors[j::size]+[initial[base+j]]))>1: changing.add(base+j)
        events.append(struct.pack(">4B80H",base,size,data[off+1]+1,len(colors)//size,
                                  *(colors+[0]*(80-len(colors)))))
    if len(events) not in (1,3): raise ValueError("Unexpected lighting controller")
    indices=gfx.compose(tiles,[(i,i,i) for i in range(64)]).crop((32,8,224,136)).getchannel("R").tobytes()
    pixels=b"".join(struct.pack(">HH",i,c) for i,c in enumerate(indices) if c in changing)
    return struct.pack(">4H",delay,len(events),len(pixels)//4,0)+b"".join(events)+bytes((3-len(events))*164)+pixels
