/* The field under test is Beetle's internal backup RAM. Hand only those bytes
 * to the next cold boot. The normal runner handles pad input and capture. */
#include <libretro.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdbool.h>
static uint8_t *battery;
static bool open_backup(void *core)
{
    if (!getenv("SNATCHER_BACKUP_OUTPUT")) return !getenv("SNATCHER_BACKUP_INPUT");
    void *(*data)(unsigned)=dlsym(core,"retro_get_memory_data");
    size_t (*size)(unsigned)=dlsym(core,"retro_get_memory_size");
    if (!data || !size || size(RETRO_MEMORY_SAVE_RAM)!=32768) return false;
    battery=data(RETRO_MEMORY_SAVE_RAM);
    if (!battery) return false;
    const char *path=getenv("SNATCHER_BACKUP_INPUT");
    if (!path) return true;
    FILE *f=fopen(path,"rb");
    if (!f) return false;
    bool ok=fread(battery,1,32768,f)==32768 && fgetc(f)==EOF;
    fclose(f);
    return ok;
}
static void close_backup(void)
{
    if (!battery) return;
    FILE *f=fopen(getenv("SNATCHER_BACKUP_OUTPUT"),"wb");
    if (!f || fwrite(battery,1,32768,f)!=32768 || fclose(f)) exit(2);
}
static void check_reset(void *core,unsigned frame)
{
    static unsigned when;
    if (!frame && getenv("SNATCHER_RESET_FRAME")) when=strtoul(getenv("SNATCHER_RESET_FRAME"),NULL,10);
    if (when && frame==when) {
        void (*reset)(void)=dlsym(core,"retro_reset");
        if (!reset) exit(2);
        reset();
    }
}
#define p_retro_load_game(game) (p_retro_load_game(game) && open_backup(core))
#define p_retro_unload_game() (close_backup(),p_retro_unload_game())
#ifndef SNATCHER_POST_FRAME
#define SNATCHER_POST_FRAME() ((void)0)
#endif
#ifndef SNATCHER_PRE_FRAME
#define SNATCHER_PRE_FRAME() ((void)0)
#endif
#define p_retro_run() (SNATCHER_PRE_FRAME(),check_reset(core,frame),p_retro_run(),SNATCHER_POST_FRAME())
#include "runner.c"
