"""Compile the two neon signs and the shopfront's palette changes from J0."""
import struct


def shopfront(data, commands, objects, tiles, gfx):
    colors = [(i,i,i) for i in range(64)]
    background = gfx.compose(tiles,colors)
    def picture(actors):
        return gfx.draw_sprites(background.copy(),tiles,colors,list(actors.values())).crop((32,8,224,136)).getchannel("R").tobytes()
    initial = picture(objects)
    poses = {}
    delays = []
    for actor in (17,18):
        pc = objects[actor]["script"]
        poses[actor] = []
        while data[pc] < 128 and len(poses[actor]) < 6:
            frame,mode,duration = struct.unpack_from(">BBH",data,pc)
            if mode or not duration:
                raise ValueError("Unexpected shop sign timing")
            modified = bytearray(data)
            modified[objects[actor]["script"]] = frame
            next_pose = next(o for o in gfx.sprite_frames(modified,commands) if o["object"]==actor)
            poses[actor].append(picture({**objects,actor:next_pose}))
            delays.append(duration)
            pc += 4
        if data[pc:pc+4]!=bytes.fromhex("81000000"):
            raise ValueError("Unexpected shop sign loop")
    if [len(poses[a]) for a in (17,18)]!=[3,6]:
        raise ValueError("Unexpected shop sign frame count")
    changing = set()
    palettes = []
    cycles = []
    for cmd in commands:
        p = cmd["body"]
        if cmd["op"]!=0 or data[p]!=6: continue
        base = data[p+2]//2
        size = data[p+3]+1
        table = []
        for off in range(p+4,p+cmd["length"]-2,4):
            pal = gfx.u32(data,off)-gfx.BASE
            for j in range(size):
                value = gfx.u16(data,pal+2*j)
                r,g,b = (((value>>k)&7)*255//7*31//255 for k in (1,5,9))
                table.append(0x8000 | r | g<<5 | b<<10)
        for j in range(size):
            if len(set(table[j::size]))>1:
                changing.add(base+j)
        cycles.append((base,size,data[p+1]+1,len(table)//size))
        palettes.extend(table)
    if [(base,size,count) for base,size,_,count in cycles]!=[(41,1,4),(48,16,6)]:
        raise ValueError("Unexpected shopfront palette programs")
    pixels = bytearray()
    for i,base in enumerate(initial):
        affected = [a for a in poses if any(frame[i]!=base for frame in poses[a])]
        if len(affected)>1: raise ValueError("Shop signs overlap")
        if not affected and base not in changing: continue
        actor = affected[0] if affected else 0
        values = [frame[i] for frame in poses[actor]] if actor else [base]
        y,x = divmod(i,192)
        pixels.extend(struct.pack(">HBB6B",(y+8)*256+x+32,actor,0,*(values+[0]*(6-len(values)))))
    return (struct.pack(">10H",len(pixels)//10,*delays) +
            bytes(v for row in cycles for v in row) +
            struct.pack(">100H",*palettes) + pixels)
