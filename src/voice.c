#include "script.h"
#include <yaul.h>
#include <string.h>
#include "disc.h"
#include "ponesound.h"
#include "sound_bus.h"

extern uint8_t sound_driver[], sound_driver_end[];
extern int ponesound_driver_copy_ok;
extern sysComPara *m68k_com;
enum { RATE = 16276, BASE = 0x10000, HALF = 16384 };
/* The largest retail line is 583,560 samples. Stage it in the 1 MiB
 * low work RAM bank so a disc seek cannot interrupt a line in progress. */
static uint8_t *const samples = (uint8_t *)0x00200000;
static struct { uint32_t sector, length; } voices[2048];
static uint8_t mix[2048][2] __attribute__((aligned(4)));
static bool ready, resident_blocked;
static struct { uint16_t sector, count; } resident_banks[512];
void resident_block(bool blocked) { resident_blocked=blocked; }
struct range_sample { unsigned offset, length, pitch, level, unit; };
#include "range_pcm.h"

static bool load_resident(const char *file)
{
    size_t size = disc_read(file, samples, 0x20000);
    if (!size) return false;
    scd_sound_copy((volatile uint16_t *)SCSP_RAM(0), 0x20000, samples, size);
    return true;
}

static void resident_sound(const struct range_sample *s)
{
    if (resident_blocked) return;
    unsigned address = 0x20000 + s->offset;
    volatile uint16_t *slot = (volatile uint16_t *)SCSP(0) + 16*(2+s->unit);
    slot[0] = 0x1000;
    slot[1] = address & 65535;
    slot[2] = 0;
    bool ring=s->length>65535;
    slot[3] = ring ? 2*HALF : s->length;
    slot[4] = slot[5] = 31;
    slot[6] = script_audio_level(s->level);
    slot[7] = 0;
    unsigned hz = (RATE*s->pitch+512)/1024;
    unsigned octave = 14, base = 11025;
    if (hz >= 22050) { octave = 15; base = 22050; }
    slot[8] = (octave << 11) | ((hz-base)*1024+base/2)/base;
    slot[9] = slot[10] = 0;
    slot[11] = 7 << 13;
    slot[0] = 0x1800 | 0x10 | (ring ? 0x20 : 0) | (address>>16);
}

/* The full thunder recording exceeds one SCSP slot's 16-bit end address.
 * Keep the source above the voice staging area and refill a separate slot. */
static uint8_t *const storm=(uint8_t *)0x002e0000;
static unsigned storm_frame,storm_next;
void storm_stop(void)
{
    if (storm_next) ((volatile uint16_t *)SCSP(0))[16*(2+storm_samples[0].unit)]=0x1000;
    storm_next=0;
}
void storm_sound(void)
{
    if (resident_blocked) return;
    scd_sound_copy((volatile uint16_t *)SCSP_RAM(0),0x20000,storm,2*HALF);
    resident_sound(storm_samples);
    storm_frame=0;
    storm_next=2*HALF;
}
void storm_tick(void)
{
    if (!storm_next) return;
    unsigned rate=(RATE*storm_samples[0].pitch+512)/1024;
    unsigned fps=vdp2_tvmd_tv_standard_get()==VDP2_TVMD_TV_STANDARD_PAL ? 50 : 60;
    unsigned position=++storm_frame*rate/fps;
    if (position>=storm_samples[0].length+1024) { storm_stop(); return; }
    if (position<storm_next-HALF+HALF/4) return;
    scd_sound_copy((volatile uint16_t *)SCSP_RAM(0),0x20000+storm_next%(2*HALF),storm+storm_next,HALF);
    storm_next+=HALF;
}

void scream_sound(void) { resident_sound(&lisa_samples[2]); }

void church_door_sound(void) { resident_sound(church_door_samples); }

void door_knock(void) { resident_sound(knock_samples); }

void garden_bark(void) { resident_sound(garden_samples); }

void taxi_sound(void) { resident_sound(taxi_samples); }

/* Bank 33 replaces the same SCSP memory used by bank 20. */
void ceiling_sound(void)
{
    extern uint32_t video_clock(void);
    extern void scene_wait(unsigned);
    unsigned fps=vdp2_tvmd_tv_standard_get()==VDP2_TVMD_TV_STANDARD_PAL ? 50 : 60;
    unsigned rate=(RATE*taxi_samples[0].pitch+512)/1024;
    uint32_t start=video_clock();
    taxi_sound();
    while ((video_clock()-start)*rate < taxi_samples[0].length*fps) scene_wait(1);
}

void shadow_sound(void) { resident_sound(shadow_samples); }

void drip_sound(void) { resident_sound(drip_samples); }

void canopy_sound(void)
{
    resident_sound(canopy_samples);
}

void blaster_sound(void)
{
    resident_sound(blaster_samples);
}

void navigator_sound(void)
{
    resident_sound(navigator_samples);
}

void range_sound(unsigned id)
{
    if (id>=71 && id<=73) resident_sound(&final_samples[id-71]);
    else if (id>=64 && id<=68) resident_sound(&ceiling_samples[id-64]);
    else if (id >= 13 && id <= 16) resident_sound(&range_samples[id-13]);
    else if (id>=49 && id<=55) resident_sound(&lisa_samples[id-49]);
    else if (id>=59 && id<=62) resident_sound(&ivan_samples[id-59]);
    else if (id >= 45 && id <= 48) resident_sound(&factory_samples[id-45]);
}

