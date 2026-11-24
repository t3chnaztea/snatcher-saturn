/* Attach a Stunner to port two. Port one replays the ordinary investigation. */
#include <libretro.h>
#include <stdio.h>
#include <stdlib.h>
static int16_t gun_input(unsigned,unsigned,unsigned,unsigned);
#define p_retro_set_input_state(cb) p_retro_set_input_state(gun_input)
#define p_retro_set_controller_port_device(port,id) (p_retro_set_controller_port_device(port,id),p_retro_set_controller_port_device(1,RETRO_DEVICE_SUBCLASS(RETRO_DEVICE_LIGHTGUN,1)))
#include "backup_core.c"

static int16_t gun_input(unsigned port,unsigned device,unsigned index,unsigned id)
{
    if (port!=1 || device!=RETRO_DEVICE_LIGHTGUN) return input(port,device,index,id);
    static struct { unsigned first,last; int x,y,off; } shots[256];
    static unsigned count,next;
    static bool initialized;
    if (!initialized) {
        const char *name=getenv("SNATCHER_GUN_INPUT");
        FILE *f=name?fopen(name,"r"):NULL;
        if (!f) fail("Missing gun input");
        while (count<256 && fscanf(f,"%u %u %d %d %d",&shots[count].first,&shots[count].last,
                                  &shots[count].x,&shots[count].y,&shots[count].off)==5) {
            if (shots[count].last<shots[count].first ||
                (count && shots[count].first<=shots[count-1].last)) fail("Overlapping gun inputs");
            ++count;
        }
        if (!feof(f)) fail("Invalid gun input");
        fclose(f); initialized=true;
    }
    while (next<count && frame>shots[next].last) ++next;
    if (!count) return 0;
    /* A released trigger leaves the gun pointing at the last field. The Saturn
     * may sample the flash after release, before the following shot starts. */
    bool pressed=next<count && frame>=shots[next].first;
    unsigned aim=pressed || !next ? next : next-1;
    if (id==RETRO_DEVICE_ID_LIGHTGUN_SCREEN_X) return shots[aim].x;
    if (id==RETRO_DEVICE_ID_LIGHTGUN_SCREEN_Y) return shots[aim].y;
    if (id==RETRO_DEVICE_ID_LIGHTGUN_TRIGGER) return pressed;
    if (id==RETRO_DEVICE_ID_LIGHTGUN_IS_OFFSCREEN) return shots[aim].off;
    return 0;
}
