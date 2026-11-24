#include "crash.h"
#include <yaul.h>
#include <string.h>
#include "script.h"
#include "disc.h"

extern bool prologue_play(void);
#include "save.h"
#include "plaza.h"
#include "lightgun.h"
#include "flashlight.h"

static struct investigation game;
static volatile bool input_enabled=true;
void save_input_gate(bool enabled) { input_enabled=enabled; }
static void phone_palette_vblank(void);
static volatile uint32_t video_ticks;
uint32_t video_clock(void) { return video_ticks; }

static void poll_pad(void *unused)
{
    (void)unused;
    ++video_ticks;
    extern void fm_vblank(void);
    fm_vblank();
    phone_palette_vblank();
    if (input_enabled) smpc_peripheral_intback_issue();
}

static uint8_t module_buffer[0x25000] __attribute__((aligned(4)));
bool queens_light(bool enabled)
{
    return flashlight_set(enabled,module_buffer,sizeof(module_buffer));
}
extern void voice_init(void);
extern void scene_tick(void);
extern void fm_effect_tick(void);
extern bool reception_draw(unsigned, unsigned, unsigned, uint8_t *, size_t, volatile uint16_t *, unsigned);

#include "item_art.h"
static uint16_t item_data[item_pixels+4] __attribute__((aligned(4)));
static uint16_t item_background[item_pixels];
static bool item_visible;
static bool panel_visible;

#include "scan.h"
void clear_dialogue(void)
{
    if (!panel_visible) return;
    panel_visible = false;
    volatile uint16_t *screen = (volatile uint16_t *)VDP2_VRAM_ADDR(0, 0) + 32;
    for (unsigned row = game.scene==0x070e ? 166 : 142; row < 224; ++row)
        for (unsigned x = 16; x < 240; ++x) screen[row*512+x] = 0x8000;
    scan_redraw_portrait();
}

void item_hide(void)
{
    if (!item_visible) return;
    volatile uint16_t *screen = (volatile uint16_t *)VDP2_VRAM_ADDR(0, 0) + 32;
    unsigned x = item_data[0], y = item_data[1], w = item_data[2], h = item_data[3];
    for (unsigned row = 0; row < h; row++)
        for (unsigned col = 0; col < w; col++)
            screen[(y+row)*512+x+col] = item_background[row*w+col];
    item_visible = false;
}

void restore_scene_beneath_item(void)
{
    if (item_visible) {
        item_hide();
        item_visible=true;
    }
}

void refresh_scene_item(void)
{
    if (!item_visible) return;
    unsigned x=item_data[0],y=item_data[1],w=item_data[2],h=item_data[3];
    volatile uint16_t *screen = (volatile uint16_t *)VDP2_VRAM_ADDR(0, 0) + 32;
    for (unsigned row = 0; row < h; row++) {
        for (unsigned col = 0; col < w; col++) {
            unsigned offset = (y+row)*512+x+col, index = row*w+col;
            item_background[index] = screen[offset];
            if (item_data[4+index]) screen[offset] = item_data[4+index];
        }
    }
}

bool item_display(unsigned item, unsigned position)
{
    if (item >= sizeof(item_files)/sizeof(item_files[0]) ||
        position >= sizeof(item_positions)/sizeof(item_positions[0])) return false;
    const char *file = item_files[item];
    item_hide();
    size_t bytes = disc_read(file, item_data, sizeof(item_data));
    if (bytes < 8) return false;
    item_data[0] += item_positions[position][0]-128;
    item_data[1] += item_positions[position][1]-112;
    unsigned x = item_data[0], y = item_data[1], w = item_data[2], h = item_data[3];
    if (x+w > 256 || y+h > 224 || bytes != 8+2*w*h) return false;
    item_visible = true;
    refresh_scene_item();
    return true;
}

void scene_wait(unsigned frames)
{
    extern void presentation_tick(void);
    while (frames--) { vdp2_sync(); vdp2_sync_wait(); presentation_tick(); }
}

#include "videophone_art.h"
bool videophone_visible;
static unsigned phone_clock, password_clock;
static unsigned eye_ticks,eye_phase;
static uint32_t eye_random;
static bool katrina_visible;
static bool phone_movie;
static bool phone_closing, phone_connecting, caller_speaking, phone_no_video;
/* The M0 no-video card changes only its CRAM palette. NBG1 displays
 * its indexed pixels above the ordinary room and dialogue bitmap. */
