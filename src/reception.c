#include "report.h"
#include "gfx.h"
#include <stdbool.h>
#include <string.h>
#include "disc.h"
#include "drive.h"
#include "scan.h"
#include "city.h"
#include "street.h"
#include "plaza.h"
#include "flashlight.h"

struct transfer { unsigned address, offset, bytes; };
struct sprite { int x, y, width, height; unsigned tile; };
struct map_step { unsigned offset, left, top, width, height, frames; };
struct motion_step { const struct sprite *sprites; unsigned count, frames; };
struct fixture_step { uint8_t op, argument; uint16_t duration; };
struct jordan_portrait { const struct sprite *tiles; unsigned count; const uint16_t *palette; };
struct face_part { unsigned id; const struct sprite *tiles; unsigned count; const struct fixture_step *code; };
struct garden_actor { unsigned id; const struct fixture_step *code; const struct motion_step *poses; };
struct shadow_step { const struct sprite *sprites; unsigned count, frames, sound; };
struct light_pixel { uint16_t position, color; };
struct light_frame { const struct light_pixel *pixels; unsigned count; };
struct arm_step { unsigned pose, frames; int vx, vy; unsigned effect; };
struct motion {
    unsigned object, left, top, right, bottom;
    const struct motion_step *steps;
    unsigned count, loop_start;
};
struct palette_cycle {
    const uint16_t *pixels;
    unsigned count;
    const uint16_t *colors;
    unsigned color_count, frames;
};
struct scene {
    unsigned command;
    const char *file;
    const struct transfer *transfers;
    unsigned transfer_count;
    const struct sprite *sprites;
    unsigned sprite_count;
    const uint16_t *palette;
    const struct motion *motion;
    unsigned scroll_b;
    const struct motion *loop;
    const struct palette_cycle *cycles;
    unsigned cycle_count;
};
#include "reception.h"

static uint8_t tiles[65536];
#define COUNT(array) (sizeof(array) / sizeof((array)[0]))

static unsigned pixel(unsigned tile, unsigned x, unsigned y)
{
    unsigned packed = tiles[(tile & 2047) * 32 + (y & 7) * 4 + (x & 7) / 2];
    return (packed >> ((x & 1) ? 0 : 4)) & 15;
}

static const struct scene *scene;
static const uint16_t *sprite_palette,*background_palette;
static volatile uint16_t *screen;
static unsigned stride, drive_scene, storm_delay;
static bool crash_sequence;
extern void storm_sound(void), storm_tick(void), storm_stop(void);
static bool motion_started;
static bool apartment_window_lit;
static bool gibson_door_visible,garden_active,ivan_door;
static void lisa_entry_tick(void);
static void hostage_tick(void);
static unsigned hostage_x, hostage_mouth, hostage_pause, hostage_lip;
static bool hostage_combat;
static unsigned lisa_entry;
static unsigned freddy_knock_ticks,bathroom_scroll,bathroom_actor;
static bool hotel_return, hotel_map_visible;
static bool freddy_dark,freddy_helper,freddy_panel,freddy_hand,freddy_lisa;
static uint16_t garden_color;
static unsigned pose, ticks, palette_tick, drip_extra;
static uint32_t drip_random=1;
static bool drip_ready;
void drip_bank_ready(void) { drip_ready=true; }
static uint16_t *pose_cache;
static uint16_t *office_cache;
static void garden_open(void);
static void garden_start(unsigned,unsigned);
static bool garden_wait(unsigned);
static void garden_tick(void);
static bool harry_left;
static unsigned engineering_visible;
static struct fixture_actor {
    const struct fixture_step *next;
    unsigned ticks, pose;
    bool signaled;
} fixture_actors[6];
static const uint16_t *phone_pixels;
static unsigned phone_frame, phone_ticks;

static void paint(const struct sprite *sprites, unsigned count,
                   unsigned left, unsigned top, unsigned right, unsigned bottom,
                   volatile uint16_t *dst, unsigned pitch, unsigned dx0, unsigned dy0)
{
    for (size_t i = 0; i < count; i++) {
        const struct sprite *s = &sprites[i];
        int x0 = s->x > (int)left ? s->x : (int)left;
        int x1 = s->x+8*s->width < (int)right ? s->x+8*s->width : (int)right;
        int y0 = s->y > (int)top ? s->y : (int)top;
        int y1 = s->y+8*s->height < (int)bottom ? s->y+8*s->height : (int)bottom;
        if (x0 >= x1) continue;
        for (int dy = y0; dy < y1; ++dy) {
            for (int dx = x0; dx < x1; ++dx) {
                unsigned x = dx-s->x, y = dy-s->y;
                unsigned sx = (s->tile & 0x800) ? 8*s->width-1-x : x;
                unsigned sy = (s->tile & 0x1000) ? 8*s->height-1-y : y;
                unsigned index = pixel(s->tile + sx/8*s->height + sy/8, sx, sy);
                if (index) {
                    unsigned color=((s->tile >> 9) & 48) + index;
                    dst[(dy-dy0)*pitch+dx-dx0] = garden_active && color==31 ? garden_color : sprite_palette[color];
                }
            }
        }
    }
}

static void render(const struct sprite *sprites, unsigned count,
                   unsigned left, unsigned top, unsigned right, unsigned bottom,
                   volatile uint16_t *dst, unsigned pitch, unsigned dx0, unsigned dy0)
{
    for (unsigned y = top; y < bottom; y++) {
        for (unsigned x = left; x < right; x++) {
            uint16_t color = 0x8000;
            for (unsigned plane = 0xc000; plane <= 0xe000; plane += 0x2000) {
                unsigned py = y;
                if (((scene->command >> 8) == 0x19) && (x<32 || x>=224 || y<8 || y>=136)) continue;
                if (scene->scroll_b && plane == 0xc000) {
                    if (x < 32 || x >= 224 || y < 8 || y >= 136) continue;
                    py = (py + scene->scroll_b) & 255;
                }
                unsigned cell = plane + 2 * (32 * (py / 8) + x / 8);
                unsigned word = tiles[cell] * 256u + tiles[cell + 1];
                unsigned index = pixel(word, (word & 0x800) ? ~x : x,
                                       (word & 0x1000) ? ~py : py);
                if (index) color = background_palette[((word >> 9) & 48) + index];
            }
            dst[(y-dy0)*pitch + x-dx0] = color;
        }
    }
    paint(sprites,count,left,top,right,bottom,dst,pitch,dx0,dy0);
}

static unsigned passage_clock, passage_stop, passage_hold;

static void passage_draw(void)
{
    static const unsigned steps[]={4,5,2,3,0,1};
    static const unsigned periods[]={7,6,5,4,3};
    uint16_t *frame=pose_cache+256*128;
    for (unsigned y=0;y<128;y++) {
        unsigned band=y<112 ? 0 : 1+(y-112)/4;
        unsigned left=(32-passage_clock/periods[band])&255;
        unsigned span=256-left;
        if (span>192) span=192;
        const uint16_t *row=pose_cache+y*256;
        memcpy(frame+y*192,row+left,span*2);
        if (span<192) memcpy(frame+y*192+span,row,(192-span)*2);
    }
    unsigned gillian=passage_stop ? (passage_hold ? 4 : 11) : steps[(passage_clock/22)%6];
    unsigned gear=passage_stop ? (passage_stop==2 ? 10 : 6) : 6+(passage_clock/17)%4;
    const struct motion_step *part=passage_poses+gear;
    paint(part->sprites,part->count,32,8,224,136,frame,192,32,8);
    part=passage_poses+gillian;
    paint(part->sprites,part->count,32,8,224,136,frame,192,32,8);
    for (unsigned y=0;y<128;y++)
        memcpy((void *)(screen+(y+8)*stride+32),frame+y*192,192*2);
}

static void passage_open(void)
{
    /* Only plane B scrolls. Plane A masks the margins outside the viewport. */
    for (unsigned y=8;y<136;y++) for (unsigned x=0;x<256;x++) {
        unsigned cell=0xc000+2*(32*(y/8)+x/8);
        unsigned tile=256u*tiles[cell]+tiles[cell+1];
        unsigned index=pixel(tile,tile&0x800 ? ~x : x,tile&0x1000 ? ~y : y);
        pose_cache[(y-8)*256+x]=index ? background_palette[((tile>>9)&48)+index] : 0x8000;
    }
    passage_clock=passage_stop=passage_hold=0;
    passage_draw();
}

static unsigned john_clock, spark_clock, spark_pause, arm_step, arm_ticks;
static int arm_x, arm_y;
static bool john_timer_visible;

static void john_paint(unsigned frame, int x, int y)
{
    const struct motion_step *step = &john_poses[frame];
    for (unsigned i=0; i<step->count; ++i) {
        struct sprite part = step->sprites[i];
        part.x += x;
        part.y += y;
        paint(&part,1,32,8,224,136,screen,stride,0,0);
    }
}

static void john_tick(void)
{
    for (unsigned i=0; i<scene->cycle_count; ++i) {
        const struct palette_cycle *cycle = &scene->cycles[i];
        unsigned elapsed = john_clock > 8 ? john_clock-8 : 0;
        uint16_t color = cycle->colors[(elapsed/cycle->frames)%cycle->color_count];
        for (unsigned n=0; n<cycle->count; ++n) {
            unsigned xy = cycle->pixels[n], x = xy&255, y = xy>>8;
            if (x>=32 && x<224 && y>=8 && y<136) pose_cache[(y-8)*192+x-32]=color;
        }
    }
    for (unsigned y=8; y<136; ++y)
        memcpy((void *)(screen+y*stride+32),pose_cache+(y-8)*192,192*sizeof(uint16_t));
    const unsigned lights[] = {5+(john_clock/10)%5,(john_clock/7)%5};
    for (unsigned i=0; i<COUNT(lights); ++i) {
        const struct light_frame *frame = &john_lights[lights[i]];
        for (unsigned j=0; j<frame->count; ++j) {
            const struct light_pixel *pixel = &frame->pixels[j];
            screen[(pixel->position>>8)*stride+(pixel->position&255)] = scene->palette[pixel->color];
        }
    }
    static const unsigned spark[] = {4,5,6,7,6,5};
    if (spark_clock<48) john_paint(spark[(spark_clock/2)%6],0,0);
    if (++spark_clock>=48+spark_pause) {
        drip_random = drip_random*1664525u+1013904223u;
        spark_pause = 1+(drip_random>>16)%32;
        spark_clock = 0;
    }
    ++john_clock;
    if (john_timer_visible) john_paint(3,0,0);
    if (!motion_started || arm_step>=COUNT(john_arm)) return;
    const struct arm_step *step = &john_arm[arm_step];
    if (!arm_ticks && step->effect) {
        extern bool fm_effect_start(unsigned);
        fm_effect_start(step->effect);
    }
    arm_x += step->vx;
    arm_y += step->vy;
    john_paint(step->pose,arm_x,arm_y);
    if (++arm_ticks>=step->frames) { arm_ticks=0; ++arm_step; }
}

struct club_sprite {
    const struct garden_actor *actor;
    const struct motion_step *pose;
    unsigned pc, ticks;
    bool paused;
};
static struct club_sprite club_sprites[11];
static unsigned club_count,club_random;
static int club_left,club_top,club_right,club_bottom;

static void club_dirty(const struct motion_step *pose)
{
    if (!pose) return;
    for (unsigned i=0;i<pose->count;i++) {
        const struct sprite *s=&pose->sprites[i];
        if (s->x<club_left) club_left=s->x;
        if (s->y<club_top) club_top=s->y;
        int r=s->x+8*s->width, b=s->y+8*s->height;
        if (r>club_right) club_right=r;
        if (b>club_bottom) club_bottom=b;
    }
}

static void club_pose(struct club_sprite *actor,const struct motion_step *pose)
{
    if (actor->pose==pose) return;
    club_dirty(actor->pose);
    club_dirty(pose);
    actor->pose=pose;
}

