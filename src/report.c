#include "report.h"
#include "disc.h"
#include <string.h>

enum { WIDTH=192, HEIGHT=132 };
static uint8_t *scratch;
static size_t capacity;
static volatile uint16_t *screen;
static unsigned pitch, current, frames, row_count;
static const uint8_t *cursor,*end;
static uint16_t *pixels;
static uint16_t previous[HEIGHT], next[HEIGHT];
static bool valid;
extern void scene_wait(unsigned);

void report_close(void) { scratch=NULL; frames=0; }

bool report_open(uint8_t *buffer,size_t size,volatile uint16_t *target,unsigned stride)
{
    if (disc_read("GTERM.BIN",buffer,size)!=256*224*2) return false;
    for (unsigned y=0;y<224;y++)
        memcpy((void *)(target+y*stride),buffer+512*y,512);
    scratch=buffer;
    capacity=size;
    screen=target;
    pitch=stride;
    current=frames=0;
    valid=true;
    return true;
}

static unsigned be16(const uint8_t *p) { return (p[0]<<8)|p[1]; }

bool report_start(unsigned actor)
{
    if (!scratch || actor<20 || actor>32) return false;
    char name[]="GTERM00.BIN";
    name[5]+=(char)(actor/10);
    name[6]+=(char)(actor%10);
    size_t size=disc_read(name,scratch,capacity);
    if (size<8) return false;
    unsigned count=be16(scratch), rows=be16(scratch+2), colors=be16(scratch+4);
    size_t data=8+2*colors+rows*WIDTH, expanded=(size+1)&~(size_t)1;
    if (!rows || !colors || colors>256 || !count || data>=size ||
        expanded+rows*WIDTH*2>capacity) return false;
    const uint16_t *palette=(const uint16_t *)(scratch+8);
    const uint8_t *source=scratch+8+2*colors;
    pixels=(uint16_t *)(scratch+expanded);
    for (unsigned i=0;i<rows*WIDTH;i++) {
        if (source[i]>=colors) return false;
        pixels[i]=palette[source[i]];
    }
    current=actor;
    row_count=rows;
    cursor=scratch+data;
    end=scratch+size;
    frames=count;
    memset(previous,0xff,sizeof(previous));
    valid=true;
    return true;
}

void report_tick(void)
{
    if (!frames || !valid) return;
    valid=false;
    if (end-cursor<2) return;
    int shift=(int8_t)*cursor++;
    unsigned changed=*cursor++;
    if (changed>HEIGHT || end-cursor<3*(int)changed) return;
    for (int y=0;y<HEIGHT;y++)
        next[y]=(y+shift>=0 && y+shift<HEIGHT) ? previous[y+shift] : UINT16_MAX;
    for (unsigned i=0;i<changed;i++,cursor+=3) {
        unsigned y=cursor[0];
        if (y>=HEIGHT) return;
        next[y]=be16(cursor+1);
    }
    for (unsigned y=0;y<HEIGHT;y++) {
        if (next[y]>=row_count) return;
        if (previous[y]!=next[y])
            memcpy((void *)(screen+(14+y)*pitch+32),pixels+WIDTH*next[y],WIDTH*2);
    }
    memcpy(previous,next,sizeof(next));
    frames--;
    valid=frames!=0 || cursor==end;
}

bool report_wait(unsigned actor)
{
    if (!scratch || actor!=current) return false;
    while (frames && valid) scene_wait(1);
    return valid;
}