static uint16_t phone_palettes[8][256];
static volatile bool phone_overlay;
static unsigned overlay_tick;
static void phone_palette_vblank(void)
{
    if (phone_overlay && !(++overlay_tick&1))
        memcpy((void *)VDP2_CRAM_ADDR(0),phone_palettes[(overlay_tick/2)%8],512);
}
static void show_phone_overlay(const uint8_t *indices)
{
    const vdp2_scrn_bitmap_format_t fmt = {
        .scroll_screen=VDP2_SCRN_NBG1, .ccc=VDP2_SCRN_CCC_PALETTE_256,
        .bitmap_size=VDP2_SCRN_BITMAP_SIZE_512X256,
        .bitmap_base=VDP2_VRAM_ADDR(3,0), .palette_base=VDP2_CRAM_ADDR(0)
    };
    uint8_t *bitmap=(uint8_t *)fmt.bitmap_base;
    memset(bitmap,0,512*224);
    for (unsigned y=0;y<128;y++)
        memcpy(bitmap+(8+y)*512+64,indices+y*192,192);
    vdp2_scrn_bitmap_format_set(&fmt);
    vdp2_scrn_priority_set(VDP2_SCRN_NBG1,7);
    memcpy((void *)VDP2_CRAM_ADDR(0),phone_palettes[0],512);
    overlay_tick=0;
    phone_overlay=true;
    vdp2_scrn_display_set(VDP2_SCRN_DISP_NBG0|VDP2_SCRN_DISPTP_NBG1);
}
static void phone_paint(unsigned fade, bool full)
{
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    const uint16_t *picture=(const uint16_t *)VDP2_VRAM_ADDR(3,0);
    const uint8_t *indices=(const uint8_t *)VDP2_VRAM_ADDR(2,0x11000);
    const uint16_t *palette=phone_palettes[(overlay_tick/2)%8];
    if (!phone_no_video && ((phone_clock/8)&1)) picture+=192*128;
    full=full || phone_no_video;
    unsigned x=full?0:phone_lamp_x, y=full?0:phone_lamp_y;
    unsigned width=full?192:phone_lamp_w, height=full?128:phone_lamp_h;
    unsigned levels[32];
    if (fade) for (unsigned c=0; c<32; ++c) {
        unsigned step=(c*7+15)/31;
        levels[c]=step>fade ? (step-fade)*255/7*31/255 : 0;
    }
    for (unsigned row=y; row<y+height; ++row) {
        volatile uint16_t *dst=screen+(8+row)*512+32+x;
        const uint16_t *src=picture+row*192+x;
        if (!fade && !phone_no_video) memcpy((void *)dst,src,width*2);
        else for (unsigned col=0; col<width; ++col) {
            uint16_t c=phone_no_video ? palette[indices[row*192+x+col]] : src[col];
            if (!fade) { dst[col]=c; continue; }
            dst[col]=0x8000 | levels[c&31] | (levels[(c>>5)&31]<<5) | (levels[(c>>10)&31]<<10);
        }
    }
}

void videophone_tick(void)
{
    if (!videophone_visible || phone_closing || phone_no_video) return;
    if (phone_movie) { plaza_tick(); return; }
    if (!(++phone_clock%8)) phone_paint(0,false);
    if (!katrina_visible || --eye_ticks) return;
    eye_phase=(eye_phase+1)%4;
    eye_random=1664525u*eye_random+1013904223u;
    eye_ticks=eye_phase?2:168+(eye_random>>16)%65;
    const uint16_t *eye=caller_eyelids[eye_phase==3?1:eye_phase];
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    for (unsigned y=0;y<caller_eye_h;y++)
        memcpy((void *)(screen+(8+caller_eye_y+y)*512+32+caller_eye_x),eye+y*caller_eye_w,2*caller_eye_w);
}

bool videophone_shutdown(void)
{
    if (!videophone_visible) return false;
    if (phone_movie) {
        volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
        uint16_t *picture=(uint16_t *)VDP2_VRAM_ADDR(3,0);
        for (unsigned y=0;y<128;y++) memcpy(picture+192*y,(const void *)(screen+(8+y)*512+32),384);
        phone_clock=0;
        plaza_close();
        phone_movie=false;
    }
    phone_closing=true;
    if (phone_overlay) {
        phone_overlay=false;
        vdp2_scrn_display_set(VDP2_SCRN_DISP_NBG0);
    }
    for (unsigned fade=1; fade<=7; ++fade) {
        phone_paint(fade,true);
        scene_wait(4);
    }
    scene_wait(20);
    return true;
}