static void club_advance(struct club_sprite *s)
{
    for (;;) {
        const struct fixture_step cmd=s->actor->code[s->pc++];
        if (cmd.op==0x93 || cmd.op==0x80) {
            if (cmd.op==0x80) --s->pc;
            s->paused=true;
            return;
        }
        if (cmd.op==0x81) { s->pc=cmd.argument; continue; }
        if (cmd.op==0x84 || cmd.op==0x85) continue; /* Position is baked into each eye pose. */
        if (cmd.op==0x9d) {
            extern bool fm_effect_start(unsigned);
            fm_effect_start(cmd.argument);
            continue;
        }
        if (cmd.op==0x95) {
            for (unsigned j=0;j<club_count;j++)
                if (club_sprites[j].actor->id==cmd.argument) {
                    club_sprites[j].paused=true;
                    club_pose(&club_sprites[j],NULL);
                }
            continue;
        }
        club_pose(s,cmd.op==0x97 ? NULL : s->actor->poses+cmd.op);
        if (cmd.argument==255) {
            unsigned lo=cmd.duration>>8, hi=cmd.duration&255;
            club_random=1664525u*club_random+1013904223u;
            s->ticks=lo+(club_random>>16)%(hi-lo+1);
        } else s->ticks=cmd.duration;
        if (!s->ticks) s->ticks=1;
        return;
    }
}

struct room_cycle { uint8_t base,size,delay,count; uint16_t colors[80]; };
struct room_lights {
    uint16_t delay,cycles,pixels,reserved;
    struct room_cycle cycle[3];
    struct { uint16_t offset,index; } pixel[];
};
static const struct room_lights *lights;
static unsigned light_delay,light_ticks[3],light_phases[3];
static uint16_t light_colors[64];
static void room_light_tick(void)
{
    if (!lights || (light_delay && --light_delay)) return;
    bool changed=false;
    for (unsigned i=0;i<lights->cycles;i++) {
        const struct room_cycle *c=lights->cycle+i;
        if (light_ticks[i] && --light_ticks[i]) continue;
        memcpy(light_colors+c->base,c->colors+c->size*light_phases[i],2*c->size);
        light_phases[i]=(light_phases[i]+1)%c->count;
        light_ticks[i]=c->delay;
        changed=true;
    }
    if (!changed) return;
    for (unsigned i=0;i<lights->pixels;i++)
        pose_cache[lights->pixel[i].offset]=light_colors[lights->pixel[i].index];
    club_left=32;club_top=8;club_right=224;club_bottom=136;
}

static void club_tick(void)
{
    room_light_tick();
    for (unsigned i=0;i<club_count;i++) {
        struct club_sprite *s=&club_sprites[i];
        if (!s->paused && (!s->ticks || !--s->ticks)) club_advance(s);
    }
    int l=club_left<32?32:club_left, r=club_right>224?224:club_right;
    int t=club_top<8?8:club_top, b=club_bottom>136?136:club_bottom;
    if (l<r && t<b) {
        extern void restore_scene_beneath_item(void),refresh_scene_item(void);
        restore_scene_beneath_item();
        for (int y=t;y<b;y++)
            memcpy((void *)(screen+y*stride+l),pose_cache+(y-8)*192+l-32,(r-l)*2);
        for (unsigned i=club_count;i--;) {
            const struct motion_step *pose=club_sprites[i].pose;
            if (pose) paint(pose->sprites,pose->count,l,t,r,b,screen,stride,0,0);
        }
        refresh_scene_item();
    }
    club_left=224;club_top=136;club_right=32;club_bottom=8;
}
/* The H04 menu first slides six choices into view. A selection resumes
 * one controller at its pause and moves that part to the composite face. */
struct face_state {
    int x,y,vx,vy;
    unsigned pc,ticks;
    bool active,visible,paused,signaled;
};
static struct face_state faces[COUNT(montage_parts)];
static bool face_dirty,face_scanning;
static bool result_revealed;
static unsigned montage_cursor_ticks;
static void face_tick(void)
{
    for (unsigned i=0;i<COUNT(faces);i++) {
        struct face_state *f=faces+i;
        if (!f->active || f->paused) continue;
        while (!f->ticks && !f->paused) {
            struct fixture_step step=montage_parts[i].code[f->pc++];
            if (step.op<128) {
                face_dirty|=!f->visible;
                f->visible=true;
                f->ticks=step.duration ? step.duration : 1;
            } else switch (step.op) {
            case 0x81: f->pc=step.argument; break;
            case 0x84: f->x=(int16_t)step.duration; break;
            case 0x85: f->y=(int16_t)step.duration; break;
            case 0x86: f->vx=(int16_t)step.duration; break;
            case 0x87: f->vy=(int16_t)step.duration; break;
            case 0x93: f->paused=true; break;
            case 0x98: f->signaled=true; break;
            case 0x9d: { extern bool fm_effect_start(unsigned); fm_effect_start(step.argument); break; }
            }
        }
        if (!f->paused) {
            --f->ticks;
            f->x+=f->vx; f->y+=f->vy;
            face_dirty |= f->vx!=0 || f->vy!=0;
        }
    }
    montage_cursor_ticks=(montage_cursor_ticks+1)%42;
    if (!face_dirty) {
        if (montage_cursor_ticks==0)
            paint(montage_cursor,COUNT(montage_cursor),208,128,216,136,screen,stride,0,0);
        if (montage_cursor_ticks==21)
            for (unsigned y=128;y<136;y++)
                memcpy((void *)(screen+y*stride+208),pose_cache+(y-8)*192+176,16);
        return;
    }
    face_dirty=false;
    for (unsigned y=0;y<128;y++)
        memcpy((void *)(screen+(y+8)*stride+32),pose_cache+y*192,192*2);
    if (montage_cursor_ticks<21)
        paint(montage_cursor,COUNT(montage_cursor),208,128,216,136,screen,stride,0,0);
    if (face_scanning) paint(montage_scan,COUNT(montage_scan),32,8,224,136,screen,stride,0,0);
    for (unsigned i=COUNT(faces);i--;) {
        const struct face_state *f=faces+i;
        const struct face_part *part=montage_parts+i;
        if (!f->visible) continue;
        for (unsigned j=0;j<part->count;j++) {
            struct sprite tile=part->tiles[j];
            tile.x+=f->x+(face_scanning?64:0); tile.y+=f->y-(face_scanning?32:0);
            paint(&tile,1,32,8,224,136,screen,stride,0,0);
        }
    }
}
struct shop_pixel { uint16_t xy; uint8_t actor, pad, color[6]; };
struct shop_lights {
    uint16_t count, delays[9];
    uint8_t cycles[2][4];
    uint16_t palette[100];
    struct shop_pixel pixels[];
};
static const struct shop_lights *shop_lights;
static unsigned shop_timers[4], shop_phases[4];
static uint16_t shop_colors[64];
static void shop_lights_tick(void)
{
    if (!shop_lights) return;
    bool dirty=false;
    for (unsigned i=0;i<4;i++) {
        if (shop_timers[i] && --shop_timers[i]) continue;
        unsigned count=i==0 ? 3 : i==1 ? 6 : shop_lights->cycles[i-2][3];
        unsigned phase=shop_phases[i]=(shop_phases[i]+1)%count;
        if (i<2) shop_timers[i]=shop_lights->delays[(i==0?0:3)+phase];
        else {
            const uint8_t *cycle=shop_lights->cycles[i-2];
            shop_timers[i]=cycle[2];
            memcpy(shop_colors+cycle[0],shop_lights->palette+(i==2?0:4)+phase*cycle[1],2*cycle[1]);
        }
        dirty=true;
    }
    if (!dirty) return;
    extern void restore_scene_beneath_item(void),refresh_scene_item(void);
    restore_scene_beneath_item();
    for (unsigned i=0;i<shop_lights->count;i++) {
        const struct shop_pixel *px=&shop_lights->pixels[i];
        unsigned pose=px->actor ? shop_phases[px->actor-17] : 0;
        screen[(px->xy>>8)*stride+(px->xy&255)]=shop_colors[px->color[pose]];
    }
    refresh_scene_item();
}
static int shop_camera;
static bool shop_mask_visible[2];
static void shop_paint(void)
{
    for (unsigned y=0;y<128;y++)
        memcpy((void *)(screen+(y+8)*stride+32),pose_cache+y*256+32-shop_camera,192*2);
}
static void shop_room(void)
{
    render(scene->sprites,scene->sprite_count,0,8,256,136,pose_cache,256,0,8);
    if (shop_mask_visible[1])
        paint(shop_mask_33,COUNT(shop_mask_33),0,8,256,136,pose_cache,256,0,8);
    if (shop_mask_visible[0])
        paint(shop_mask_32,COUNT(shop_mask_32),0,8,256,136,pose_cache,256,0,8);
    shop_paint();
}
static void pan_frame(unsigned offset)
{
    for (unsigned y=0;y<128;y++)
        memcpy((void *)(screen+(y+8)*stride+32),pose_cache+y*224+offset,192*2);
}

static unsigned operating_scroll;
static void operating_draw(bool skeleton)
{
    render(operating_skeleton,skeleton ? COUNT(operating_skeleton) : 0,
           32,8,256,136,pose_cache,224,32,8);
    pan_frame(operating_scroll);
}

static void bathroom_draw(void)
{
    const struct sprite *sprites=bathroom_actor==16?bathroom_16:bathroom_17;
    unsigned count=bathroom_actor==16?COUNT(bathroom_16):COUNT(bathroom_17);
    render(sprites,bathroom_actor?count:0,32,8,256,136,pose_cache,224,32,8);
    pan_frame(bathroom_scroll);
}

static unsigned ending_scene,briefing_track,queens_switches;

static unsigned queens_room,queens_fade;
static bool queens_returning;

static void queens_fade_tick(void)
{
    if (!queens_fade) return;
    /* DATA_Q3 actor 35 subtracts one Genesis intensity step every 12 ticks. */
    if ((--queens_fade)%12) return;
    uint16_t level[32];
    for (unsigned i=0;i<32;i++) {
        unsigned component=(i*7+15)/31;
        level[i]=component ? (component-1)*255/7*31/255 : 0;
    }
    for (unsigned y=8;y<136;y++) for (unsigned x=32;x<224;x++) {
        unsigned c=screen[y*stride+x];
        screen[y*stride+x]=0x8000 | level[c&31] | (level[(c>>5)&31]<<5) | (level[(c>>10)&31]<<10);
    }
}

static void queens_waiting_room(void)
{
    render(NULL,0,32,8,224,136,screen,stride,0,0);
    if (queens_switches & 1) paint(queens_switch1,COUNT(queens_switch1),32,8,224,136,screen,stride,0,0);
    if (queens_switches & 2) paint(queens_switch2,COUNT(queens_switch2),32,8,224,136,screen,stride,0,0);
    if (queens_switches & 4) paint(queens_switch3,COUNT(queens_switch3),32,8,224,136,screen,stride,0,0);
}

