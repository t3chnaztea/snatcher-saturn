/* Record the viewport and the matching end-of-frame VDP state during track 11.
 * SP29 changes the palette during the frame. Fit the viewport palette to the
 * displayed colors and retain exceptions at their original pixel positions. */
#include <libretro.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "crash_graphics.c"

static int (*transport)(uint8_t *);
static const uint8_t *regs,*cram,*vsram,*vram;
static void *open_core(const char *path,int flags)
{
    void *core=dlopen(path,flags);
    if (core) {
        transport=dlsym(core,"cdd_context_save");
        regs=dlsym(core,"reg"); cram=dlsym(core,"cram");
        vsram=dlsym(core,"vsram"); vram=dlsym(core,"vram");
    }
    return core;
}
static void capture(const void *,unsigned,unsigned,size_t);
#define dlopen open_core
#define p_retro_set_video_refresh(cb) p_retro_set_video_refresh(capture)
#include "runner.c"

static void put16(FILE *file,unsigned value)
{
    if (fputc(value>>8,file)==EOF || fputc(value&255,file)==EOF) fail("Cannot write track 11 frame");
}

static unsigned saturn_color(unsigned code)
{
    unsigned word=0x8000;
    for (unsigned shift=0;shift<3;shift++)
        word|=(((code>>(3*shift))&7)*255/7*31/255)<<(5*shift);
    return word;
}

static void capture(const void *data,unsigned width,unsigned height,size_t pitch)
{
    video(data,width,height,pitch);
    if (!rgb || width!=256 || height!=224 || frame+1<13859 || frame+1>20289) return;
    static FILE *file;
    if (!file) file=fopen("crash.raw","wb");
    uint8_t drive[64]; int track,lba;
    if (!file || !transport || !regs || !cram || !vsram || !vram || transport(drive)!=33)
        fail("Cannot capture track 11 video state");
    memcpy(&track,drive+8,4); memcpy(&lba,drive+12,4);
    if (track!=10 || lba<139157 || lba>=147155) fail("Unexpected track 11 CD position");
    put16(file,lba-139157);
    static uint8_t state[65824],indices[192*128];
    memcpy(state,regs,32); memcpy(state+32,cram,128);
    memcpy(state+160,vsram,128); memcpy(state+288,vram,65536);
    if (fwrite(state,1,sizeof(state),file)!=sizeof(state)) fail("Cannot write track 11 VDP data");
    static uint8_t atlas[131072];
    for (unsigned off=0;off<65536;off+=8) crash_decode(vram,atlas,off);
    crash_background(state,atlas,indices);
    crash_sprites(state,atlas,indices);
    static uint16_t counts[64][512],palette[64],pixels[192*128];
    memset(counts,0,sizeof(counts));
    for (unsigned row=0;row<128;row++) for (unsigned x=0;x<192;x++) {
        const uint8_t *src=rgb+3*((row+8)*256+x+32);
        unsigned color=0;
        for (unsigned k=0;k<3;k++) {
            unsigned level=(src[k]+17)/34;
            color|=(level>7?7:level)<<(3*k);
        }
        unsigned pos=row*192+x;
        pixels[pos]=color;
        ++counts[indices[pos]&63][color];
    }
    for (unsigned i=0;i<64;i++) {
        unsigned best=0;
        for (unsigned c=0;c<512;c++) if (counts[i][c]>best) { best=counts[i][c];palette[i]=c; }
        put16(file,saturn_color(palette[i]));
    }
    unsigned count=0;
    for (unsigned i=0;i<192*128;i++) count+=palette[indices[i]&63]!=pixels[i];
    put16(file,count);
    for (unsigned i=0;i<192*128;i++) if (palette[indices[i]&63]!=pixels[i]) {
        put16(file,i); put16(file,saturn_color(pixels[i]));
    }
}