static bool videophone_panel(volatile uint16_t *screen, const char *picture_file)
{
    const unsigned width=192, height=128;
    uint16_t *saved=(uint16_t *)VDP2_VRAM_ADDR(2,0);
    uint16_t *picture=(uint16_t *)VDP2_VRAM_ADDR(3,0);
    bool opening=picture_file!=NULL;
    bool indexed=opening && !strcmp(picture_file,"PHONEOFF.BIN");
    unsigned bytes=indexed ? 8*256*2+width*height : width*height*4;
    uint16_t *data=indexed ? (uint16_t *)VDP2_VRAM_ADDR(2,0x10000) : picture;
    if (phone_overlay) {
        phone_overlay=false;
        vdp2_scrn_display_set(VDP2_SCRN_DISP_NBG0);
        vdp2_sync();
        vdp2_sync_wait();
    }
    if (phone_movie) { plaza_close(); phone_movie=false; }
    if (opening && disc_read(picture_file,data,bytes)!=bytes) return false;
    for (unsigned y=0; y<height; ++y) {
        volatile uint16_t *row=screen+(8+y)*512+32;
        if (opening && !videophone_visible) memcpy(saved+y*width,(const void *)row,width*2);
        if (!indexed) memcpy((void *)row,(opening?picture:saved)+y*width,width*2);
    }
    phone_clock=0;
    phone_closing=false;
    videophone_visible=opening;
    phone_no_video=indexed;
    katrina_visible=opening && !strcmp(picture_file,"PHONEKAT.BIN");
    eye_phase=0; eye_ticks=200; eye_random=1;
    if (indexed) {
        memcpy(phone_palettes,data,sizeof(phone_palettes));
        show_phone_overlay((const uint8_t *)(data+8*256));
    }
    return true;
}

bool videophone_movie(const char *file)
{
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    plaza_close();
    phone_connecting=false;
    phone_movie=plaza_load(file,false,module_buffer,sizeof(module_buffer),screen,512);
    return phone_movie;
}

bool videophone_connect(void)
{
    if (!phone_connecting) return false;
    if (game.scene==0x1a07 || game.scene==0x1a08) {
        phone_connecting=false;
        caller_speaking=katrina_visible=false;
        if (!videophone_movie(game.scene==0x1a07?"MASKON.BIN":"JAMIE.BIN")) return false;
        scene_wait(game.scene==0x1a07?46:30);
        return true;
    }
    scene_wait(8); /* Actor 30 releases the caller graphic controller. */
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    bool napoleon=game.scene==0x1a01;
    if (!videophone_panel(screen,napoleon?"PHONENAP.BIN":game.scene==0x1a05?"PHONEKAT.BIN":"PHONEOFF.BIN")) return false;
    scene_wait(16);
    phone_connecting=false;
    caller_speaking=napoleon;
    return true;
}

bool videophone_disconnect(void)
{
    if (!videophone_visible || (game.scene!=0x1a01 && game.scene!=0x1a02 && game.scene!=0x1a05 && game.scene!=0x1a07 && game.scene!=0x1a08 && game.scene!=0x1a09)) return false;
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    if (!videophone_panel(screen,"PHONEUI.BIN")) return false;
    scene_wait(17); /* Actor 29 holds the restored monitor for 1 + 16 ticks. */
    return true;
}

bool hospital_stair_actor(unsigned actor)
{
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    return plaza_local_clip(actor==21?"QBUTTON.BIN":"QHATCH.BIN",module_buffer,sizeof(module_buffer),screen,512);
}

bool crash_movie(void)
{
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    return crash_play(module_buffer,sizeof(module_buffer),screen,512);
}