bool reception_draw(unsigned command, unsigned module_id, unsigned instruction, uint8_t *module, size_t capacity,
                    volatile uint16_t *destination, unsigned pitch)
{
    if (crash_sequence && command>=0x2202 && command<=0x2209)
        return true;
    crash_sequence=false;
    if (module_id==33 && ((briefing_track==13 && command>=0x1501 && command<=0x1503) ||
                         (briefing_track==14 && command==0x1504))) return true;
    if (module_id==38 && ((briefing_track==16 && (instruction==0xb44 || instruction==0xb4c)) ||
                         (briefing_track==17 && instruction>=0xb66 && instruction<=0xb82))) return true;
    if (module_id==36 && briefing_track==15 && command>=0x260c && command<=0x260f) return true;
    if (briefing_track==12 && command==0x1300) return true;
    if (briefing_track==21 && command>=0x1f01 && command<=0x1f0c) return true;
    if (briefing_track && command>=0x1100 && command<=0x1111 && command!=0x1102 && command!=0x1110)
        return true;
    briefing_track=0;
    hotel_return=module_id==32;
    hotel_map_visible=false;
    storm_stop();
    storm_delay=drip_extra=0;
    drip_ready=false;
    screen = destination;
    stride = pitch;
    scene = NULL;
    garden_active=false;
    club_count=0;
    lights=NULL;
    shop_lights=NULL;
    bool apartment_entry=command==0x1c04 && drive_scene==0x1c03;
    queens_returning=command==0x1d05 && queens_room!=0;
    flashlight_close();
    queens_switches=queens_fade=0;
    queens_room=command==0x1d0a ? 1 : command==0x1d0b ? 2 : command==0x1d0d ? 3 : 0;
    apartment_window_lit=false;
    gibson_door_visible=false;
    drive_scene=command==0x1c03 ? command : 0;
    scan_close();
    city_close();
    street_close();
    plaza_close();
    report_close();
    hostage_combat=false;
    lisa_entry=0;
    freddy_knock_ticks=0;
    freddy_dark=freddy_helper=freddy_panel=freddy_hand=freddy_lisa=false;
    ivan_door=command==0x1703;
    ending_scene=0;
    if (command==0x2301) return plaza_load("TAXIWON.BIN",true,module,capacity,screen,stride);
    if (command==0x2300) return plaza_load("TAXIRIDE.BIN",true,module,capacity,screen,stride);
    if (command==0x2400) return plaza_load("TUNDARK.BIN",true,module,capacity,screen,stride);
    if (command==0x2401) return plaza_load("TUNEXIT.BIN",true,module,capacity,screen,stride);
    if (command==0x2404) return plaza_load("TUNLADR.BIN",true,module,capacity,screen,stride);
    if (command==0x2402) return plaza_load("TUNWALK.BIN",true,module,capacity,screen,stride);
    if (command==0x1f10) return plaza_load("QVISIN.BIN",true,module,capacity,screen,stride);
    if (command>=0x1f0d && command<=0x1f0f) {
        static const char *const views[]={"QVISD.BIN","QVISE.BIN","QVISF.BIN"};
        return plaza_load(views[command-0x1f0d],true,module,capacity,screen,stride);
    }
    if (command==0x1f00) {
        briefing_track=21;
        return plaza_briefing_load(21) && plaza_load("QVISEND.BIN",true,module,capacity,screen,stride);
    }
    if (command>=0x1e03 && command<=0x1e07) {
        char file[]="QRCIN3.BIN";
        file[5]+=(char)(command-0x1e03);
        return plaza_load(file,true,module,capacity,screen,stride);
    }
    if (command==0x1d03) return plaza_load("QTALK.BIN",true,module,capacity,screen,stride);
    if (command==0x1d0c) return plaza_load("QLAB.BIN",true,module,capacity,screen,stride);
    if (command==0x1d01) return plaza_load("QHEAD.BIN",true,module,capacity,screen,stride);
    if (command==0x1d0e) return plaza_load("QSTAIRS.BIN",true,module,capacity,screen,stride);
    if (command==0x2200) {
        briefing_track=10;
        return plaza_briefing_load(10) && plaza_load("CHASEIN.BIN",true,module,capacity,screen,stride);
    }
    if (command==0x2201) return plaza_local_clip("COCKPIT.BIN",module,capacity,screen,stride);
    if (command==0x2204) return plaza_load("CARROAD.BIN",true,module,capacity,screen,stride);
    if (command==0x2203) return plaza_load("CARDEST.BIN",true,module,capacity,screen,stride);
    if (command==0x1102 || command==0x1110) {
        briefing_track=command==0x1102?8:9;
        if (!plaza_briefing_load(briefing_track)) return false;
        return briefing_track==9 || plaza_load("BRIEFING.BIN",true,module,capacity,screen,stride);
    }
    if (command==0x1904) {
        /* The end-of-act save prompt clears the picture and the dialogue area. */
        for (unsigned y=0;y<224;y++)
            for (unsigned x=0;x<256;x++) screen[y*stride+x]=0x8000;
        return true;
    }
    if (queens_room) {
        static const char *const rooms[]={"QROOM1.BIN","QROOM2.BIN","QROOM3.BIN"};
        return plaza_load(rooms[queens_room-1],true,module,capacity,screen,stride);
    }
    if (command==0x1b05) return plaza_load("NAPSHOW.BIN",true,module,capacity,screen,stride);
    if (command==0x1c06 || command==0x1c07) return plaza_apartment_film(command==0x1c07,screen,stride);
    if (command==0x1c00) return plaza_load("APTNEON.BIN",true,module,capacity,screen,stride);
    if (command==0x1600) return street_open(screen,stride,module_id==33 ? "HQCITY.BIN" : "STREET.BIN",module_id==33);
    if (module_id==33 && (command==0x1506 || command==0x1201 || command==0x1400)) {
        const char *file=command==0x1506?"ALHALL.BIN":command==0x1201?"LOBBYIN.BIN":"MIKAIN.BIN";
        return plaza_load(file,true,module,capacity,screen,stride);
    }
    if (command==0x1202 && module_id==33) return plaza_load("SHUTIN.BIN",true,module,capacity,screen,stride);
    if (module_id==33 && command>=0x0a00 && command<=0x0e02 && (command&255)<4) {
        static const char *const rooms[][4]={
            {"HQA00.BIN",NULL,"HQA02.BIN","HQA03.BIN"},
            {"HQB00.BIN","HQB01.BIN",NULL,NULL},
            {"HQC00.BIN",NULL,NULL,"HQC03.BIN"},
            {"HQD00.BIN","HQD01.BIN",NULL,NULL},
            {NULL,"HQE01.BIN","HQE02.BIN",NULL}
        };
        const char *file=rooms[(command>>8)-10][command&255];
        if (file) return plaza_load(file,true,module,capacity,screen,stride);
    }
    if (module_id==33 && command==0x1500) {
        briefing_track=13;
        return plaza_briefing_load(13) && plaza_load("RESCIN.BIN",true,module,capacity,screen,stride);
    }
    if (module_id==33 && command==0x1505)
        return plaza_load("RESCOUT.BIN",false,module,capacity,screen,stride);
    if (command==0x1300 && module_id==33) return plaza_load("HALLMENU.BIN",true,module,capacity,screen,stride);
    if (command==0x1301 && module_id==33) {
        briefing_track=12;
        return plaza_briefing_load(12);
    }
    if (command==0x1302 && module_id==33) return plaza_load("HQHALL.BIN",true,module,capacity,screen,stride);
    if (command==0x1200 && module_id==33) return plaza_load("HQBOOTH.BIN",true,module,capacity,screen,stride);
    if (module_id==36 && command>=0x2500 && command<=0x2509) {
        /* A save restore has no draw instruction. Use the first matching camera. */
        static const unsigned first[]={0x2bf,0xdb,0x227,0x110,0x53,0xa1,0x1e8,0x1b5,0x194,0x6d};
        return act3_room_clip(instruction ? instruction : first[command-0x2500],
                              true,module,capacity,screen,stride);
    }
    if (module_id==36 && command==0x260b) {
        briefing_track=15;
        return plaza_briefing_load(15) && plaza_load("A3CDIN.BIN",true,module,capacity,screen,stride);
    }
    if (module_id==36 && command>=0x2600 && command<=0x260a) {
        static const unsigned first[]={0x60f,0x3c7,0x62d,0x61e,0x427,0x756,0x77e,0x3ef,0x5bf,0x63c,0x71c};
        return act3_room_clip(instruction ? instruction : first[command-0x2600],
                              true,module,capacity,screen,stride);
    }
    if (module_id==36 && command==0x1603) return street_open(screen,stride,"ACT3CITY.BIN",false);
    if (module_id==36 && command==0x1602) return plaza_load("ACT3IN.BIN",true,module,capacity,screen,stride);
    if (command==0x1601) return plaza_load("CUREIN.BIN",true,module,capacity,screen,stride);
    if (command>=0x0604 && command<=0x060a) {
        static const uint8_t sections[]={0,2,4,3,5,6,7};
        ending_scene=command;
        return plaza_ending(sections[command-0x0604],screen,stride);
    }
    if (command==0x0602) return plaza_load("FRSHOT.BIN",true,module,capacity,screen,stride);
    if (command==0x0600) return plaza_load("FRMIRROR.BIN",true,module,capacity,screen,stride);
    if (command==0x050a) return plaza_load("FRFALL.BIN",true,module,capacity,screen,stride);
    if (command==0x0508 || command==0x0509)
        return plaza_load(command==0x0508?"FRSHOW.BIN":"FRFACE.BIN",true,module,capacity,screen,stride);
    if (ivan_door) return plaza_open(command,module,capacity,screen,stride);
    if (command==0x070e) return report_open(module,capacity,screen,stride);
    if (command==0x0100 || command==0x0102)
        return plaza_load(command==0x0100?"OLEEN.BIN":"OLEIN.BIN",true,module,capacity,screen,stride);
    if (command<=1 || command==3) return plaza_open(command,module,capacity,screen,stride);
    if (command>=0x1000 && command<=0x1003) return city_open(command&3,screen,stride);
    if (command>=0x190b && command<=0x190d)
        return scan_open(command, module, capacity, screen, stride);
    if (command==0x2101) return plaza_mika_call(module,capacity,screen,stride);
    if (command==0x2103) {
        drive_scene=command;
        return true;
    }
    if (module_id == 38 && ((instruction == 0xb56 && command == 0x3301) ||
                            (instruction == 0xd64 && command == 0x3306))) {
        briefing_track = instruction == 0xb56 ? 17 : 18;
        const char *entrance = briefing_track == 17 ? "A3EB56.BIN" : "A3ED64.BIN";
        return plaza_briefing_load(briefing_track) &&
               plaza_load(entrance, true, module, capacity, screen, stride);
    }
    if (module_id==38) {
        static const struct { unsigned pc,scene; const char *file; } ending_views[]={
            {0x6,0x2a05,"A3ENDIN.BIN"},
            {0x61,0x2a02,"A3ENDTWO.BIN"},
            {0xad,0x2a01,"A3E0AD.BIN"},
            {0xe7,0x2a02,"A3E0E7.BIN"},
            {0x10d,0x2a04,"A3E10D.BIN"},
            {0x152,0x2a00,"A3E152.BIN"},
            {0x180,0x2a06,"A3E180.BIN"},
            {0x1c8,0x2a07,"A3E1C8.BIN"},
            {0x1ef,0x2a02,"A3E1EF.BIN"},
            {0x1fd,0x2a06,"A3E1FD.BIN"},
            {0x21b,0x2a03,"A3E21B.BIN"},
            {0x24e,0x2a02,"A3E24E.BIN"},
            {0x276,0x2b02,"A3E276.BIN"},
            {0x299,0x2b04,"A3E299.BIN"},
            {0x2ce,0x2b01,"A3E2CE.BIN"},
            {0x2e0,0x2b03,"A3E2E0.BIN"},
            {0x2f7,0x2b05,"A3E2F7.BIN"},
            {0x31b,0x2b00,"A3E31B.BIN"},
            {0x35a,0x2c06,"A3E35A.BIN"},
            {0x376,0x2c05,"A3E376.BIN"},
            {0x39f,0x2c01,"A3E39F.BIN"},
            {0x3ce,0x2c02,"A3E3CE.BIN"},
            {0x3e4,0x2c00,"A3E3E4.BIN"},
            {0x40b,0x2c03,"A3E40B.BIN"},
            {0x42b,0x2c04,"A3E42B.BIN"},
            {0x445,0x2d03,"A3E445.BIN"},
            {0x468,0x2d04,"A3E468.BIN"},
            {0x495,0x2d03,"A3E495.BIN"},
            {0x4b0,0x2d02,"A3E4B0.BIN"},
            {0x4d5,0x2d01,"A3E4D5.BIN"},
            {0x4e5,0x2d03,"A3E4E5.BIN"},
            {0x514,0x2d00,"A3E514.BIN"},
            {0x559,0x2e05,"A3E559.BIN"},
            {0x57b,0x2e00,"A3E57B.BIN"},
            {0x58f,0x2e04,"A3E58F.BIN"},
            {0x5b6,0x2e02,"A3E5B6.BIN"},
            {0x5d0,0x2e05,"A3E5D0.BIN"},
            {0x5ec,0x2e03,"A3E5EC.BIN"},
            {0x60c,0x2e05,"A3E60C.BIN"},
            {0x62a,0x2e01,"A3E62A.BIN"},
            {0x665,0x2e03,"A3E665.BIN"},
            {0x673,0x2e02,"A3E673.BIN"},
            {0x683,0x2f04,"A3E683.BIN"},
            {0x697,0x2f01,"A3E697.BIN"},
            {0x6b8,0x2f00,"A3E6B8.BIN"},
            {0x6e6,0x2f02,"A3E6E6.BIN"},
            {0x71e,0x2f04,"A3E71E.BIN"},
            {0x744,0x2f00,"A3E744.BIN"},
            {0x76e,0x2f03,"A3E76E.BIN"},
            {0x77c,0x2f04,"A3E77C.BIN"},
            {0x79a,0x3003,"A3E79A.BIN"},
            {0x7b4,0x3002,"A3E7B4.BIN"},
            {0x7d4,0x3001,"A3E7D4.BIN"},
            {0x7e8,0x3000,"A3E7E8.BIN"},
            {0x7fc,0x3004,"A3E7FC.BIN"},
            {0x80a,0x3005,"A3E80A.BIN"},
            {0x814,0x3006,"A3E814.BIN"},
            {0x836,0x3001,"A3E836.BIN"},
            {0x84a,0x3004,"A3E84A.BIN"},
            {0x854,0x3006,"A3E854.BIN"},
            {0x882,0x3108,"A3E882.BIN"},
            {0x8a1,0x3104,"A3E8A1.BIN"},
            {0x8ad,0x3103,"A3E8AD.BIN"},
            {0x8e3,0x3100,"A3E8E3.BIN"},
            {0x8f5,0x3107,"A3E8F5.BIN"},
            {0x92b,0x3105,"A3E92B.BIN"},
            {0x937,0x3101,"A3E937.BIN"},
            {0x950,0x3102,"A3E950.BIN"},
            {0x968,0x3106,"A3E968.BIN"},
            {0x98a,0x3107,"A3E98A.BIN"},
            {0x99e,0x3206,"A3E99E.BIN"},
            {0x9ac,0x3204,"A3E9AC.BIN"},
            {0x9d8,0x320a,"A3E9D8.BIN"},
            {0x9e6,0x3205,"A3E9E6.BIN"},
            {0x9f0,0x3203,"A3E9F0.BIN"},
            {0x9fe,0x3209,"A3E9FE.BIN"},
            {0xa12,0x3206,"A3EA12.BIN"},
            {0xa26,0x3208,"A3EA26.BIN"},
            {0xa52,0x3209,"A3EA52.BIN"},
            {0xa71,0x3204,"A3EA71.BIN"},
            {0xa8f,0x3203,"A3EA8F.BIN"},
            {0xa9d,0x3208,"A3EA9D.BIN"},
            {0xaac,0x3200,"A3EAAC.BIN"},
            {0xaba,0x3204,"A3EABA.BIN"},
            {0xac8,0x3203,"A3EAC8.BIN"},
            {0xada,0x3206,"A3EADA.BIN"},
            {0xae8,0x3203,"A3EAE8.BIN"},
            {0xb0b,0x3207,"A3EB0B.BIN"},
            {0xb1f,0x3200,"A3EB1F.BIN"},
            {0xb8c,0x3305,"A3EB8C.BIN"},
            {0xd6e,0x3307,"A3ED6E.BIN"},
            {0xe28,0x3308,"A3EE28.BIN"},
        };
        for (unsigned i=0;i<COUNT(ending_views);++i)
            if (command==ending_views[i].scene && instruction==ending_views[i].pc)
                return plaza_load(ending_views[i].file,true,module,capacity,screen,stride);
    }
    if (module_id==37 && ((command>=0x2800 && command<=0x2806) || (command>=0x2900 && command<=0x2904))) {
        static const struct { unsigned instruction, scene; const char *file; } shots[]={
            {0x8cc,0x2806,"A3CYL.BIN"},
            {0x94a,0x2803,"A3RETURN.BIN"},
            {0xad0,0x2805,"A3DAD0.BIN"},
            {0xb0a,0x2801,"A3DB0A.BIN"},
            {0xb18,0x2803,"A3DB18.BIN"},
            {0xb56,0x2800,"A3DB56.BIN"},
            {0xb68,0x2802,"A3DB68.BIN"},
            {0xb7e,0x2803,"A3DB7E.BIN"},
            {0xbb2,0x2800,"A3DBB2.BIN"},
            {0xbc8,0x2802,"A3DBC8.BIN"},
            {0xbe6,0x2800,"A3DBE6.BIN"},
            {0xbf6,0x2802,"A3DBF6.BIN"},
            {0xc19,0x2900,"A3DC18.BIN"},
            {0xc40,0x2901,"A3DC40.BIN"},
            {0xc99,0x2902,"A3DC99A.BIN"},
            {0xcf0,0x2903,"A3DCF0A.BIN"},
            {0xf13,0x2904,"A3FAILIN.BIN"},
            {0xf65,0x2900,"A3RIN.BIN"},
            {0xf7e,0x2901,"A3RHALL1.BIN"},
        };
        for (unsigned i=0;i<COUNT(shots);i++)
            if (shots[i].scene==command && (!instruction || shots[i].instruction==instruction))
                return plaza_load(shots[i].file,true,module,capacity,screen,stride);
    }
    if (module_id==37 && command==0x2804)
        return plaza_load("A3CULT.BIN",true,module,capacity,screen,stride);
    if (module_id==37 && command>=0x2702 && command<=0x2704) {
        const char *file=command==0x2704 ? "A3FRAME.BIN" : !instruction ? "A3REARID.BIN" :
                         command==0x2702 ? "A3BACK.BIN" : "A3REAR.BIN";
        return plaza_load(file,true,module,capacity,screen,stride);
    }
    if (module_id==37 && command==0x2701) {
        extern bool church_transition(bool);
        if (instruction) return church_transition(false);
        return plaza_load("A3SMALL.BIN",true,module,capacity,screen,stride);
    }
    if (module_id==37 && command==0x2700)
        return plaza_load("A3CHURCH.BIN",true,module,capacity,screen,stride);
    if (module_id==37 && (command==0x2003 || command==0x2002 || command==0x2004)) {
        const char *file=command==0x2003 ? "A3BOARD.BIN" :
                         command==0x2002 ? "A3CRUISE.BIN" : "A3LAND.BIN";
        return plaza_load(file,true,module,capacity,screen,stride);
    }
    if (command==0x2002 || command==0x2004) {
        drive_scene=command;
        return command==0x2002 || drive_load(false);
    }
    for (size_t i = 0; i < COUNT(scenes); i++)
        if (scenes[i].command == command) scene = &scenes[i];
    if (!scene) return false;
    background_palette=sprite_palette=scene->palette;
    size_t bytes = disc_read(scene->file, module, capacity);
    if (!bytes) return false;
    memset(tiles, 0, sizeof(tiles));
    for (size_t i = 0; i < scene->transfer_count; i++) {
        const struct transfer *t = &scene->transfers[i];
        if (t->offset > bytes || t->bytes > bytes - t->offset ||
            gfx_unpack(module + t->offset, t->bytes, tiles + t->address,
                       sizeof(tiles) - t->address) != t->bytes) return false;
    }
    if (command == 0x0f03) {
        if (disc_read("PHONE.BIN",module,capacity) != phone_bytes) return false;
        phone_pixels = (const uint16_t *)module;
        phone_frame = phone_ticks = 0;
    }
    motion_started = false;
    harry_left = false;
    engineering_visible = 0;
    memset(fixture_actors, 0, sizeof(fixture_actors));
    for (unsigned i=0; i<COUNT(fixture_actors); ++i) fixture_actors[i].pose=COUNT(fixture_poses);
    pose = ticks = palette_tick = 0;
    if (command==0x2403) {
        if (capacity<(256+192)*128*sizeof(uint16_t)) return false;
        for (unsigned y=0;y<224;y++)
            for (unsigned x=0;x<256;x++) screen[y*stride+x]=0x8000;
        pose_cache=(uint16_t *)module;
        passage_open();
    } else if (hotel_return && command==0x0503) {
        render(NULL,0,0,0,256,224,screen,stride,0,0);
    } else {
        render(scene->sprites, scene->sprite_count, 0, 0, 256, 224, screen, stride, 0, 0);
        if (hotel_return && command==0x0500)
            paint(hotel_cars,COUNT(hotel_cars),32,8,224,136,screen,stride,0,0);
    }
    if (apartment_entry) {
        extern bool gibson_transition(const char *);
        return gibson_transition("APTROOM.BIN");
    }
    result_revealed=false;
    if (command==0x1d02) {
        if (capacity<224*128*sizeof(uint16_t)) return false;
        pose_cache=(uint16_t *)module;
        operating_scroll=0;
        operating_draw(false);
    }
    if (command==0x0505) {
        if (capacity<224*128*sizeof(uint16_t)) return false;
        pose_cache=(uint16_t *)module;
        bathroom_scroll=0;
        bathroom_actor=hotel_return ? 17 : 0;
        bathroom_draw();
    }
    if (command==0x0c02) {
        face_scanning=false;
        montage_cursor_ticks=0;
        if (capacity<192*128*sizeof(uint16_t)) return false;
        pose_cache=(uint16_t *)module;
        for (unsigned y=0;y<128;y++)
            memcpy(pose_cache+y*192,(const void *)(screen+(y+8)*stride+32),192*2);
        memset(faces,0,sizeof(faces));
        face_dirty=false;
    }
    if ((command>=0x1e00 && command<=0x1e02) || (command>=0x1b02 && command<=0x1b04) || command==0x0c05 || command==0x0500 || (command>=0x1704 && command<=0x1706) || command==0x1700 || command==0x1701) {
        if (capacity<192*128*sizeof(uint16_t)) return false;
        pose_cache=(uint16_t *)module;
        for (unsigned y=0;y<128;y++)
            memcpy(pose_cache+y*192,(const void *)(screen+(y+8)*stride+32),192*2);
        const struct garden_actor *cast=command==0x1b02?club_2:command==0x1b03?club_3:club_4;
        club_count=command==0x1b02?COUNT(club_2):1;
        if (command==0x1e00) { cast=club_morgue0; club_count=COUNT(club_morgue0); }
        if (command==0x1e01) { cast=club_morgue1; club_count=COUNT(club_morgue1); }
        if (command==0x1e02) { cast=club_morgue2; club_count=COUNT(club_morgue2); }
        if (command==0x0500) { cast=club_freddy; club_count=COUNT(club_freddy); }
        if (command==0x1704) { cast=club_ivan4; club_count=COUNT(club_ivan4); }
        if (command==0x1706) { cast=club_ivan6; club_count=COUNT(club_ivan6); }
        if (command==0x1705) { cast=club_ivan5; club_count=COUNT(club_ivan5); }
        if (command==0x0c05) { cast=club_5; club_count=COUNT(club_5); }
        if (command==0x1700 || command==0x1701) { cast=club_ivan; club_count=COUNT(club_ivan); }
        if (command==0x0500 || command==0x1700 || command==0x1701 || command==0x1b02) {
            unsigned cache_bytes=192*128*2;
            const char *file=command==0x0500?"FREDPAL.BIN":command==0x1b02?"CLUBPAL.BIN":"IVANPAL.BIN";
            size_t size=disc_read(file,
                                  module+cache_bytes,capacity-cache_bytes);
            lights=(const struct room_lights *)(module+cache_bytes);
            if (size<sizeof(*lights) || size!=sizeof(*lights)+4*lights->pixels || lights->cycles>3) return false;
            memcpy(light_colors,scene->palette,sizeof(light_colors));
            sprite_palette=light_colors;
            light_delay=lights->delay;
            memset(light_ticks,0,sizeof(light_ticks));
            memset(light_phases,0,sizeof(light_phases));
        }
        memset(club_sprites,0,sizeof(club_sprites));
        for (unsigned i=0;i<club_count;i++) club_sprites[i].actor=cast+i;
        if (command==0x1e02) club_sprites[1].paused=true;
        if (command==0x1704) {
            /* SP14 enters with the seated Ivan. Its later room visit explicitly
             * resumes actor 16 and hides the static replacement, actor 17. */
            club_sprites[1].paused=true;
        }
        club_random=1;
        club_left=224;club_top=136;club_right=32;club_bottom=8;
        club_tick();
    }
    if (command==0x1800 || command==0x1801) {
        size_t size=disc_read("SHOPFX.BIN",module,capacity);
        const struct shop_lights *lights=(const struct shop_lights *)module;
        if (size<sizeof(*lights) || size!=sizeof(*lights)+lights->count*sizeof(struct shop_pixel)) return false;
        shop_lights=lights;
        memcpy(shop_colors,scene->palette,sizeof(shop_colors));
        memset(shop_timers,0,sizeof(shop_timers));
        shop_phases[0]=2; shop_phases[1]=5;
        shop_phases[2]=3; shop_phases[3]=5;
        shop_lights_tick();
    }
    if (command==0x1802) {
        if (capacity<256*128*sizeof(uint16_t)) return false;
        pose_cache=(uint16_t *)module;
        shop_mask_visible[0]=shop_mask_visible[1]=true;
        shop_camera=24;
        for (unsigned y=0;y<224;y++) memset((void *)(screen+y*stride),0,256*2);
        shop_room();
    }
    if (command==0x0603 || command==0x070b || command==0x070d) {
        if (capacity<192*128*sizeof(uint16_t)) return false;
        pose_cache=(uint16_t *)module;
        garden_open();
    }
    if (command == 0x1908) {
        if (capacity < 192*128*sizeof(uint16_t)) return false;
        pose_cache = (uint16_t *)module;
        for (unsigned y=8; y<136; ++y)
            memcpy(pose_cache+(y-8)*192,(const void *)(screen+y*stride+32),192*sizeof(uint16_t));
        john_clock=spark_clock=arm_step=arm_ticks=0;
        spark_pause=1;
        arm_x=arm_y=0;
        john_timer_visible=false;
        john_tick();
    }
    if (command == 0x0f02) {
        // The first part of the module buffer holds the four fan poses.
        const struct motion *fan = scene->loop;
        size_t fan_words = (fan->right-fan->left)*(fan->bottom-fan->top)*fan->count;
        if (2*(fan_words + 96*112) > capacity) return false;
        office_cache = (uint16_t *)module + fan_words;
        render(empty_office, COUNT(empty_office), 32,24,128,136,office_cache,96,32,24);
    }
    if (command == 0x0e00 || command == 0x1900 || command==0x2405 || command==0x1702 || command==0x0507) {
        size_t words = 256*136;
        if (command == 0x2405) words += 192*128;
        if (capacity < words*sizeof(uint16_t)) return false;
        pose_cache = (uint16_t *)module;
        render(NULL,0,16,8,240,136,pose_cache,256,0,0);
    }
    if (command==0x0601) {
        if (capacity<256*136*sizeof(uint16_t)) return false;
        pose_cache=(uint16_t *)module;
        render(scene->sprites,scene->sprite_count,32,8,224,136,pose_cache,256,0,0);
        hostage_x=72;
        hostage_mouth=8;
        hostage_lip=0;
        hostage_pause=3;
        hostage_tick();
    }
    if (scene->loop) {
        // Tile transfers are complete. Reuse the CD read buffer until the next scene.
        const struct motion *m = scene->loop;
        unsigned width = m->right - m->left, area = width * (m->bottom-m->top);
        if (m->count * area > capacity / sizeof(uint16_t)) return false;
        pose_cache = (uint16_t *)module;
        for (unsigned i = 0; i < m->count; i++)
            render(m->steps[i].sprites, m->steps[i].count, m->left, m->top, m->right,
                   m->bottom, pose_cache+i*area, width, m->left, m->top);
    }
    return true;
}

