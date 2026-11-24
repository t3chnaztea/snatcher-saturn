#include "plaza.h"
#include "disc.h"
#include <yaul.h>
#include <string.h>

/* The room stays resident while the CD block loads voices and story modules. */
struct header { uint32_t size; uint16_t count,loop; uint32_t offsets[6]; };
struct step { uint16_t delay,patch; };
struct patch { uint16_t first,count; };
struct update { uint16_t cell,tile; };
struct recipe { uint16_t pattern,colors; };
static const struct header *clip;
static const struct step *steps;
static const struct patch *patches;
static const struct update *updates;
static const struct recipe *recipes;
static const uint8_t *patterns;
static const uint16_t *colors;
static unsigned next,delay,pitch,clip_ticks;
static bool played;
static volatile uint16_t *screen;

bool plaza_played(void) { return played; }

static unsigned briefing_cuts,cut,step;
static bool rescue_timing;
static uint32_t rescue_clock;
static unsigned rescue_age,rescue_adjust;
static bool full_screen,timed;
static const uint32_t *const movie=(const uint32_t *)0x00200000;
static const uint16_t *deadlines;
static const uint32_t *mika_sections;
static const uint16_t *apartment_cues;

void plaza_close(void) { clip=NULL; full_screen=timed=false; briefing_cuts=0; mika_sections=NULL; apartment_cues=NULL; }

/* Some SP37 shots update both the cockpit and the snow on each source
 * frame. Merge overdue tile writes before drawing the latest picture. */
static bool video_timed;
static uint32_t last_refresh;
static uint16_t pending_tiles[692];

void plaza_use_video_clock(void)
{
    video_timed=true;
    last_refresh=0;
}

static void draw_update(struct update u)
{
    const struct recipe tile=recipes[u.tile];
    const uint16_t *row=colors+tile.colors;
    volatile uint16_t *dst;
    if (full_screen) {
        dst=screen+8*(u.cell/32)*pitch+8*(u.cell%32);
    } else if (u.cell<384) {
        dst=screen+(8+8*(u.cell/24))*pitch+32+8*(u.cell%24);
    } else {
        unsigned portrait_cell=u.cell-384;
        dst=screen+(136+8*(portrait_cell/28))*pitch+16+8*(portrait_cell%28);
    }
    if (tile.pattern==0xffff) {
        for (unsigned y=0;y<8;y++,dst+=pitch)
            for (unsigned x=0;x<8;x++) dst[x]=*row++;
        return;
    }
    const uint8_t *pixels=patterns+32*tile.pattern;
    for (unsigned y=0;y<8;y++,dst+=pitch)
        for (unsigned x=0;x<8;x+=2) {
            unsigned pair=*pixels++;
            dst[x]=row[pair>>4];
            dst[x+1]=row[pair&15];
        }
}

static void apply_step(void)
{
    const struct step s=steps[next++];
    const struct patch p=patches[s.patch];
    for (unsigned i=0;i<p.count;i++) {
        const struct update u=updates[p.first+i];
        if (video_timed) pending_tiles[u.cell]=u.tile;
        else draw_update(u);
    }
    if (next==clip->count) { played=true; next=clip->loop; }
    delay=s.delay-1;
}

static void tick_video_clip(void)
{
    extern uint32_t video_clock(void);
    uint32_t now=video_clock();
    unsigned elapsed=last_refresh ? now-last_refresh : 1;
    last_refresh=now;
    if (!elapsed || (played && clip->loop+1==clip->count)) return;
    if (elapsed<=delay) { delay-=elapsed; return; }
    memset(pending_tiles,0xff,sizeof(pending_tiles));
    while (elapsed>delay) {
        elapsed-=delay+1;
        apply_step();
        if (played && clip->loop+1==clip->count) { elapsed=0; break; }
    }
    delay-=elapsed;
    for (unsigned cell=0;cell<692;cell++)
        if (pending_tiles[cell]!=0xffff)
            draw_update((struct update){cell,pending_tiles[cell]});
}