static bool row_pan(const char *file,unsigned frames_expected)
{
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    plaza_close();
    size_t size=disc_read(file,module_buffer,sizeof(module_buffer));
    const uint16_t *header=(const uint16_t *)module_buffer;
    if (size<4 || header[0]!=frames_expected || header[1]>256 ||
        size!=4+frames_expected*128+header[1]*384U) return false;
    const uint8_t *frames=module_buffer+4;
    const uint16_t *rows=(const uint16_t *)(frames+frames_expected*128);
    const uint32_t start=video_clock();
    unsigned frame=0;
    for (;;) {
        const uint8_t *map=frames+frame*128;
        for (unsigned y=0;y<128;y++) {
            if (!frame || map[y]!=map[(int)y-128])
                memcpy((void *)(screen+(8+y)*512+32),rows+192*map[y],384);
        }
        if (frame+1==frames_expected) break;
        while (video_clock()-start<=frame) {}
        ++frame;
    }
    return true;
}

bool ceiling_pan(void) { return row_pan("HQCEIL.BIN",192); }
bool church_portrait_pan(void) { return row_pan("A3PAN.BIN",127); }

bool church_transition(bool opening)
{
    extern void fm_effect_stop(void),church_door_sound(void);
    uint16_t *data=(uint16_t *)0x00200000;
    volatile uint16_t *view=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+64+8*512;
    plaza_close();
    fm_effect_stop();
    size_t bytes=disc_read(opening ? "A3OPEN.BIN" : "A3AISLE.BIN",data,0x100000);
    if (bytes<2+192*128*2 || (bytes&1)) return false;
    const uint16_t *end=data+bytes/2;
    unsigned frames=*data++;
    if (frames!=(opening ? 207u : 64u)) return false;
    for (unsigned y=0;y<128;y++,data+=192)
        memcpy((void *)(view+y*512),data,192*2);
    uint32_t start=video_clock();
    for (unsigned frame=1;frame<frames;frame++) {
        while (video_clock()-start<frame) {}
        if (opening && frame==65) church_door_sound();
        if (data==end) return false;
        unsigned count=*data++;
        if ((size_t)(end-data)<count*2) return false;
        for (unsigned i=0;i<count;i++,data+=2) {
            unsigned offset=data[0];
            if (offset%512>=192) return false;
            view[offset]=data[1];
        }
    }
    return data==end;
}

bool hospital_road_clip(const char *name)
{
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    return plaza_load(name,false,module_buffer,sizeof(module_buffer),screen,512);
}

bool cockpit_clip(const char *name)
{
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    return plaza_local_clip(name,module_buffer,sizeof(module_buffer),screen,512);
}

bool office_or_taxi_prepare(bool ceiling)
{
    extern bool office_or_taxi_art(const char *,uint8_t *,size_t);
    return office_or_taxi_art(ceiling?"HFIGHT.BIN":"TFIGHT.BIN",module_buffer,sizeof(module_buffer));
}

bool mika_prepare(void)
{
    extern bool mika_art(uint8_t *,size_t);
    return mika_art(module_buffer,sizeof(module_buffer));
}

bool swarm_prepare(unsigned stage)
{
    extern bool office_or_taxi_art(const char *,uint8_t *,size_t);
    return office_or_taxi_art(stage==14 ? "FINAL14.BIN" : stage==13 ? "FINAL13.BIN" : "SWARM.BIN",module_buffer,sizeof(module_buffer));
}

bool crawler_prepare(void)
{
    extern bool crawler_art(uint8_t *,size_t);
    return crawler_art(module_buffer,sizeof(module_buffer));
}

bool operating_room_actor(unsigned actor)
{
    static bool rising;
    if (actor==29) { rising=false; return true; }
    if (actor==28) { rising=true; return cockpit_clip("QREACH.BIN"); }
    return !rising || cockpit_clip("QFALL.BIN");
}

bool chief_picture(bool repeat)
{
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    return plaza_local_clip(repeat?"CHFRAME.BIN":"CHPHOTO.BIN",module_buffer,sizeof(module_buffer),screen,512);
}

/* The later scanner sound occupies VDP1 texture RAM while Napoleon is on screen. */
static unsigned benson_letter;
bool napoleon_pose(void)
{
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    benson_letter=0;
    return plaza_local_clip("NAPTALK.BIN",module_buffer,sizeof(module_buffer),screen,512);
}

bool benson_actor(unsigned object)
{
    unsigned clip;
    if (object==16 && benson_letter<5) clip=benson_letter++;
    else if (object==19) clip=5;
    else if (object==18) clip=6;
    else if (object==20) clip=7;
    else return false;
    char name[]="BENSON0.BIN";
    name[6]+=(char)clip;
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    return plaza_local_clip(name,module_buffer,sizeof(module_buffer),screen,512);
}