struct garden_state {
    unsigned pc, ticks, repeat;
    int pose, x, y, vx, vy;
    bool active, signaled;
};
static struct garden_state garden[COUNT(garden_cast)];
static const struct garden_actor *room_actors;
static unsigned room_actor_count;
static bool garden_dirty;
static uint32_t garden_random;

static void garden_start(unsigned object,unsigned action)
{
    if (scene->command==0x070d && object==18) object=21;
    for (unsigned i=0;i<room_actor_count;i++) {
        if (room_actors[i].id!=object) continue;
        if (action==0 || action==2) {
            garden[i]=(struct garden_state){.pose=-1,.active=action==0};
            garden_dirty=true;
        }
        break;
    }
}

static void garden_open(void)
{
    garden_active=true;
    garden_color=scene->palette[31];
    for (unsigned y=0;y<128;y++)
        memcpy(pose_cache+y*192,(const void *)(screen+(8+y)*stride+32),192*2);
    memset(garden,0,sizeof(garden));
    garden_random=1;
    bool floor=scene->command==0x0603;
    room_actors=floor?hostage_floor_cast:garden_cast;
    room_actor_count=floor?COUNT(hostage_floor_cast):COUNT(garden_cast);
    garden_start(floor?17:20,0);
    garden_start(floor?18:21,0);
    if (scene->command==0x070d) garden_start(23,0);
    garden_tick();
}

