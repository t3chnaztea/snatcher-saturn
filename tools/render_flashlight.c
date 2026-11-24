/* Capture both layers of the retail flashlight view separately. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dlfcn.h>

static uint16_t *front, *back;
static uint8_t *vram;

static void *open_core(const char *path,int flags)
{
    void *core=dlopen(path,flags);
    if (core) {
        front=dlsym(core,"ntab");
        back=dlsym(core,"ntbb");
        vram=dlsym(core,"vram");
    }
    return core;
}

static void capture_layer(unsigned frame)
{
    if (frame<14600 || frame>=14800) return;
    if (!front || !back || !vram || *back!=0xc000 || (*front!=0xe000 && *front!=0xa000)) abort();
    if (frame<14700) {
        *front=0xa000;
        memset(vram+0xa000,0,0x1000);
    } else {
        *front=0xe000;
        /* A solid room tile under the aperture exposes its dithered outline. */
        if (vram[255*32]!=0x77) abort();
        uint16_t *map=(uint16_t *)(vram+0xc000);
        for (unsigned i=0;i<0x800;i++) map[i]=0x20ff;
    }
}

#define dlopen open_core
#define p_retro_run() (capture_layer(frame),p_retro_run())
#include "render_plaza.c"