/* These room animations share the scene scratch buffer. */
bool apartment_list_actor(unsigned object,unsigned action)
{
    static const char *const files[]={
        [33]="LIST33.BIN",[34]="LIST34.BIN",[35]="LIST35.BIN",[36]="LIST36.BIN",
        [39]="LIST39.BIN",[40]="LIST40.BIN",[41]="LIST41.BIN",[42]="LIST42.BIN",[44]="LIST44.BIN"
    };
    if (object==40 && action==2) return true;
    if (object>=sizeof(files)/sizeof(files[0]) || !files[object]) return false;
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    return plaza_local_clip(files[object],module_buffer,sizeof(module_buffer),screen,512);
}

bool oleen_door(void)
{
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    return plaza_hospital_door(screen,512);
}

bool oleen_waiting_room(void)
{
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    plaza_wait_frames(82);
    return plaza_load("OLEROOM.BIN",false,module_buffer,sizeof(module_buffer),screen,512);
}

bool act2_title_fade(void)
{
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    return plaza_load("CUREOUT.BIN",false,module_buffer,sizeof(module_buffer),screen,512);
}

bool room202_expression(unsigned object)
{
    const char *file=object==16?"FRGASP.BIN":object==17?"FRCRY.BIN":object==18?"FRREFL.BIN":NULL;
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    return file && plaza_load(file,false,module_buffer,sizeof(module_buffer),screen,512);
}

bool room202_film(const char *file,unsigned frames)
{
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    if (!plaza_load(file,false,module_buffer,sizeof(module_buffer),screen,512)) return false;
    scene_wait(frames-1);
    plaza_close();
    return true;
}

static bool play_transition(const char *file,uint8_t *buffer,size_t capacity)
{
    size_t bytes=disc_read(file,buffer,capacity);
    if (bytes<4) return false;
    const uint16_t *header=(const uint16_t *)buffer;
    unsigned frames=header[0], colors=header[1];
    if (!frames || !colors || colors>256 || bytes<4+2*colors) return false;
    const uint16_t *palette=header+2;
    const uint8_t *cursor=buffer+4+2*colors, *end=buffer+bytes;
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+64+8*512;
    clear_dialogue();
    for (unsigned y=0;y<128;y++)
        for (unsigned x=0;x<192;x++) screen[y*512+x]=0x8000;
    for (unsigned frame=0;frame<frames;frame++) {
        for (;;) {
            if (end-cursor<2) return false;
            unsigned group=(cursor[0]<<8)|cursor[1];
            cursor+=2;
            if (group==0xffff) break;
            if (group>=24*128 || cursor==end) return false;
            unsigned mask=*cursor++;
            volatile uint16_t *dst=screen+(group/24)*512+8*(group%24);
            for (unsigned bit=0;bit<8;bit++)
                if (mask & (1u<<bit)) {
                    if (cursor==end || *cursor>=colors) return false;
                    dst[bit]=palette[*cursor++];
                }
        }
        scene_wait(1);
    }
    return cursor==end;
}

bool gibson_transition(const char *file)
{
    return play_transition(file,module_buffer,sizeof(module_buffer));
}

bool operating_attack(void)
{
    /* The skeleton crosses the full viewport. Its retail pixel deltas use
     * 328 KiB. The operating room keeps its panorama in high work RAM. */
    return play_transition("QATTACK.BIN",(uint8_t *)0x00200000,0x100000);
}