static void garden_advance(unsigned i)
{
    struct garden_state *state=&garden[i];
    const struct garden_actor *actor=&room_actors[i];
    for (;;) {
        const struct fixture_step step=actor->code[state->pc++];
        if (step.op<128) {
            garden_dirty|=state->pose!=(int)step.op;
            state->pose=step.op;
            state->ticks=step.duration;
            if (step.argument==255) {
                unsigned first=step.duration>>8,last=step.duration&255;
                garden_random=garden_random*1664525u+1013904223u;
                state->ticks=first+(garden_random>>16)%(last-first+1);
            }
            return;
        }
        switch (step.op) {
        case 0x80: state->active=false; garden_dirty=true; return;
        case 0x81: state->pc=step.argument; break;
        case 0x82:
            if (state->repeat<step.argument) { ++state->repeat; state->pc=step.duration; }
            else state->repeat=0;
            break;
        case 0x86: state->vx=(int16_t)step.duration*256+step.argument; break;
        case 0x87: state->vy=(int16_t)step.duration*256+step.argument; break;
        case 0x95: garden_start(step.argument,2); break;
        case 0x98: state->signaled=true; break;
        case 0x9f: {
            extern void garden_bark(void);
            garden_bark();
            break;
        }
        }
    }
}

static void garden_tick(void)
{
    for (unsigned i=0;i<room_actor_count;i++) {
        struct garden_state *s=&garden[i];
        if (!s->active) continue;
        if (!s->ticks || !--s->ticks) garden_advance(i);
        if (s->vx || s->vy) {s->x+=s->vx; s->y+=s->vy; garden_dirty=true;}
    }
    for (unsigned i=0;i<scene->cycle_count;i++) {
        const struct palette_cycle *c=&scene->cycles[i];
        if (palette_tick%c->frames) continue;
        uint16_t color=c->colors[(palette_tick/c->frames)%c->color_count];
        garden_color=color;
        for (unsigned j=0;j<c->count;j++) {
            unsigned x=c->pixels[j]&255,y=c->pixels[j]>>8;
            if (x>=32 && x<224 && y>=8 && y<136) pose_cache[(y-8)*192+x-32]=color;
        }
        garden_dirty=true;
    }
    palette_tick++;
    if (!garden_dirty) return;
    for (unsigned y=0;y<128;y++)
        memcpy((void *)(screen+(8+y)*stride+32),pose_cache+y*192,192*2);
    for (unsigned i=room_actor_count;i--;) {
        const struct garden_state *s=&garden[i];
        if (!s->active || s->pose<0) continue;
        const struct motion_step *frame=&room_actors[i].poses[s->pose];
        for (unsigned j=0;j<frame->count;j++) {
            struct sprite part=frame->sprites[j];
            part.x+=s->x/256; part.y+=s->y/256;
            paint(&part,1,32,8,224,136,screen,stride,0,0);
        }
    }
    extern void refresh_scene_item(void);
    refresh_scene_item();
    garden_dirty=false;
}

static bool garden_wait(unsigned object)
{
    extern void scene_wait(unsigned);
    for (unsigned i=0;i<room_actor_count;i++) {
        if (room_actors[i].id!=object || !garden[i].active) continue;
        while (garden[i].active && !garden[i].signaled) scene_wait(1);
        return true;
    }
    return false;
}

static void fixture_draw(unsigned index)
{
    const struct motion_step *base = &fixture_poses[index < 3 ? 0 : 2];
    for (unsigned j=0; j<base->count; ++j) {
        const struct sprite *part = &base->sprites[j];
        unsigned x=part->x, y=part->y;
        unsigned right=x+8*part->width, bottom=y+8*part->height;
        render(NULL,0,x,y,right,bottom,screen,stride,0,0);
        for (unsigned i=index/3*3; i<index/3*3+3; ++i) {
            unsigned frame=fixture_actors[i].pose;
            if (frame >= COUNT(fixture_poses)) continue;
            const struct motion_step *pose=&fixture_poses[frame];
            paint(pose->sprites,pose->count,x,y,right,bottom,screen,stride,0,0);
        }
    }
}

static void fixture_advance(unsigned index)
{
    struct fixture_actor *actor=&fixture_actors[index];
    while (actor->next) {
        const struct fixture_step step=*actor->next++;
        if (step.op < COUNT(fixture_poses)) {
            actor->pose=step.op;
            actor->ticks=1+step.duration;
            fixture_draw(index);
            return;
        }
        if (step.op==0x98) actor->signaled=true;
        else if (step.op==0x9d) {
            extern bool fm_effect_start(unsigned);
            fm_effect_start(step.argument);
        } else {
            actor->next=NULL;
            if (step.op==0x80) {
                actor->pose=COUNT(fixture_poses);
                fixture_draw(index);
            }
        }
    }
}

static void fixture_tick(void)
{
    for (unsigned i=0; i<COUNT(fixture_actors); ++i) {
        struct fixture_actor *actor=&fixture_actors[i];
        if (actor->next && actor->ticks && !--actor->ticks) fixture_advance(i);
    }
}

void restore_answer_background(void)
{
    if (scene && (scene->command==0x0700 || scene->command==0x0701))
        render(NULL,0,56,99,184,120,screen,stride,0,0);
}