static void begin_clip(const uint8_t *bank,bool clear,volatile uint16_t *target,unsigned stride)
{
    clip=(const struct header *)bank;
    steps=(const struct step *)(bank+clip->offsets[0]);
    patches=(const struct patch *)(bank+clip->offsets[1]);
    updates=(const struct update *)(bank+clip->offsets[2]);
    recipes=(const struct recipe *)(bank+clip->offsets[3]);
    patterns=bank+clip->offsets[4];
    colors=(const uint16_t *)(bank+clip->offsets[5]);
    video_timed=false;
    next=delay=clip_ticks=0;
    played=false;
    screen=target;
    pitch=stride;
    if (clear) for (unsigned y=0;y<224;y++)
        for (unsigned x=0;x<256;x++) screen[y*pitch+x]=0x8000;
    apply_step();
}

static const uint8_t *movie_pointer(unsigned index)
{
    return (const uint8_t *)movie+movie[1+index];
}

static void start_cut(unsigned which)
{
    cut=which;
    deadlines=(const uint16_t *)movie_pointer(2*cut+1);
    begin_clip(movie_pointer(2*cut),false,screen,pitch);
    step=1;
}

bool plaza_briefing_load(unsigned track)
{
    unsigned size=disc_read(track==8?"BRIEF8.BIN":track==9?"BRIEF9.BIN":track==12?"HALL12.BIN":track==13?"RESC13.BIN":track==14?"RESC14.BIN":track==15?"A3CD15.BIN":track==16?"A3CD16.BIN":track==17?"A3CD17.BIN":track==18?"A3CD18.BIN":track==21?"VIS21.BIN":"CHASE10.BIN",(void *)movie,0x100000);
    unsigned count=track==8?4:1;
    if (size<4+8*count || movie[0]!=count) return false;
    for (unsigned i=0;i<count;i++) {
        unsigned offset=movie[1+2*i],times=movie[2+2*i];
        if (offset%4 || offset<4+8*count || offset>size-sizeof(struct header) ||
            times<=offset || times>size || times%2) return false;
        const struct header *h=(const struct header *)movie_pointer(2*i);
        if (h->size!=times-offset || !h->count || h->count>(size-times)/2) return false;
    }
    rescue_timing=track==14 && vdp2_tvmd_tv_standard_get()!=VDP2_TVMD_TV_STANDARD_PAL;
    full_screen=track==8 || track==9;
    briefing_cuts=count;
    return true;
}

void plaza_briefing_start(volatile uint16_t *target,unsigned stride)
{
    screen=target;
    pitch=stride;
    timed=true;
    start_cut(0);
    rescue_clock=0;
    rescue_age=rescue_adjust=0;
}

/* The track 14 videophone animates on every NTSC source vblank. The CD block reports whole
 * sectors, sometimes advancing twice between successive Saturn frames. Use
 * the retail frame durations for drawing and the disc position for drift. */
static void rescue_tick(unsigned sector)
{
    extern uint32_t video_clock(void);
    uint32_t now=video_clock();
    unsigned ticks=rescue_clock ? now-rescue_clock : 0;
    rescue_clock=now;
    unsigned previous=step-1;
    unsigned duration=steps[previous].delay;
    if (step<clip->count && ++rescue_adjust>=30) {
        rescue_adjust=0;
        unsigned span=deadlines[step]-deadlines[previous];
        unsigned expected=deadlines[previous]+span*rescue_age/duration;
        if (sector>expected+2) ++ticks;
        else if (expected>sector+2 && ticks) --ticks;
    }
    rescue_age+=ticks;
    while (rescue_age>=duration) {
        if (step==clip->count) { clip=NULL; timed=false; return; }
        rescue_age-=duration;
        apply_step();
        duration=steps[step++].delay;
    }
}