bool scene_draw_at(unsigned command,unsigned instruction)
{
    if (game.module==36 && game.scene==0x2509 && instruction==0x194 && command==0x2508)
        return true; /* Cue 807 already displays the Moscow map. */
    panel_visible = false;
    item_hide();
    volatile uint16_t *screen = (volatile uint16_t *)VDP2_VRAM_ADDR(0, 0) + 32;
    if (command == 0x1a00) return videophone_panel(screen,"PHONEUI.BIN");
    if (videophone_visible && (command == 0x1a01 || command == 0x1a02 || command == 0x1a05 || command == 0x1a07 || command == 0x1a08 || command == 0x1a09)) {
        phone_connecting=true;
        return true;
    }
    if (videophone_visible)
        return command==game.return_scene && videophone_panel(screen,NULL);
    if (command != 0x0901) {
        if (!reception_draw(command, game.module, instruction, module_buffer, sizeof(module_buffer), screen, 512))
            return false;
        if (command == 0x0a00 && game.module == 22)
            return plaza_local_clip("CHOFFICE.BIN", module_buffer, sizeof(module_buffer), screen, 512);
        return true;
    }
    size_t bytes = disc_read("ACT1.BIN", module_buffer, sizeof(module_buffer));
    const uint16_t *words = (const uint16_t *)module_buffer;
    if (bytes < 8) return false;
    unsigned x = words[0], y = words[1], width = words[2], height = words[3];
    if (x + width > 256 || y + height > 224 || bytes != 8 + 2 * width * height)
        return false;
    for (unsigned row = 0; row < 224; row++)
        for (unsigned col = 0; col < 256; col++)
            screen[row*512+col] = row >= y && row < y+height && col >= x && col < x+width
                ? words[4+(row-y)*width+col-x] : 0x8000;
    return true;
}

bool scene_draw(unsigned command) { return scene_draw_at(command,0); }