void motion_start(unsigned object, unsigned action)
{
    if (hotel_return && scene && scene->command==0x0503 && object==19 && !action) {
        hotel_map_visible=!hotel_map_visible;
        sprite_palette=hotel_map_visible ? hotel_map_palette : scene->palette;
        render(hotel_map,hotel_map_visible ? COUNT(hotel_map) : 0,48,24,112,88,screen,stride,0,0);
        return;
    }
    if (scene && scene->command==0x2403 && !action && (object==16 || object==18)) {
        passage_stop=object==16 ? 1 : 2;
        passage_hold=object==16 ? 35 : 0;
        passage_draw();
        return;
    }
    extern bool videophone_visible;
    if (scene && scene->command==0x1d02 && object==18) {
        operating_draw(action==0);
        return;
    }
    if (scene && (scene->command==0x1d04 || scene->command==0x1d06) && object==18) {
        render(scene->sprites,scene->sprite_count,32,8,224,136,screen,stride,0,0);
        if (action==0) paint(queens_door,COUNT(queens_door),32,8,224,136,screen,stride,0,0);
        return;
    }
    if ((scene && scene->command==0x1d05 && object==35) || (queens_room==1 && object==21)) {
        if (action==0) { plaza_close(); queens_fade=73; }
        return;
    }
    if (scene && (scene->command==0x1d05 || scene->command==0x1d07 || scene->command==0x1d08) && object>=32 && object<=34) {
        unsigned mask=1u<<(object-32);
        if (action==0) queens_switches |= mask;
        if (action==2) queens_switches &= ~mask;
        queens_waiting_room();
        return;
    }
    if (scene && scene->command==0x1c03 && object==18) {
        if (action==0) paint(apartment_door,COUNT(apartment_door),32,8,224,136,screen,stride,0,0);
        if (action==2) render(apartment_window,apartment_window_lit ? COUNT(apartment_window) : 0,32,8,224,136,screen,stride,0,0);
        return;
    }
    if (scene && scene->command==0x0507 && object==30 && !action) { lisa_entry=1; lisa_entry_tick(); return; }
    if (videophone_visible) return; /* Phone waits run their own overlay controller. */
    if (scene && scene->command==0x0c01 && object==48 && action==0) {
        result_revealed=true;
        return;
    }
    if (scene && scene->command==0x0c01 && object>=32 && object<=42) {
        const struct jordan_portrait *portrait=jordan_portraits+object-32;
        render(scene->sprites,scene->sprite_count,32,8,224,136,screen,stride,0,0);
        if (action==0 || action==5) {
            sprite_palette=portrait->palette;
            paint(portrait->tiles,portrait->count,32,8,224,136,screen,stride,0,0);
            sprite_palette=scene->palette;
        }
        return;
    }
    if (scene && scene->command==0x0c02) {
        if ((object==28 || object==15) && action==0) {
            if (object==15) face_scanning=!face_scanning;
            if (face_scanning) memset(tiles+0xc000,0,2048);
            else memcpy(tiles+0xc000,tiles+0xc800,2048);
            render(scene->sprites,scene->sprite_count,32,8,224,136,pose_cache,192,32,8);
            face_dirty=true;
            return;
        }
        for (unsigned i=0;i<COUNT(faces);i++) {
            if (montage_parts[i].id!=object) continue;
            struct face_state *f=faces+i;
            if (action==5) { memset(f,0,sizeof(*f)); f->active=true; }
            if (action==2) { f->visible=false; f->active=false; }
            if (action==0) { f->active=true; f->paused=false; }
            face_dirty=true;
        }
        return;
    }
    if (club_count) {
        for (unsigned i=0;i<club_count;i++) {
            struct club_sprite *s=&club_sprites[i];
            if (s->actor->id!=object) continue;
            if (action==0 && s->paused) {
                s->paused=false;
                s->ticks=0;
            } else if (action==2) {
                s->paused=true;
                club_pose(s,NULL);
            }
        }
        return;
    }
    if (scene && scene->command==0x0505 && (object==16 || object==17)) {
        if (action==0 || action==5) bathroom_actor=object;
        if (action==2 && bathroom_actor==object) bathroom_actor=0;
        bathroom_draw();
        return;
    }
    if (scene && scene->command==0x0504 && object==21 && action==0) {
        freddy_lisa=true;
        return;
    }
    if (scene && scene->command==0x0502 && object==17 && action==0) freddy_helper=true;
    if (scene && scene->command==0x0502 && (object==21 || object==22 || object==19)) {
        if (object==21 && action==0) freddy_dark=true;
        if (object==22) freddy_panel=action==0;
        if (object==19) {
            if (action==5) {
                freddy_hand=true;
                freddy_knock_ticks=freddy_knock_delay;
            } else if (action==2) {
                freddy_knock_ticks=0;
                freddy_hand=false;
            }
        }
        background_palette=sprite_palette=freddy_dark ? freddy_palette : scene->palette;
        render(NULL,0,32,8,224,136,screen,stride,0,0);
        if (freddy_panel) paint(freddy_door,COUNT(freddy_door),32,8,224,136,screen,stride,0,0);
        if (freddy_hand) paint(freddy_knock,COUNT(freddy_knock),32,8,224,136,screen,stride,0,0);
        return;
    }
    if (shop_lights && object==16 && action==0) {
        shop_lights=NULL;
        render(NULL,0,32,8,224,136,screen,stride,0,0);
        return;
    }
    if (scene && scene->command==0x1802 && (object==16 || object==17) && action==0) {
        shop_mask_visible[object-16]=false;
        shop_room();
        return;
    }
    if (scene && (scene->command==0x0603 || scene->command==0x070b || scene->command==0x070d)) {
        garden_start(object,action);
        return;
    }
    if (scene && scene->command==0x0708 && (object==22 || object==23)) {
        const struct sprite *item=object==22 ? study_item_22 : study_item_23;
        unsigned count=object==22 ? COUNT(study_item_22) : COUNT(study_item_23);
        if (action==0) paint(item,count,32,8,224,136,screen,stride,0,0);
        else if (action==2) {
            for (unsigned i=0;i<count;i++)
                render(scene->sprites,scene->sprite_count,item[i].x,item[i].y,
                       item[i].x+8*item[i].width,item[i].y+8*item[i].height,screen,stride,0,0);
        }
        return;
    }
    if (scene && (scene->command==0x0700 || scene->command==0x0701) && object==21) {
        if (action!=5 && action!=2) return;
        gibson_door_visible=action==5;
        if (gibson_door_visible)
            paint(gibson_door,COUNT(gibson_door),32,8,224,136,screen,stride,0,0);
        else
            render(NULL,0,32,8,224,136,screen,stride,0,0);
        return;
    }
    if (scene && scene->command == 0x0b00 && (object==24 || object==25 || object==29)) {
        if (object==24 && action==0) engineering_visible |= 1;
        else if (object==25 && action==5) {
            extern bool fm_effect_start(unsigned);
            engineering_visible |= 2;
            fm_effect_start(capsule_effect);
        } else if (object==25 && action==2) engineering_visible &= ~2u;
        else if (object==29 && action==0)
            engineering_visible=(engineering_visible&3) | ((engineering_visible&4) ? 8 : 4);
        else return;
        render(scene->sprites, scene->sprite_count,32,8,224,136,screen,stride,0,0);
        for (unsigned i=0; i<COUNT(engineering_figures); ++i) {
            if (!(engineering_visible & (1u<<i))) continue;
            const struct motion_step *figure=&engineering_figures[i];
            paint(figure->sprites,figure->count,32,8,224,136,screen,stride,0,0);
        }
        return;
    }
    if (scene && scene->command == 0x0d00 && object == 18 && action == 0) {
        render(detective_tour, COUNT(detective_tour), 32, 8, 224, 136, screen, stride, 0, 0);
        return;
    }
    if (scene && scene->command == 0x0d00 && object == 21) {
        if (action == 5) {
            extern bool fm_effect_start(unsigned);
            paint(capsule_picture, COUNT(capsule_picture), 32, 8, 224, 136, screen, stride, 0, 0);
            fm_effect_start(capsule_effect);
        } else if (action == 2) {
            for (unsigned i=0; i<COUNT(capsule_picture); ++i) {
                const struct sprite *s=&capsule_picture[i];
                render(NULL,0,s->x,s->y,s->x+8*s->width,s->y+8*s->height,screen,stride,0,0);
            }
        }
        return;
    }
    if (scene && scene->command == 0x0d00 && object >= 22 && object <= 27) {
        unsigned index = object-22;
        struct fixture_actor *actor=&fixture_actors[index];
        if (action == 0) {
            actor->next=fixture_programs[index];
            actor->signaled=false;
            fixture_advance(index);
        } else if (action == 2) {
            actor->next=NULL;
            actor->pose=COUNT(fixture_poses);
            fixture_draw(index);
        }
        return;
    }
    if (scene && scene->command==0x1908 && object==20) john_timer_visible=action==0;
    else if (scene && scene->command==0x1905 && object==20 && action==0) storm_delay=16;
    else if (scene && scene->command == 0x0f02 && (object == 16 || object == 27))
        motion_started = action == 0;
    else if (scene && (scene->command==0x1b00 || scene->command==0x1b01 || (scene->command == 0x0f00 && object == 17) ||
                       ((scene->command == 0x0f01 || scene->command == 0x2000 || scene->command == 0x1908 || scene->command == 0x1909) && object == 16)))
        motion_started = action == 0;
    else if (scene && scene->motion && scene->motion->object == object)
        motion_started = action == 0;
}

bool music_start(unsigned track)
{
    if (track==11) {
        extern bool crash_movie(void);
        crash_sequence=crash_movie();
        return crash_sequence;
    }
    if (ending_scene==0x0604 && track==7 && !plaza_ending(1,screen,stride)) return false;
    if (scene && scene->command==0x2003 && track==20 &&
        (!drive_load(false) || !drive_section(0,screen,stride))) return false;
    if (briefing_track==13 && track==14) {
        if (!plaza_briefing_load(14)) return false;
        briefing_track=14;
    }
    if (track==16 && !briefing_track) {
        if (!plaza_briefing_load(16)) return false;
        briefing_track=16;
    }
    if (!disc_play_track(track)) return false;
    if (briefing_track && track==briefing_track) plaza_briefing_start(screen,stride);
    return true;
}

bool music_wait(void)
{
    crash_sequence=false;
    if (drive_scene==0x2002 && !drive_section(2,screen,stride)) return false;
    if (!disc_wait_track_frame(0xffff)) return false;
    if (city_dialogue()) {
        if (!city_wait()) return false;
        city_close();
    }
    return true;
}

