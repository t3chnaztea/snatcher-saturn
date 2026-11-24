#include "flashlight.h"
#include "disc.h"
#include "plaza.h"
#include <yaul.h>
#include <string.h>

enum { WIDTH=192, HEIGHT=128, BEAM=47 };
struct lamp_data {
    uint16_t room[2][HEIGHT][WIDTH];
    uint8_t mask[BEAM][BEAM],targets[20][36];
};
static const struct lamp_data *const data=(const struct lamp_data *)VDP1_VRAM(0x20000);
static bool active;
static int x_eighths,y_eighths,last_x,last_y;
static unsigned ticks;
static uint32_t random_state;
extern void restore_scene_beneath_item(void),refresh_scene_item(void);

static volatile uint16_t *row_at(int x,int y)
{
    return (volatile uint16_t *)VDP2_VRAM_ADDR(0,0)+(8+y)*512+64+x;
}

static void erase(void)
{
    for (int y=0;y<BEAM;y++) {
        volatile uint16_t *dst=row_at(last_x,last_y+y);
        for (int x=0;x<BEAM;x++) dst[x]=0x8000;
    }
}

void flashlight_close(void)
{
    active=false;
}

bool flashlight_set(bool on,void *scratch,size_t capacity)
{
    if (active==on) return true;
    if (!on) {
        restore_scene_beneath_item();
        erase();
        refresh_scene_item();
        flashlight_close();
        return true;
    }
    size_t size=disc_read("QLIGHT.BIN",scratch,capacity);
    if (size!=sizeof(data->room)+sizeof(data->mask)+sizeof(data->targets)) return false;
    plaza_close();
    extern void fm_invalidate_scan(void);
    fm_invalidate_scan();
    memcpy((void *)data,scratch,size);
    last_x=73; last_y=41;
    x_eighths=y_eighths=0;
    random_state=1;
    ticks=0;
    active=true;
    flashlight_tick();
    return true;
}

/* The original rejects steps outside [-71,69) by [-39,37) and maps
 * four-pixel squares to SUBCODE's hotspot table. */
static int move_axis(int value,int direction,int low,int high)
{
    int step=value+direction*15;
    return step<low*8 ? low*8 : step>=high*8 ? high*8-1 : step;
}

bool flashlight_aim(bool aiming,int horizontal,int vertical)
{
    if (!active || !aiming) return false;
    x_eighths=move_axis(x_eighths,horizontal,-71,69);
    y_eighths=move_axis(y_eighths,vertical,-39,37);
    return true;
}

unsigned flashlight_target(void)
{
    if (!active) return 0;
    return data->targets[(y_eighths+40*8)/32][(x_eighths+72*8)/32];
}

void flashlight_tick(void)
{
    if (!active) return;
    restore_scene_beneath_item();
    erase();
    random_state=random_state*1664525u+1013904223u;
    last_x=(x_eighths+72*8)/8+1+(random_state>>31);
    last_y=(y_eighths+40*8)/8+1+((random_state>>30)&1);
    static const unsigned intensity[]={4,8,13,17,22,26,31};
    unsigned limit=ticks<96 ? intensity[ticks/16] : 31;
    unsigned palette=ticks<96 ? 1 : 1-((ticks-96)/4&1);
    ++ticks;
    for (int y=0;y<BEAM;y++) {
        volatile uint16_t *dst=row_at(last_x,last_y+y);
        const uint16_t *src=&data->room[palette][last_y+y][last_x];
        for (int x=0;x<BEAM;x++) {
            if (!data->mask[y][x]) continue;
            uint16_t color=src[x];
            if (limit<31) {
                unsigned r=color&31,g=(color>>5)&31,b=(color>>10)&31;
                color=0x8000 | (r<limit?r:limit) | ((g<limit?g:limit)<<5) | ((b<limit?b:limit)<<10);
            }
            dst[x]=color;
        }
    }
    refresh_scene_item();
}
