#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>

static const uint8_t *sprite_vram;
static const uint16_t *sprite_cram;
static int (*transport)(uint8_t *);
static void *open_core(const char *path,int flags)
{
    void *core=dlopen(path,flags);
    if (core) {
        transport=dlsym(core,"cdd_context_save");
        sprite_vram=dlsym(core,"vram");
        sprite_cram=dlsym(core,"cram");
    }
    return core;
}

static void record_transport(unsigned frame)
{
    bool ceiling=frame==14200 && getenv("SNATCHER_CEILING_PATTERNS");
    bool mika=frame==18780 && getenv("SNATCHER_MIKA_PATTERNS");
    bool swarm=frame==164500 && getenv("SNATCHER_SWARM_PATTERNS");
    bool final13=frame==169380 && getenv("SNATCHER_FINAL13_PATTERNS");
    bool final14=frame==172440 && getenv("SNATCHER_FINAL13_PATTERNS");
    if (final14 || final13 || swarm || mika || ceiling || (frame==14000 && getenv("SNATCHER_TAXI_PATTERNS"))) {
        FILE *out=fopen(final14?"FINAL14.BIN":final13?"FINAL13.BIN":swarm?"SWARM.BIN":mika?"MFIGHT.BIN":ceiling?"HFIGHT.BIN":"TFIGHT.BIN","wb");
        if (!out || !sprite_vram || !sprite_cram) exit(1);
        for (unsigned i=0;i<65536;i++) fputc(sprite_vram[i^1],out);
        for (unsigned i=0;i<64;i++) {
            unsigned raw=sprite_cram[i];
            unsigned color=0x8000;
            for (unsigned channel=0;channel<3;channel++)
                color|=(((raw>>(3*channel))&7)*31/7)<<(5*channel);
            fputc(color>>8,out);
            fputc(color&255,out);
        }
        if (fclose(out)) exit(1);
    }
    static FILE *file;
    if (!file) file=fopen("transport.tsv","w");
    uint8_t raw[64];
    int track,lba;
    if (!file || !transport || transport(raw)!=33) {
        fprintf(stderr,"Unsupported Genesis Plus GX CD transport state\n");
        exit(1);
    }
    memcpy(&track,raw+8,4);
    memcpy(&lba,raw+12,4);
    fprintf(file,"%u %d %d %u\n",frame,track,lba,raw[24]&15);
}
#define RECORD_TRANSPORT(frame) record_transport(frame)
#define dlopen open_core
#include "render_plaza.c"
