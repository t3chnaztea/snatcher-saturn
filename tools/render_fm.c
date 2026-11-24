/* Run the original FM driver from the verified data track. The libretro
 * memory map identifies sub-CPU program RAM. No emulator state is needed. */
#include <libretro.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static bool render_environment(unsigned,void *);
static void send_commands(unsigned);
#define p_retro_set_environment(callback) p_retro_set_environment(render_environment)
#define p_retro_run() (send_commands(frame),p_retro_run())
#include "runner.c"

static uint8_t *program_ram;
static bool render_environment(unsigned cmd,void *data)
{
    if (cmd==RETRO_ENVIRONMENT_SET_MEMORY_MAPS) {
        const struct retro_memory_map *map=data;
        for (unsigned i=0;i<map->num_descriptors;i++) {
            const struct retro_memory_descriptor *m=&map->descriptors[i];
            if (m->addrspace && !strcmp(m->addrspace,"PRGRAM") && m->len==0x80000)
                program_ram=(uint8_t *)m->ptr+m->offset;
        }
        return true;
    }
    if (cmd==RETRO_ENVIRONMENT_GET_VARIABLE) {
        struct retro_variable *v=data;
        if (!strcmp(v->key,"genesis_plus_gx_pcm_volume") || !strcmp(v->key,"genesis_plus_gx_cdda_volume")) {
            v->value="0";
            return true;
        }
    }
    return environment(cmd,data);
}

static void send_commands(unsigned n)
{
    static const struct { unsigned frame, effect; } script[] = {
        {1750,255}, {1900,48}, {2200,53}, {2600,2}, {6600,61},
        {6800,26}, {7100,8}, {7400,9}, {7700,10}, {8000,21},
        {8300,33}, {8600,46}, {8900,13}, {9450,42}, {9750,6}, {10250,14}, {10750,255}, {10850,69}, {11300,255}, {11400,35}, {12000,61}, {12100,255}, {12200,70}, {12650,255}, {12700,59}, {13150,255}, {13200,5}, {13500,255}, {13600,80}, {15750,255}
    };
    static unsigned position;
    if (position==sizeof(script)/sizeof(script[0]) || n!=script[position].frame) return;
    unsigned id=script[position++].effect;
    if (!program_ram) fail("Missing sub-CPU program RAM");
    static const uint16_t signature[]={0x4eb9,0x0001,0x6984,0x41f9,0x0001,0x5400};
    if (memcmp(program_ram+0x16974,signature,sizeof(signature))) fail("Retail sound driver has not booted");
    /* Genesis Plus GX stores 68000 words in host order. */
    const uint16_t test=1;
    const unsigned lane=*(const uint8_t *)&test;
    unsigned next=program_ram[0x7f87f^lane];
    if (next>=128 || next!=program_ram[0x7f87e^lane]) fail("FM command buffer is busy");
    program_ram[(0x7f880+next)^lane]=id;
    program_ram[0x7f87f^lane]=(next+1)&127;
    if (n!=1750) printf("FM%u %u\n",id,audio_frames);
}