void plaza_tick(void)
{
    if (!clip) return;
    ++clip_ticks;
    if (video_timed) { tick_video_clip(); return; }
    if (!timed) {
        if (delay) --delay;
        else apply_step();
        return;
    }
    unsigned sector;
    if (!disc_track_sector(&sector)) return;
    if (rescue_timing) { rescue_tick(sector); return; }
    if (cut+1<briefing_cuts) {
        const uint16_t *following=(const uint16_t *)movie_pointer(2*(cut+1)+1);
        if (sector>=following[0]) start_cut(cut+1);
    }
    while (step<clip->count && deadlines[step]<=sector) { apply_step(); ++step; }
    if (step==clip->count && cut+1==briefing_cuts) { clip=NULL; timed=false; }
}

bool plaza_open(unsigned scene,void *scratch,size_t capacity,volatile uint16_t *target,unsigned stride)
{
    const char *file=scene==0x1703 ? "IVANDOOR.BIN" : scene==3 ? "SANTA.BIN" : scene ? "PLAZAB.BIN" : "PLAZA.BIN";
    return plaza_load(file,true,scratch,capacity,target,stride);
}

static bool valid_header(const struct header *h,unsigned limit)
{
    if (h->size<sizeof(*h) || h->size>limit || !h->count || h->loop>=h->count ||
        h->offsets[0]!=sizeof(*h) || h->offsets[1]-h->offsets[0]!=sizeof(*steps)*h->count)
        return false;
    for (unsigned i=0;i<6;i++)
        if (h->offsets[i]>=h->size || h->offsets[i]%2 ||
            (i && h->offsets[i]<h->offsets[i-1])) return false;
    return true;
}

bool plaza_mika_call(void *scratch,size_t capacity,volatile uint16_t *target,unsigned stride)
{
    unsigned size=disc_read("MIKACALL.BIN",scratch,capacity);
    const uint32_t *sections=scratch;
    if (size<7*sizeof(*sections)) return false;
    for (unsigned i=0;i<7;i++) {
        unsigned start=sections[i],end=i==6?size:sections[i+1];
        if ((start&3) || start<7*sizeof(*sections) || end>size ||
            start>end || end-start<sizeof(struct header) ||
            !valid_header((const struct header *)((const uint8_t *)scratch+start),end-start)) return false;
    }
    mika_sections=sections;
    begin_clip((const uint8_t *)sections+sections[0],true,target,stride);
    return true;
}

void plaza_mika_voice(unsigned id)
{
    if (!mika_sections || id<762 || id>767) return;
    begin_clip((const uint8_t *)mika_sections+mika_sections[1+id-762],false,screen,pitch);
}

/* These voices fit in the bottom 384 KiB of low WRAM. Keep the film above
 * them so the sound chip can stream while the display advances. */
bool plaza_apartment_film(bool shower,volatile uint16_t *target,unsigned stride)
{
    extern void fm_effect_stop(void);
    fm_effect_stop();
    uint16_t *bank=(uint16_t *)0x00260000;
    size_t bytes=disc_read(shower?"APTSHOW.BIN":"APTTALK.BIN",bank,0xa0000);
    if (bytes<4 || bank[0]!=(shower?464:467) || bank[1]!=(shower?2:19)) return false;
    unsigned offset=4+4*bank[1];
    const struct header *h=(const struct header *)((const uint8_t *)bank+offset);
    if (bytes<offset+sizeof(*h) || !valid_header(h,bytes-offset)) return false;
    for (unsigned i=0;i<bank[1];i++) if (bank[3+2*i]>=h->count) return false;
    apartment_cues=bank;
    begin_clip((const uint8_t *)h,true,target,stride);
    return true;
}

void plaza_apartment_voice(unsigned id)
{
    if (!apartment_cues || id<apartment_cues[0]) return;
    unsigned i=id-apartment_cues[0];
    if (i>=apartment_cues[1]) return;
    clip_ticks=apartment_cues[2+2*i];
    next=apartment_cues[3+2*i];
    played=false;
    apply_step();
}

void plaza_apartment_stop(void)
{
    if (apartment_cues) plaza_close();
}