void voice_init(void)
{
    ponesound_load_driver(sound_driver, sound_driver_end - sound_driver, ADX_MASTER_768);
    for (unsigned frame = 0; frame < 600 && m68k_com->start != 0x7777; frame++) {
        vdp2_sync();
        vdp2_sync_wait();
    }
    /* Route the CD block's stereo input through SCSP slots 16 and 17. */
    m68k_com->cdda_left_channel_vol_pan=0xff;
    m68k_com->cdda_right_channel_vol_pan=0xef;
    MEMORY_WRITE(16,SCSP(0x216),0x00ff);
    MEMORY_WRITE(16,SCSP(0x236),0x00ef);
    ready = ponesound_driver_copy_ok && m68k_com->start == 0x7777 &&
            disc_read_sectors("VOICE.BIN", 0, voices, sizeof(voices)/2048) &&
            disc_read("MIX.BIN", mix, sizeof(mix)) == sizeof(mix) &&
            disc_read_sectors("RESIDENT.BIN",0,resident_banks,1);
}

/* Refill the half the sound chip has passed. The spare quarter-buffer
 * tolerates command latency and display-clock variation on NTSC and PAL. */
bool voice_play(unsigned id)
{
    if (!ready || id >= 2048) return false;
    if (id==255) return true; /* Stop: streamed cues finish synchronously. */
    if (id==2) {
        size_t bytes=disc_read("STORM.BIN",storm,0x20000);
        if (bytes!=(storm_samples[0].length+1u)/2*2) return false;
        memset(storm+bytes,0,0x20000-bytes);
        return true;
    }
    if (id == 1) return load_resident("RANGEPCM.BIN");
    if (id == 5) return load_resident("FACTPCM.BIN");
    if (id==6) {
        if (!load_resident("DRIP.BIN")) return false;
        extern void drip_bank_ready(void);
        drip_bank_ready();
        return true;
    }
    if (id == 8) return load_resident("SHADOW.BIN");
    if (id == 7) return load_resident("NAVPCM.BIN");
    if (id == 20) return load_resident("BODYPCM.BIN");
    if (id == 16) return load_resident("CARPCM.BIN");
    if (id == 32) return load_resident("GUNPCM.BIN");
    if (id<512 && resident_banks[id].count) {
        unsigned count=resident_banks[id].count;
        if (count>64 || !disc_read_sectors("RESIDENT.BIN",resident_banks[id].sector,samples,count)) return false;
        scd_sound_copy((volatile uint16_t *)SCSP_RAM(0),0x20000,samples,count*2048);
        return true;
    }
    size_t length = voices[id].length;
    if (!length || length > 0x100000) return false;
    if (!disc_read_sectors("VOICE.BIN", voices[id].sector, samples, (length + 2047)/2048))
        return false;
    if (length < HALF * 2) memset(samples + length, 0, HALF * 2 - length);
    scd_sound_copy((volatile uint16_t *)SCSP_RAM(0), BASE, samples, HALF * 2);
    /* Both slots read the same ring. Latch both key-on bits before executing
     * the command so the left and right streams start on the same sample. */
    volatile uint16_t *slots = (volatile uint16_t *)SCSP(0);
    slots[0] = 0;
    slots[16] = 0x1000;
    for (unsigned channel = 0; channel < 2; channel++) {
        volatile uint16_t *slot = slots + channel*16;
        slot[1] = BASE & 0xffff;
        slot[2] = 0;
        slot[3] = HALF * 2;
        slot[4] = slot[5] = 31;
        slot[6] = script_audio_level(mix[id][channel]);
        slot[7] = 0;
        slot[8] = (14u << 11) | (((RATE - 11025u) * 1024 + 5512) / 11025);
        slot[9] = slot[10] = 0;
        unsigned level = mix[id][channel] == 255 ? 0 : 7;
        slot[11] = (level << 13) | ((channel == 0 ? 31u : 15u) << 8);
        slot[0] = 0x800 | 0x20 | 0x10 | (BASE >> 16) | (channel ? 0x1000 : 0);
    }
    unsigned fps = vdp2_tvmd_tv_standard_get() == VDP2_TVMD_TV_STANDARD_PAL ? 50 : 60;
    unsigned next = HALF * 2;
    extern uint32_t video_clock(void);
    const uint32_t start=video_clock();
    /* The SCSP keeps playing when a picture update takes two refreshes. */
    while ((video_clock()-start)*RATE < (length+1024)*fps) {
        vdp2_sync();
        vdp2_sync_wait();
        unsigned elapsed=video_clock()-start;
        if (elapsed*RATE >= (next-HALF+HALF/4)*fps) {
            unsigned bank=BASE+next%(2*HALF);
            size_t count=next<length ? length-next : 0;
            if (count>HALF) count=HALF;
            if (count) scd_sound_copy((volatile uint16_t *)SCSP_RAM(0),bank,samples+next,count);
            if (count<HALF) {
                static const uint8_t zeros[HALF]={0};
                scd_sound_copy((volatile uint16_t *)SCSP_RAM(0),bank+count,zeros,HALF-count);
            }
            next+=HALF;
        }
        extern void presentation_tick(void);
        presentation_tick();
    }
    slots[0] = 0;
    slots[16] = 0x1000;
    return true;
}