bool motion_wait(unsigned object)
{
    if (crash_sequence && (object==2 || object==15)) return true;
    /* Track 10's packed pictures include the original actors' starts and waits.
     * SP29 waits for the CD after actor 29 before it enables the destination menu. */
    if (briefing_track==10 && (object==15 || object==29)) return true;
    /* SP31 waits for the last fade again after the track has ended. */
    /* The packed sequence includes actor 15 and the cut to scene 1300.
     * SP33 waits for the disc before it offers the room choices. */
    if (briefing_track>=12 && briefing_track<=14 && object==15) return true;
    if (briefing_track==21 && object==16) return disc_wait_track_sector(31229);
    if (ending_scene>=0x0604 && ending_scene<=0x0608 && object==15) {
        /* Original track-relative CD sectors at the five picture changes. */
        static const unsigned sectors[]={606,3643,7879,6712,9241};
        return disc_wait_track_sector(sectors[ending_scene-0x0604]);
    }
    if (scene && scene->command==0x1d02 && (object==19 || object==20)) {
        extern void scene_wait(unsigned);
        unsigned target=object==19 ? operating_pan_pixels : 0;
        while (operating_scroll!=target) {
            operating_scroll+=object==19 ? 1 : -1;
            pan_frame(operating_scroll);
            scene_wait(2);
        }
        return true;
    }
    if (scene && scene->command==0x0505 && object==18) {
        extern void scene_wait(unsigned);
        bool returning=bathroom_scroll!=0;
        for (unsigned tick=0;tick<bathroom_pan_ticks;tick+=2) {
            bathroom_scroll+=returning?-1:1;
            pan_frame(bathroom_scroll);
            scene_wait(2);
        }
        return true;
    }
    extern bool room202_film(const char *,unsigned);

    if (scene && scene->command==0x0502 && object==16) {
        const char *second=freddy_dark ? (freddy_helper?"FG2A.BIN":"FG2B.BIN")
                                      : (freddy_helper?"FC2A.BIN":"FC2B.BIN");
        return room202_film(freddy_dark?"FG1.BIN":"FC1.BIN",63) && room202_film(second,52);
    }
    if (scene && scene->command==0x0504 && object==31) {
        return room202_film(freddy_lisa?"FR1B.BIN":"FR1A.BIN",32) &&
               room202_film(freddy_lisa?"FR2B.BIN":"FR2A.BIN",81);
    }
    if (ivan_door && object==19) {
        extern void scene_wait(unsigned),range_sound(unsigned);
        scene_wait(7);
        range_sound(60);
        scene_wait(17);
        range_sound(59);
        scene_wait(40);
        return true;
    }
    if (scene && scene->command==0x1702 && object==28) {
        extern void scene_wait(unsigned),door_knock(void);
        scene_wait(knock_before);
        door_knock();
        scene_wait(knock_after);
        return true;
    }
    if (scene && (scene->command==0x0c01 || scene->command==0x0c02 ||
                  scene->command==0x0c05) && object==23) {
        /* H04 actor 23 fades all 64 colors, waits 32 frames, and hides the frame. */
        extern void scene_wait(unsigned);
        for (unsigned phase=0;phase<8;phase++) {
            scene_wait(4);
            for (unsigned y=0;y<142;y++) for (unsigned x=0;x<256;x++) {
                unsigned c=screen[y*stride+x];
                unsigned r=c&31,g=(c>>5)&31,b=(c>>10)&31;
                screen[y*stride+x]=0x8000 | (r>4?r-4:0) | ((g>4?g-4:0)<<5) | ((b>4?b-4:0)<<10);
            }
        }
        return true;
    }
    if (scene && scene->command==0x0c01 && object==49 && result_revealed) {
        extern void scene_wait(unsigned);
        extern bool fm_effect_start(unsigned);
        scene_wait(4);
        fm_effect_start(8);
        for (unsigned frame=1;frame<=64;frame++) {
            render(scene->sprites,scene->sprite_count,32,8,224,136,screen,stride,0,0);
            sprite_palette=jordan_result_palette;
            for (unsigned j=0;j<COUNT(jordan_result_49);j++) {
                struct sprite tile=jordan_result_49[j];
                tile.y+=frame;
                paint(&tile,1,32,8,224,136,screen,stride,0,0);
            }
            paint(jordan_result_4,COUNT(jordan_result_4),32,8,224,136,screen,stride,0,0);
            sprite_palette=scene->palette;
            scene_wait(1);
        }
        return true;
    }
    if (scene && scene->command==0x0c02) {
        extern void scene_wait(unsigned);
        for (unsigned i=0;i<COUNT(faces);i++) if (montage_parts[i].id==object) {
            struct face_state *f=faces+i;
            while (f->active && !f->paused && !f->signaled) scene_wait(1);
            return f->signaled;
        }
    }
    if (scene && scene->command==0x1802 && (object==19 || object==20 || object==22)) {
        extern void scene_wait(unsigned);
        int to=object==19 ? 24 : -24;
        if (object==22) scene_wait(129);
        while (shop_camera!=to) {
            shop_camera+=shop_camera<to ? 1 : -1;
            shop_paint();
            scene_wait(1);
        }
        return true;
    }
    if (scene && scene->command==0x0708 && object==24) {
        extern void garden_bark(void);
        extern void scene_wait(unsigned);
        scene_wait(33);
        garden_bark();
        scene_wait(209);
        return true;
    }
    if (scene && (scene->command==0x0603 || scene->command==0x070b || scene->command==0x070d))
        return garden_wait(object);
    extern bool gibson_transition(const char *);
    extern bool operating_attack(void);
    if (scene && scene->command==0x1d02 && object==28) return operating_attack();
    if (scene && (scene->command==0x1d04 || scene->command==0x1d06) && object==16)
        return gibson_transition("QDOOR.BIN");
    if (scene && scene->command==0x1d05 && object==16) {
        if (!queens_returning && !gibson_transition("QENTRY.BIN")) return false;
        queens_waiting_room();
        return true;
    }
    if (scene && scene->command==0x1c03 && object==21) {
        apartment_window_lit=true;
        return gibson_transition("APTLIGHT.BIN");
    }
    if (scene && scene->command==0x1c03 && object==16) return gibson_transition("APTDOOR.BIN");
    if (scene && (scene->command==0x0700 || scene->command==0x0701) && object==16)
        return gibson_transition("GDOOR.BIN");
    if (scene && (scene->command==0x0702 || scene->command==0x0703) && object==16)
        return gibson_transition("G2DOOR.BIN");
    if (scene && scene->command==0x0705 && object==32)
        return gibson_transition("G2ENTRY.BIN");
    if (scene && scene->command==0x0704 && object==32)
        return gibson_transition("GENTRY.BIN");
    extern bool videophone_visible;
    if (videophone_visible && object==29) { extern bool videophone_disconnect(void); return videophone_disconnect(); }
    if (videophone_visible && object==30) { extern bool videophone_connect(void); return videophone_connect(); }
    if (videophone_visible && object==32) { extern bool videophone_shutdown(void); return videophone_shutdown(); }
    if (object==15 && city_wait()) return true;
    extern void scene_wait(unsigned);
    if (scene && scene->command == 0x0d00 && object >= 22 && object <= 27) {
        struct fixture_actor *actor=&fixture_actors[object-22];
        while (actor->next && !actor->signaled) scene_wait(1);
        return actor->signaled;
    }
    if (scene && scene->command==0x1909 && object==16 && motion_started) {
        extern void shadow_sound(void);
        for (unsigned i=0; i<COUNT(shadow_steps); ++i) {
            const struct shadow_step *step=&shadow_steps[i];
            if (step->sound==24) shadow_sound();
            render(step->sprites,step->count,32,8,224,136,screen,stride,0,0);
            scene_wait(step->frames);
        }
        render(NULL,0,32,8,224,136,screen,stride,0,0);
        motion_started=false;
        return true;
    }
    if (scene && scene->command==0x1908 && object==16 && motion_started) {
        while (arm_step<COUNT(john_arm)) scene_wait(1);
        motion_started=false;
        return true;
    }
    if ((object==22 || object==23) && scan_active()) {
        while (scan_waiting()) scene_wait(1);
        return true;
    }
    if (scene && (scene->command==0x2100 || scene->command==0x2102) && object==32) {
        extern void clear_dialogue(void);
        clear_dialogue();
        return drive_load(true) && drive_section(0,screen,stride);
    }
    if (drive_scene==0x2103 && object==17) return drive_section(1,screen,stride);
    if (scene && scene->command==0x2003) {
        if (object==32) return drive_section(1,screen,stride);
        if (object==15) return true; /* The retail controller has already signalled. */
    }
    if (drive_scene==0x2002 && object==18) return drive_section(3,screen,stride);
    if (drive_scene==0x2004 && object==17) return drive_section(4,screen,stride);
    if (motion_started && scene && scene->command == 0x0f02 && object == 16) {
        struct sprite body[COUNT(harry_body)];
        memcpy(body, harry_body, sizeof(body));
        for (unsigned frame = 0; frame <= harry_pause + harry_travel; frame++) {
            if (frame == 0 || frame >= harry_pause) {
                for (unsigned y = 0; y < 112; y++)
                    memcpy((void *)(screen+(24+y)*stride+32), office_cache+y*96, 96*sizeof(uint16_t));
                if (frame < harry_pause + harry_travel) {
                    int elapsed = frame > harry_pause ? (int)(frame-harry_pause) : 0;
                    for (unsigned i = 0; i < COUNT(body); i++)
                        body[i].x = harry_body[i].x + elapsed*harry_velocity/2;
                    paint(body,COUNT(body),32,24,128,136,screen,stride,0,0);
                }
            }
            if (frame < harry_pause + harry_travel) scene_wait(1);
        }
        motion_started = false;
        harry_left = true;
        return true;
    }
    if (motion_started && scene && scene->command == 0x0f02 && object == 27 && harry_left) {
        extern void navigator_sound(void);
        for (unsigned step = 0; step < 32; step++) {
            const struct motion_step *motion = &navigator_walk[step % COUNT(navigator_walk)];
            struct sprite actor[16];
            if (motion->count > COUNT(actor)) return false;
            memcpy(actor,motion->sprites,motion->count*sizeof(*actor));
            int offset = (int)(3*(step+1)/2);
            for (unsigned i = 0; i < motion->count; i++) actor[i].x += offset;
            for (unsigned y = 40; y < 120; y++)
                memcpy((void *)(screen+y*stride+32), office_cache+(y-24)*96, 96*sizeof(uint16_t));
            paint(actor,motion->count,32,40,128,120,screen,stride,0,0);
            paint(office_partition,COUNT(office_partition),32,40,128,120,screen,stride,0,0);
            if (step && !(step % 2)) navigator_sound();
            scene_wait(motion->frames+1);
        }
        motion_started = false;
        return true;
    }
    if (motion_started && scene && scene->command == 0x0f01 && object == 16) {
        extern void blaster_sound(void);
        scene_wait(8);
        blaster_sound();
        for (unsigned i = 0; i < COUNT(blaster_flash); i++) {
            const struct motion_step *step = &blaster_flash[i];
            render(step->sprites,step->count,32,8,224,136,screen,stride,0,0);
            scene_wait(step->frames);
        }
        render(scene->sprites,scene->sprite_count,32,8,224,136,screen,stride,0,0);
        motion_started = false;
        return true;
    }
    if (motion_started && scene && ((scene->command == 0x0f00 && object == 17) ||
                                    (scene->command == 0x2000 && object == 16))) {
        bool vehicle = scene->command == 0x2000;
        const struct motion_step *steps = vehicle ? canopy : antenna;
        unsigned count = vehicle ? COUNT(canopy) : COUNT(antenna);
        if (vehicle) {
            extern void canopy_sound(void);
            canopy_sound();
        }
        for (unsigned i = 0; i < count; ++i) {
            render(steps[i].sprites,steps[i].count,32,8,224,136,screen,stride,0,0);
            scene_wait(steps[i].frames);
        }
        motion_started = false;
        return true;
    }
    if (!motion_started || !scene || !scene->motion || scene->motion->object != object)
        return false;
    const struct motion *m = scene->motion;
    for (unsigned i = 0; i < m->count; i++) {
        const struct motion_step *step = &m->steps[i];
        render(step->sprites, step->count, m->left, m->top, m->right, m->bottom, screen, stride, 0, 0);
        scene_wait(step->frames);
    }
    motion_started = false;
    return true;
}


void scene_tick(void)
{
    flashlight_tick();
    queens_fade_tick();
    street_tick();
    if (scene && scene->command==0x0c02) face_tick();
    report_tick();
    plaza_tick();
    if (lisa_entry) lisa_entry_tick();
    if (scene && scene->command==0x0601) hostage_tick();
    if (club_count) { club_tick(); return; }
    if (shop_lights) { shop_lights_tick(); return; }
    if (!scene) return;
    if (scene->command==0x0603 || scene->command==0x070b || scene->command==0x070d) { garden_tick(); return; }
    if (scene->command==0x2403) {
        if (!passage_stop) { ++passage_clock; passage_draw(); }
        else if (passage_hold && !--passage_hold) passage_draw();
        return;
    }
    if (scene->command==0x0d00) { fixture_tick(); return; }
    if (scene->command==0x1908) { john_tick(); return; }
    if (scene->command==0x1905) {
        if (storm_delay && !--storm_delay) storm_sound();
        storm_tick();
    }
    for (unsigned i = 0; i < scene->cycle_count; ++i) {
        const struct palette_cycle *c = gibson_door_visible ? &cycles_gibson_door[i] : &scene->cycles[i];
        if (palette_tick % c->frames) continue;
        uint16_t color = c->colors[(palette_tick / c->frames) % c->color_count];
        for (unsigned j = 0; j < c->count; ++j) {
            unsigned xy = c->pixels[j];
            screen[(xy >> 8)*stride + (xy & 255)] = color;
        }
    }
    ++palette_tick;
    if (!scene->loop) return;
    const struct motion *m = scene->loop;
    if (++ticks < m->steps[pose].frames+drip_extra) return;
    ticks = 0;
    if (++pose == m->count) pose = m->loop_start;
    if (scene->command==0x1907) {
        drip_random=drip_random*1664525u+1013904223u;
        drip_extra=pose==0 ? (drip_random>>16)%65 : pose==1 ? (drip_random>>16)%59 : 0;
        if (pose==9 && drip_ready) { extern void drip_sound(void); drip_sound(); }
    }
    if (harry_left) {
        // In this room the four fan steps end with Harry and his face.
        const struct motion_step *step = &m->steps[pose];
        unsigned count = step->count - COUNT(harry_body) - 1;
        render(step->sprites,count,m->left,m->top,m->right,m->bottom,screen,stride,0,0);
        return;
    }
    unsigned width = m->right-m->left;
    const uint16_t *pixels = pose_cache + pose*width*(m->bottom-m->top);
    for (unsigned y = m->top; y < m->bottom; y++) {
        memcpy((void *)(screen + y*stride + m->left), pixels, width*sizeof(*pixels));
        pixels += width;
    }
}

void presentation_tick(void)
{
    flashlight_tick();
    queens_fade_tick();
    street_tick();
    city_tick();
    if (scene && (scene->command==0x0603 || scene->command==0x070b || scene->command==0x070d)) garden_tick();
    if (scene && scene->command==0x0d00) fixture_tick();
    extern void fm_effect_tick(void);
    fm_effect_tick();
    extern bool videophone_visible;
    if (freddy_knock_ticks && !--freddy_knock_ticks) {
        extern void door_knock(void);
        door_knock();
    }
    if (videophone_visible) { extern void videophone_tick(void); videophone_tick(); return; }
    if (scene && scene->command==0x0c02) face_tick();
    if (club_count) club_tick();
    shop_lights_tick();
    report_tick();
    plaza_tick();
    if (lisa_entry) lisa_entry_tick();
    if (scene && scene->command==0x0601) hostage_tick();
    scan_tick();
    if (scene && scene->command == 0x1908) john_tick();
    if (scene && scene->command == 0x0f03 && phone_frame < COUNT(phone_connection)) {
        if (phone_ticks) {
            --phone_ticks;
        } else {
            const struct map_step *step = &phone_connection[phone_frame++];
            for (unsigned row=0; row<step->height; ++row)
                memcpy((void *)(screen+(step->top+row)*stride+step->left),
                       phone_pixels+step->offset+row*step->width,step->width*sizeof(uint16_t));
            phone_ticks = step->frames;
        }
    }
    if (scene && (scene->command==0x1b00 || scene->command==0x1b01 || (scene->command == 0x0f00 && !motion_started) || scene->command == 0x0f04 || scene->command==0x1907 ||
                  (scene->command == 0x0f02 && harry_left)))
        scene_tick();
}

#include "practice.h"
struct range_frame { const struct sprite *sprites; unsigned count; };
#include "range_art.h"

static void append_frame(struct sprite *sprites, unsigned *count,
                         const struct range_frame *frame, int x, int y)
{
    for (unsigned i = 0; i < frame->count; ++i) {
        struct sprite sprite = frame->sprites[i];
        sprite.x += x;
        sprite.y += y;
        sprites[(*count)++] = sprite;
    }
}

static void range_region(const struct sprite *sprites, unsigned count,
                         unsigned left, unsigned top, unsigned right, unsigned bottom)
{
    for (unsigned y = top; y < bottom; ++y)
        memcpy((void *)(screen+y*stride+left),pose_cache+y*256+left,(right-left)*2);
    paint(sprites,count,left,top,right,bottom,screen,stride,0,0);
}

static void lisa_entry_tick(void)
{
    unsigned frame=lisa_entry==1?2:lisa_entry==34?4:lisa_entry==43?5:255;
    if (frame!=255) {
        struct sprite parts[80];
        unsigned count=0;
        append_frame(parts,&count,&lisa_frames[frame],72,8);
        range_region(parts,count,32,8,224,136);
    }
    if (++lisa_entry>49) lisa_entry=0;
}

static void hostage_parts(struct sprite *parts,unsigned *count)
{
    append_frame(parts,count,&hostage_frames[7],hostage_x,70);
    append_frame(parts,count,&hostage_frames[hostage_mouth],112,72);
}