bool plaza_local_clip(const char *file,void *scratch,size_t capacity,volatile uint16_t *target,unsigned stride)
{
    size_t bytes=disc_read(file,scratch,capacity);
    if (bytes<sizeof(struct header) || !valid_header(scratch,bytes)) return false;
    plaza_close();
    begin_clip(scratch,false,target,stride);
    return true;
}

bool plaza_hospital_door(volatile uint16_t *target,unsigned stride)
{
    /* No voice or drive animation runs between the door and the waiting room. */
    extern void fm_effect_stop(void);
    fm_effect_stop();
    uint8_t *bank=(uint8_t *)0x00200000;
    unsigned size=disc_read("OLEDOOR.BIN",bank,0x100000);
    if (size<sizeof(struct header) || !valid_header((const struct header *)bank,size)) return false;
    begin_clip(bank,true,target,stride);
    return true;
}

static bool load_at(const char *file,unsigned sector,bool clear,void *scratch,size_t capacity,volatile uint16_t *target,unsigned stride)
{
    enum { LIMIT=0x60000, CHUNK=32768 };
    uint8_t *bank=(uint8_t *)VDP1_VRAM(0x20000);
    if (capacity<CHUNK || !disc_read_sectors(file,sector,scratch,1)) return false;
    const struct header *h=scratch;
    if (!valid_header(h,LIMIT)) return false;
    unsigned size=h->size;
    extern void fm_invalidate_scan(void);
    fm_invalidate_scan();
    for (unsigned offset=0;offset<size;offset+=CHUNK) {
        unsigned bytes=size-offset;
        if (bytes>CHUNK) bytes=CHUNK;
        if (!disc_read_sectors(file,sector+offset/2048,scratch,(bytes+2047)/2048)) return false;
        memcpy(bank+offset,scratch,bytes);
    }
    begin_clip(bank,clear,target,stride);
    return true;
}

bool plaza_load(const char *file,bool clear,void *scratch,size_t capacity,volatile uint16_t *target,unsigned stride)
{
    return load_at(file,0,clear,scratch,capacity,target,stride);
}

bool act3_room_clip(unsigned key,bool clear,void *scratch,size_t capacity,volatile uint16_t *target,unsigned stride)
{
    if (capacity<2048 || !disc_read_sectors("ACT3ROOM.BIN",0,scratch,1)) return false;
    unsigned count=*(const uint32_t *)scratch;
    if (count>(2048-4)/4) return false;
    const uint16_t *entries=(const uint16_t *)scratch+2;
    for (unsigned i=0;i<count;i++)
        if (entries[2*i]==key && entries[2*i+1])
            return load_at("ACT3ROOM.BIN",entries[2*i+1],clear,scratch,capacity,target,stride);
    return false;
}

/* Voice playback releases low work RAM before the track 7 montage.
 * Keep every shot here so changing scenes cannot seek away from CD audio. */
static uint32_t *const ending=(uint32_t *)0x00200000;
static unsigned ending_size;

bool plaza_ending(unsigned section,volatile uint16_t *target,unsigned stride)
{
    if (section>=8) return false;
    if (!section) {
        extern void fm_effect_stop(void);
        fm_effect_stop();
        ending_size=disc_read("ACT1END.BIN",ending,0x100000);
    }
    if (ending_size<8*sizeof(*ending)) return false;
    unsigned offset=ending[section];
    if (offset%4 || offset<8*sizeof(*ending) || offset>ending_size-sizeof(struct header))
        return false;
    const uint8_t *bank=(const uint8_t *)ending+offset;
    const struct header *h=(const struct header *)bank;
    if (!h->count || h->loop>=h->count || h->size>ending_size-offset) return false;
    begin_clip(bank,!section,target,stride);
    return true;
}


void plaza_wait_frames(unsigned frames)
{
    extern void scene_wait(unsigned);
    while (clip && clip_ticks<frames) scene_wait(1);
}
