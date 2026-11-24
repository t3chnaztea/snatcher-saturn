#include "street.h"
#include "disc.h"
#include "drive.h"
#include <string.h>

enum { WIDTH=192, HEIGHT=128, BANK_SIZE=0xf4000 };
static uint8_t *const bank=(uint8_t *)0x00200000;
static uint8_t (*const pixels)[HEIGHT][WIDTH]=(void *)0x002f4000;
static const uint8_t *cursor,*end,*loop;
static const uint16_t *palette;
static volatile uint16_t *screen;
static unsigned pitch,page,remaining,delay;

void street_close(void)
{
    if (!cursor) return;
    if (page && !loop) {
        for (unsigned y=8;y<136;y++)
            memcpy((void *)(screen+y*pitch+32),(const void *)(screen+0x20000+y*pitch+32),WIDTH*2);
        bitmap_page(0);
    }
    cursor=loop=NULL;
}

static bool street_stream(const uint8_t *stream)
{
    if (end-stream<4) return false;
    unsigned colors=(stream[0]<<8)|stream[1];
    remaining=(stream[2]<<8)|stream[3];
    if (!colors || colors>128 || !remaining || end-stream<=4+colors*2) return false;
    palette=(const uint16_t *)(stream+4);
    cursor=stream+4+colors*2;
    memset(pixels[page],0,HEIGHT*WIDTH);
    return true;
}

void street_tick(void)
{
    if (!cursor) return;
    if (delay) { --delay; return; }
    if (!remaining && (!loop || !street_stream(loop))) return;
    if (end-cursor<2) { street_close(); return; }
    unsigned duration=(cursor[0]<<8)|cursor[1];
    cursor+=2;
    unsigned dest=page^1;
    for (unsigned y=0;y<HEIGHT;y++) {
        if (end-cursor<2) { street_close(); return; }
        unsigned ref=*cursor++,spans=*cursor++;
        if (ref>=HEIGHT) { street_close(); return; }
        uint8_t *row=pixels[dest][y];
        memcpy(row,pixels[page][ref],WIDTH);
        for (unsigned run=0;run<spans;run++) {
            if (end-cursor<2) { street_close(); return; }
            unsigned x=*cursor++,width=*cursor++;
            if (x+width>WIDTH || end-cursor<(int)width) { street_close(); return; }
            memcpy(row+x,cursor,width);
            cursor+=width;
        }
        volatile uint16_t *out=screen+(loop?0:dest)*0x20000+(8+y)*pitch+32;
        for (unsigned x=0;x<WIDTH;x++) out[x]=palette[row[x]];
    }
    if (!loop) bitmap_page(dest);
    page=dest;
    remaining--;
    delay=duration ? duration-1 : 0;
}

void street_finish_pan(void)
{
    extern void scene_wait(unsigned);
    while (cursor && !loop && remaining) scene_wait(1);
    street_close();
}

bool street_open(volatile uint16_t *target,unsigned stride,const char *file,bool returning)
{
    unsigned size=disc_read(file,bank,BANK_SIZE);
    if (size<8) return false;
    end=bank+size;
    loop=NULL;
    if (returning) {
        unsigned offset=(bank[0]<<24)|(bank[1]<<16)|(bank[2]<<8)|bank[3];
        if (offset<8 || offset>=size || (offset&1)) return false;
        loop=bank+offset;
    }
    pitch=stride;
    screen=target;
    delay=page=0;
    if (!street_stream(bank+(returning?4:0))) return false;
    for (unsigned y=0;y<224;y++) {
        for (unsigned x=0;x<256;x++) target[y*stride+x]=0x8000;
        memcpy((void *)(target+0x20000+y*stride-32),(const void *)(target+y*stride-32),320*2);
    }
    street_tick();
    return cursor!=NULL;
}