bool act3_script_clip(unsigned key)
{
    volatile uint16_t *screen=(volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+32;
    return act3_room_clip(key,false,module_buffer,sizeof(module_buffer),screen,512);
}


extern void panel_slots(volatile uint16_t *,unsigned,unsigned,unsigned);
static void title_game(volatile uint16_t *screen)
{
    unsigned occupied=0, selection=0, slot=0;
    bool choosing_slot=false;
    for (unsigned i=0;i<4;i++) if (save_exists(i+1)) occupied|=1u<<i;
    scene_draw(occupied ? 0xd201 : 0xd200);
    while (true) {
        smpc_peripheral_digital_t pad;
        vdp2_sync();
        vdp2_sync_wait();
        smpc_peripheral_process();
        smpc_peripheral_digital_port(1,&pad);
        bool confirm=pad.held.button.c || pad.held.button.start;
        int step=pad.held.button.down-pad.held.button.up;
        if (!choosing_slot) {
            if (occupied && step) {
                selection^=1;
                scene_draw(selection ? 0xd202 : 0xd201);
            }
            if (!confirm) continue;
            if (!selection) {
                prologue_play();
                script_start(&game);
                return;
            }
            choosing_slot=true;
            slot=0;
            while (!(occupied&(1u<<slot))) slot++;
        } else if (pad.held.button.b) {
            choosing_slot=false;
            scene_draw(0xd202);
            continue;
        } else if (step) {
            do { slot=(slot+4+step)%4; } while (!(occupied&(1u<<slot)));
        } else if (confirm && save_load(slot+1,&game)) return;
        else continue;
        panel_slots(screen,512,occupied,slot);
    }
}

void game_display_init(void)
{
    const vdp2_scrn_bitmap_format_t fmt = {
        .scroll_screen = VDP2_SCRN_NBG0, .ccc = VDP2_SCRN_CCC_RGB_32768,
        .bitmap_size = VDP2_SCRN_BITMAP_SIZE_512X256, .bitmap_base = VDP2_VRAM_ADDR(0, 0)
    };
    vdp2_scrn_bitmap_format_set(&fmt);
    vdp2_scrn_priority_set(VDP2_SCRN_NBG0, 6);
    vdp2_vram_cycp_t cycles = {0};
    for (unsigned i = 0; i < 4; i++) {
        cycles.pt[i].t0 = cycles.pt[i].t1 = cycles.pt[i].t2 = cycles.pt[i].t3 =
            VDP2_VRAM_CYCP_CHPNDR_NBG0;
        cycles.pt[i].t4 = cycles.pt[i].t5 = cycles.pt[i].t6 = cycles.pt[i].t7 =
            VDP2_VRAM_CYCP_NO_ACCESS;
    }
    cycles.pt[3].t0=cycles.pt[3].t1=VDP2_VRAM_CYCP_CHPNDR_NBG1;
    vdp2_vram_cycp_set(&cycles);
    vdp2_scrn_scroll_x_set(VDP2_SCRN_NBG0, 0);
    vdp2_scrn_scroll_y_set(VDP2_SCRN_NBG0, 0);
}

int main(void)
{
    game_display_init();
    volatile uint16_t *screen = (volatile uint16_t *)VDP2_VRAM_ADDR(0, 0);
    bool ok = disc_init();
    vdp2_scrn_back_color_set(VDP2_VRAM_ADDR(3, 0x1fffe), RGB1555(1, ok ? 0 : 31, 0, 0));
    if (ok) vdp2_scrn_display_set(VDP2_SCRN_DISP_NBG0);
    vdp2_tvmd_display_res_set(VDP2_TVMD_INTERLACE_NONE, VDP2_TVMD_HORZ_NORMAL_A,
                             VDP2_TVMD_VERT_224);
    vdp2_tvmd_display_set();
    vdp2_sync();
    vdp2_sync_wait();
    voice_init();
    smpc_peripheral_init();
    lightgun_init();
    vdp_sync_vblank_out_set(poll_pad, NULL);
    saves_init();
    title_game(screen+32);
    panel_draw(&game, screen + 32, 512);
    panel_visible = true;
    vdp2_tvmd_display_set();
    while (true) {
        smpc_peripheral_digital_t pad;
        smpc_peripheral_process();
        smpc_peripheral_digital_port(1, &pad);
        int step = pad.held.button.down - pad.held.button.up;
        int horizontal=pad.held.button.right-pad.held.button.left;
        bool password=game.password_input && game.page>=game.line_count;
        bool keypad=game.phone_keypad && game.page>=game.line_count;
        bool aiming=flashlight_aim(game.page>=game.line_count && pad.pressed.button.b,
                                   pad.pressed.button.right-pad.pressed.button.left,
                                   pad.pressed.button.down-pad.pressed.button.up);
        if (!aiming && (step || ((keypad || password) && horizontal) || (password && pad.held.button.start) || pad.held.button.c || pad.held.button.b)) {
            extern void terminal_page_clear(volatile uint16_t *,unsigned);
            terminal_page_clear(screen+32,512);
            if (password) {
                if (pad.held.button.c || pad.held.button.start) {
                    if (game.module==28) {
                        extern void password_list_restore(volatile uint16_t *,unsigned);
                        password_list_restore(screen+32,512);
                    } else if (videophone_visible) phone_paint(0,true);
                    else if (!game.numeric_answer) {
                        extern void restore_answer_background(void);
                        restore_answer_background();
                    }
                }
                script_password(&game,horizontal,step,pad.held.button.c,pad.held.button.b,pad.held.button.start);
            } else if (keypad) script_dial(&game,horizontal,step,pad.held.button.c,pad.held.button.b);
            else script_input(&game,step,pad.held.button.c,pad.held.button.b);
            if (caller_speaking && game.scene==0x1a01) {
                uint16_t *saved=(uint16_t *)VDP2_VRAM_ADDR(3,0);
                for (unsigned y=0; y<mouth_h; ++y) {
                    unsigned pos=(mouth_y+y)*192+mouth_x;
                    memcpy(saved+pos,mouth_closed+y*mouth_w,mouth_w*2);
                    memcpy(saved+192*128+pos,mouth_closed+y*mouth_w,mouth_w*2);
                    memcpy((void *)(screen+(8+mouth_y+y)*512+64+mouth_x),
                           mouth_closed+y*mouth_w,mouth_w*2);
                }
                caller_speaking=false;
            }
            if (game.finished) title_game(screen+32);
            panel_draw(&game, screen + 32, 512);
            panel_visible = true;
        }
        if (game.password_input && game.page>=game.line_count &&
            game.password_length<game.password_limit) {
            unsigned x=32+65+9*game.password_length;
            uint16_t color=password_clock<33?0xffff:0x8000;
            for (unsigned i=0; i<6; ++i) screen[(game.numeric_answer ? 177 : 113)*512+x+i]=color;
            password_clock=(password_clock+1)%66;
        } else password_clock=0;
        fm_effect_tick();
        if (videophone_visible) videophone_tick();
        else scene_tick();
        vdp2_sync();
        vdp2_sync_wait();
    }
}

/* Pad held flags are new presses in Yaul. Pressed flags give the sustained D-pad. */
void range_pad(bool *draw, bool *fire, int *field)
{
    smpc_peripheral_digital_t pad;
    smpc_peripheral_process();
    smpc_peripheral_digital_port(1, &pad);
    *draw = pad.held.button.a;
    *fire = pad.held.button.c;
    *field = 4 + pad.pressed.button.right - pad.pressed.button.left
               + 3*(pad.pressed.button.down - pad.pressed.button.up);
}
