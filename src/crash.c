#include "crash.h"
#include "disc.h"
#include "plaza.h"
#include <string.h>
#include <yaul.h>

enum { STATE_BYTES=65824, PALETTE_BYTES=128, PIXELS=192*128 };
static unsigned word(const uint8_t *p) { return (unsigned)p[0]<<8 | p[1]; }

static bool load_dictionary(uint8_t *scratch,uint8_t *bank,unsigned size)
{
    /* CRASHTIL is sector padded by the ISO. The movie header gives its exact size. */
    if (!size || size>0x60000 || (size&7)) return false;
    for (unsigned off=0;off<size;off+=32768) {
        unsigned n=size-off;
        if (n>32768) n=32768;
        if (!disc_read_sectors("CRASHTIL.BIN",off/2048,scratch,(n+2047)/2048)) return false;
        memcpy(bank+off,scratch,n);
    }
    return true;
}

bool crash_play(void *scratch,size_t capacity,volatile uint16_t *screen,unsigned pitch)
{
    uint8_t *movie=(uint8_t *)0x00200000;
    uint8_t *bank=(uint8_t *)VDP1_VRAM(0x20000);
    uint8_t *state=scratch,*pixels=state+STATE_BYTES+PALETTE_BYTES;
    uint8_t *background=pixels+PIXELS;
    uint8_t *atlas=(uint8_t *)0x002e0000;
    if (capacity<STATE_BYTES+PALETTE_BYTES+2*PIXELS) return false;
    plaza_close();
    extern void fm_invalidate_scan(void);
    fm_invalidate_scan();
    size_t bytes=disc_read("CRASH11.BIN",movie,0xe0000);
    if(bytes<8) return false;
    unsigned frames=word(movie+2);
    unsigned dict_size=(word(movie+4)<<16)|word(movie+6);
    if(word(movie) || !frames || !load_dictionary(state,bank,dict_size)) return false;
    memset(state,0,STATE_BYTES+PALETTE_BYTES);
    memset(atlas,0,131072);
    bool redraw=true;
    if(!disc_play_track(11)) return false;
    const uint8_t *pos=movie+8,*end=movie+bytes,*fixes=NULL;
    unsigned correction_count=0;
    while(frames) {
        if((size_t)(end-pos)<4) return false;
        unsigned sector=word(pos);
        if(!disc_wait_track_sector(sector)) return false;
        unsigned now=sector;
        disc_track_sector(&now);
        do {
            unsigned changes=word(pos+2),address=0;
            pos+=4;
            for(unsigned n=0;n<changes;n++){
                if(end-pos<3) return false;
                unsigned gap=*pos++;
                if(gap&128) {
                    if(end-pos<3) return false;
                    gap=((gap&127)<<8)|*pos++;
                }
                address+=gap;
                unsigned tile=word(pos);
                pos+=2;
                if(address>=(STATE_BYTES+PALETTE_BYTES)/8 || tile>=dict_size/8) return false;
                uint32_t *to=(uint32_t *)(state+address*8);
                const uint32_t *from=(const uint32_t *)(bank+tile*8);
                to[0]=from[0];to[1]=from[1];
                unsigned off=address*8;
                if (off<16 || off==160) redraw=true;
                if (off>=288 && off<STATE_BYTES) {
                    unsigned v=off-288;
                    crash_decode(state+288,atlas,v);
                    /* SP29 uses C000/E000 for maps and F800 for scroll.
                     * Sprite attributes at FE00 never enter either plane. */
                    if (v<0xf000 || v==0xf800) redraw=true;
                }
            }
            if(end-pos<2) return false;
            unsigned count=word(pos);
            pos+=2;
            if(count!=0xffff) {
                if(end-pos<(int)(count*4)) return false;
                fixes=pos;correction_count=count;pos+=count*4;
            }
            --frames;
            if(frames && end-pos<4) return false;
        } while(frames && word(pos)<=now);
        if (redraw) {
            crash_background(state,atlas,background);
            redraw=false;
        }
        memcpy(pixels,background,PIXELS);
        crash_sprites(state,atlas,pixels);
        const uint16_t *palette=(const uint16_t *)(state+STATE_BYTES);
        for(unsigned y=0;y<128;y++) {
            volatile uint16_t *row=screen+(8+y)*pitch+32;
            const uint8_t *src=pixels+y*192;
            for(unsigned x=0;x<192;x++) row[x]=palette[src[x]&63];
        }
        for(unsigned n=0;n<correction_count;n++){
            unsigned at=word(fixes+4*n);
            if(at>=PIXELS) return false;
            screen[(8+at/192)*pitch+32+at%192]=word(fixes+4*n+2);
        }
    }
    return pos==end;
}