static void hostage_tick(void)
{
    if (hostage_lip && !--hostage_lip) hostage_mouth=hostage_mouth==8?9:8;
    if (hostage_pause && !--hostage_pause) {
        /* Actor 30 shifts one pixel and signals actor 29 to move its mouth. */
        hostage_x=hostage_x==72?73:72;
        hostage_lip=2;
        drip_random=1664525u*drip_random+1013904223u;
        hostage_pause=4+(drip_random>>16)%13;
    }
    if (!hostage_combat) {
        struct sprite parts[160];
        unsigned count=0;
        hostage_parts(parts,&count);
        range_region(parts,count,32,8,224,136);
    }
}

static void lisa_flash(unsigned amount)
{
    static uint16_t palette[64];
    static const uint8_t level[]={0,4,8,13,17,22,26,31};
    memcpy(palette,scene->palette,sizeof(palette));
    for (unsigned i=48;i<64;++i) {
        unsigned color=0x8000;
        for (unsigned shift=0;shift<=10;shift+=5) {
            unsigned channel=((palette[i]>>shift)&31)*7;
            unsigned index=(channel+15)/31+amount;
            color|=level[index<7?index:7]<<shift;
        }
        palette[i]=color;
    }
    sprite_palette=palette;
}

bool office_or_taxi_art(const char *file,uint8_t *module,size_t capacity)
{
    static uint16_t palette[64];
    plaza_close();
    if (disc_read(file,module,capacity)!=65536+sizeof(palette)) return false;
    memcpy(tiles,module,65536);
    memcpy(palette,module+65536,sizeof(palette));
    sprite_palette=palette;
    pose_cache=(uint16_t *)module;
    for (unsigned y=8;y<136;y++)
        memcpy(pose_cache+y*256+32,(const void *)(screen+y*stride+32),192*2);
    return true;
}

/* Stage 10 preserves the retail sprite overlap with Mika in each tile map. */
static const uint16_t *mika_bank;
static const uint8_t *mika_timeline;
static const uint16_t *mika_maps,*mika_tiles;
static int mika_last_map;

bool mika_art(uint8_t *module,size_t capacity)
{
    if (!office_or_taxi_art("MFIGHT.BIN",module,capacity)) return false;
    uint16_t *bank=(uint16_t *)0x00260000;
    size_t bytes=disc_read("MIKATGT.BIN",bank,0xa0000);
    if (bytes<100 || bank[0]>=bank[1] || bank[1]>256 || !bank[2] ||
        bank[4]!=0 || bank[49]!=bank[3] ||
        bytes!=100U+((bank[3]+1U)&~1U)+bank[1]*768U+bank[2]*128U) return false;
    for (unsigned i=4;i<49;i++) if (bank[i]>=bank[i+1]) return false;
    mika_bank=bank;
    mika_timeline=(const uint8_t *)(bank+50);
    mika_maps=bank+50+(bank[3]+1)/2;
    mika_tiles=mika_maps+384*bank[1];
    mika_last_map=-1;
    return true;
}

unsigned mika_phase_length(unsigned field,unsigned phase)
{
    unsigned slot=4+5*field+phase-1;
    return mika_bank[slot+1]-mika_bank[slot];
}

static void mika_backdrop(const struct range_picture *p)
{
    unsigned id=mika_bank[0];
    for (unsigned i=0;i<9;++i)
        if (p->target[i]!=255) id=mika_timeline[mika_bank[4+5*i]+p->target[i]];
    if ((int)id==mika_last_map) return;
    const uint16_t *map=mika_maps+384*id;
    for (unsigned pos=0;pos<384;++pos) {
        if (mika_last_map>=0 && map[pos]==mika_maps[384*mika_last_map+pos]) continue;
        uint16_t *dest=pose_cache+256*(8+8*(pos/24))+32+8*(pos%24);
        const uint16_t *src=mika_tiles+64*map[pos];
        for (unsigned y=0;y<8;++y) memcpy(dest+256*y,src+8*y,16);
    }
    mika_last_map=id;
}

bool crawler_art(uint8_t *module,size_t capacity)
{
    static uint16_t palette[64];
    plaza_close();
    if (disc_read("QFIGHT.BIN",module,capacity)!=65536+128+192*128*2) return false;
    memcpy(tiles,module,65536);
    memcpy(palette,module+65536,sizeof(palette));
    sprite_palette=palette;
    const uint16_t *picture=(const uint16_t *)(module+65536+128);
    pose_cache=(uint16_t *)module;
    for (unsigned y=0;y<128;y++)
        memcpy(pose_cache+(y+8)*256+32,picture+y*192,192*2);
    return true;
}

void range_present(const struct range_picture *p)
{
    static struct range_picture last;
    static bool initialized;
    if (!p) { initialized = false; return; }
    if (p->factory) {
        if (!p->swarm && !p->mika && !p->ceiling && !p->driver && !p->crawler && (!scene || scene->command != (p->tunnel?0x2405:p->skeleton?0x1d02:p->hostage?0x0601:p->lisa?0x0507:p->apartment?0x1702:0x1900))) return;
        if (p->skeleton && !p->crawler && !initialized) {
            for (unsigned y=8;y<136;y++)
                memcpy(pose_cache+y*256+32,(const void *)(screen+y*stride+32),192*2);
        }
        if (p->apartment && !initialized) {
            background_palette=sprite_palette=ivan_palette;
            render(NULL,0,16,8,240,136,pose_cache,256,0,0);
        }
        if (initialized && !p->hostage && !memcmp(&last,p,sizeof(last))) return;
        struct sprite sprites[192];
        unsigned count=0;
        if (p->apartment && p->sign!=2) {
            unsigned target=p->target[4]==255 ? 7 : p->target[4];
            append_frame(sprites,&count,&ivan_frames[target],104,24);
        }
        if (p->hostage) {
            hostage_combat=true;
            hostage_parts(sprites,&count);
        }
        if (p->lisa) {
            lisa_entry=0;
            lisa_flash(p->light);
            unsigned target=p->target[1]!=255?p->target[1]:p->target[4]!=255?p->target[4]:p->resting_pose;
            append_frame(sprites,&count,&lisa_frames[target],72,8);
        }
        if (p->mika) mika_backdrop(p);
        static const int corridor_aim[9][2]={{48,24},{112,16},{176,24},{48,40},{110,39},{176,40},{48,96},{112,96},{176,96}};
        const struct range_frame *insects=p->tunnel?tunnel_frames:insector_frames;
        const int (*positions)[2]=p->final_corridor?corridor_positions:p->swarm?swarm_positions:p->tunnel?tunnel_positions:factory_positions;
        for (int i=8;!p->hostage && !p->lisa && !p->apartment && !p->skeleton && !p->driver && !p->ceiling && !p->mika && i>=0;--i) {
            if (p->target[i]==255) continue;
            const struct range_frame *poses=p->final_corridor?corridor_frames:p->swarm?swarm_frames[i]:insects;
            append_frame(sprites,&count,&poses[p->target[i]],
                         positions[i][0],positions[i][1]);
        }
        if (p->ceiling) {
            if (p->attack_field>=0)
                append_frame(sprites,&count,&ceiling_frames[p->attack_frame],96,0);
        } else if (p->driver) {
            if (p->target[5]!=255)
                append_frame(sprites,&count,&driver_frames[p->target[5]],160,40);
            if (p->attack_field>=0)
                append_frame(sprites,&count,&driver_frames[p->attack_frame],150,48);
        } else if (p->crawler) {
            unsigned pose=p->target[6]==255 ? 4 : p->target[6];
            append_frame(sprites,&count,&crawler_frames[pose],46,88);
            if (p->attack_field>=0)
                append_frame(sprites,&count,&crawler_frames[p->attack_frame],38,72);
        }
        else if (p->skeleton && p->attack_field>=0)
            append_frame(sprites,&count,&skeleton_attack_frames[p->attack_frame],93,54);
        else if (p->attack_field>=0 && !p->hostage)
            append_frame(sprites,&count,p->lisa?&lisa_frames[p->attack_frame]:p->final_corridor?&corridor_frames[p->attack_frame]:p->swarm?&swarm_attack_frames[p->attack_frame]:&insects[p->attack_frame],
                         p->final_corridor?corridor_aim[p->attack_field][0]:48+64*(p->attack_field%3),
                         p->final_corridor?corridor_aim[p->attack_field][1]:16+40*(p->attack_field/3));
        const struct range_frame *sight=p->swarm?swarm_sight_frames:p->mika?mika_sight_frames:p->ceiling?ceiling_sight_frames:p->driver?driver_sight_frames:p->tunnel?tunnel_sight_frames:p->crawler?crawler_sight_frames:p->skeleton?skeleton_sight_frames:p->hostage?hostage_sight_frames:p->lisa?lisa_sight_frames:p->apartment?ivan_sight_frames:factory_sight_frames;
        if (p->aim>=0) {
            append_frame(sprites,&count,&sight[5],0,0);
            append_frame(sprites,&count,&sight[14],p->final_corridor?corridor_aim[p->aim][0]:48+64*(p->aim%3),
                         p->final_corridor?corridor_aim[p->aim][1]:16+40*(p->aim/3));
        }
        if (p->flash_field>=0)
            append_frame(sprites,&count,&sight[p->flash_frame],
                         p->final_corridor?corridor_aim[p->flash_field][0]:48+64*(p->flash_field%3),
                         p->final_corridor?corridor_aim[p->flash_field][1]:16+40*(p->flash_field/3));
        if ((p->tunnel || p->swarm) && p->aim>=0) {
            /* Keep the sight visible while new enemies are painted over the backdrop. */
            uint16_t *backdrop = pose_cache + 256*136;
            if (!initialized || last.aim<0) {
                for (unsigned y=0; y<128; ++y)
                    memcpy(backdrop+y*192,pose_cache+(y+8)*256+32,192*sizeof(*backdrop));
                paint(sight[5].sprites,sight[5].count,32,8,224,136,backdrop,192,32,8);
            }
            for (unsigned y=0; y<128; ++y)
                memcpy((void *)(screen+(y+8)*stride+32),backdrop+y*192,192*sizeof(*backdrop));
            paint(sprites,count,32,8,224,136,screen,stride,0,0);
        } else {
            range_region(sprites,count,32,8,224,136);
        }
        for (unsigned y=0;y<8;++y)
            for (unsigned x=0;x<192;++x)
                screen[(136+y)*stride+32+x]=p->sign==2 || (p->skeleton && !p->crawler) ? 0x8000 : p1900[factory_life[p->damage][y][x]];
        initialized=true;
        last=*p;
        return;
    }
    if (!scene || scene->command != 0x0e00) return;
    bool full = !initialized || p->sign != last.sign || (p->aim < 0) != (last.aim < 0);
    struct sprite sprites[192];
    unsigned count = 0;
    if (p->enemies)
        append_frame(sprites, &count, &field_frames[44+p->enemies], 224, 8);
    if (p->announced)
        append_frame(sprites, &count, &field_frames[19+p->announced], 16, 8);
    // GO is printed on the backdrop. READY and OVER cover it with sprites.
    if (p->sign != 1) {
        unsigned sign_frame = p->sign == 0 ? 16 : 18;
        append_frame(sprites, &count, &field_frames[sign_frame], 216, 112);
        append_frame(sprites, &count, &field_frames[sign_frame], 16, 112);
    }
    for (int i = 8; i >= 0; --i)
        append_frame(sprites, &count, &field_frames[p->target[i]], 48+64*(i%3), 16+40*(i/3));
    if (p->aim >= 0) {
        append_frame(sprites, &count, &sight_frames[5], 0, 0);
        append_frame(sprites, &count, &sight_frames[14], 48+64*(p->aim%3), 16+40*(p->aim/3));
    }
    if (p->flash_field >= 0)
        append_frame(sprites, &count, &sight_frames[p->flash_frame],
                     48+64*(p->flash_field%3), 16+40*(p->flash_field/3));
    if (full) {
        range_region(sprites,count,16,8,240,136);
    } else {
        if (p->announced != last.announced)
            range_region(sprites,count,16,8,32,112);
        if (p->enemies != last.enemies)
            range_region(sprites,count,224,8,240,112);
        for (int i = 0; i < 9; ++i) {
            if (p->target[i] == last.target[i] &&
                (p->aim == i) == (last.aim == i) &&
                p->flash_field != i && last.flash_field != i) continue;
            unsigned x = 48+64*(i%3), y = 16+40*(i/3);
            range_region(sprites,count,x,y,x+32,y+32);
        }
    }
    initialized = true;
    last = *p;
}
