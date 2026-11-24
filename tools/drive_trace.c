/* Capture the original VDP registers after each completed Sega CD frame.
 * The compiler uses only sprite geometry, palette and scroll values. */
#include <libretro.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <dlfcn.h>
static void save_vdp(void *core)
{
    static const uint8_t *reg,*colors,*scroll,*vram;
    static FILE *stream;
    if (!stream) {
        reg=dlsym(core,"reg");
        colors=dlsym(core,getenv("SNATCHER_SCAN_UPPER") ? "scan_palette" : "cram");
        scroll=dlsym(core,"vsram"); vram=dlsym(core,"vram");
        stream=fopen(getenv("SNATCHER_DRIVE_TRACE"),"wb");
        if (!reg || !colors || !scroll || !vram || !stream) exit(2);
    }
    if (fwrite(reg,1,32,stream)!=32 || fwrite(colors,1,128,stream)!=128 ||
        fwrite(scroll,1,128,stream)!=128 ||
        fwrite(vram+((reg[5]&127)<<9),1,640,stream)!=640 ||
        fwrite(vram+((reg[13]&63)<<10),1,4,stream)!=4) exit(2);
}
#define p_retro_run() (p_retro_run(),save_vdp(core))
#include "runner.c"
