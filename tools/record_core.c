/* Add frame output to the same libretro host used for the retail comparisons. */
#include <libretro.h>
#include <stdio.h>
#include <stdlib.h>

static void movie_frame(void);
static void movie_input(void);
#define SNATCHER_PRE_FRAME() movie_input()
static void movie_timing(const struct retro_system_av_info *av)
{
    printf("{\"fps\":%.12f}\n",av->timing.fps);
    fflush(stdout);
}
#define SNATCHER_POST_FRAME() movie_frame()
#define p_retro_get_system_av_info(av) (p_retro_get_system_av_info(av), movie_timing(av))
#include "backup_core.c"
#undef p_retro_run
#undef p_retro_get_system_av_info

/* One native-endian button mask per frame, including released buttons. */
static void movie_input(void)
{
    static FILE *pad;
    if (!pad) {
        const char *path=getenv("SNATCHER_MOVIE_INPUT");
        if (!path) return;
        pad=fopen(path,"rb");
        if (!pad) fail("Cannot read movie input");
    }
    uint16_t buttons;
    if (fread(&buttons,sizeof(buttons),1,pad)!=1) fail("Truncated movie input");
    mask=buttons;
}

static void movie_frame(void)
{
    static FILE *stream;
    static unsigned char canvas[224][330*3];
    if (!stream) {
        const char *fd = getenv("SNATCHER_MOVIE_FD");
        if (!fd || !(stream=fdopen(atoi(fd),"wb"))) fail("Missing movie stream");
    }
    if (rgb && width == 330 && height == 224) {
        if (fwrite(rgb,1,sizeof(canvas),stream) != sizeof(canvas)) fail("Movie write failed");
        return;
    }
    /* The BIOS can switch resolution. Preserve the full picture during switches. */
    if (rgb && width && height) {
        for (unsigned y=0; y<224; ++y)
            for (unsigned x=0; x<330; ++x)
                memcpy(canvas[y]+3*x,rgb+3*((y*height/224)*width+x*width/330),3);
    }
    if (fwrite(canvas,1,sizeof(canvas),stream) != sizeof(canvas)) fail("Movie write failed");
}
