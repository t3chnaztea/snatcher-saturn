#include "script.h"
#include "disc.h"
#include "sound_bus.h"
#include <yaul.h>
#include "ponesound.h"
#include <string.h>

/* Voice PCM occupies at most 583,560 bytes of low WRAM. The factory thunder
 * source begins at 0x002e0000. The FM recording fits between those buffers. */
static uint8_t *const source=(uint8_t *)0x00292000;
enum { CAPACITY=0x4e000, HALF=16384, BASE=0x40000, SLOT=10 };
static unsigned length, next, elapsed, fps, sample_rate;
enum { SCAN_SAMPLES=64*22050, SCAN_VRAM=0x20000 };
static bool microscope, scan_cached;
static volatile bool scan_playing;
static uint16_t unpacked[1024] __attribute__((aligned(4)));
extern void scene_wait(unsigned);

static void refill(unsigned first, unsigned requested)
{
    unsigned count=first<length ? length-first : 0;
    if (count>requested) count=requested;
    unsigned dest=BASE+(first%(2*HALF))*2;
    if (count && microscope) {
        for (unsigned pos=0;pos<count;pos+=1024) {
            unsigned addr=(first+pos)/2;
            const uint8_t *chunk=addr<CAPACITY ? source+addr :
                (const uint8_t *)VDP1_VRAM(SCAN_VRAM+addr-CAPACITY);
            unsigned n=count-pos;
            if (n>1024) n=1024;
            for (unsigned i=0;i<n/2;i++) {
                unsigned v=chunk[i];
                unpacked[2*i]=(int16_t)(int8_t)(v&0xf0)*16;
                unpacked[2*i+1]=(int16_t)(int8_t)(v<<4)*16;
            }
            scd_sound_copy((volatile uint16_t *)SCSP_RAM(0),dest+pos*2,unpacked,n*2);
        }
    } else if (count) {
        scd_sound_copy((volatile uint16_t *)SCSP_RAM(0),dest,source+first*2,count*2);
    }
    static const uint8_t silence[1024]={0};
    for (unsigned pos=count*2;pos<requested*2;) {
        unsigned n=requested*2-pos;
        if (n>sizeof(silence)) n=sizeof(silence);
        scd_sound_copy((volatile uint16_t *)SCSP_RAM(0),dest+pos,silence,n);
        pos+=n;
    }
}

void fm_effect_stop(void)
{
    scan_playing=false;
    if (length) ((volatile uint16_t *)SCSP(0))[16*SLOT]=0x1000;
    length=0;
}

/* Scans use VDP2 for display. Stage the second part of the effect in unused
 * VDP1 texture RAM before loading the first part into the low WRAM buffer. */
void fm_invalidate_scan(void) { scan_cached=false; }

bool fm_prepare_scan(void)
{
    if (scan_cached) return true;
    fm_effect_stop();
    const unsigned tail=SCAN_SAMPLES/2-CAPACITY;
    volatile uint16_t *dst=(volatile uint16_t *)VDP1_VRAM(SCAN_VRAM);
    for (unsigned pos=0;pos<tail;pos+=32768) {
        unsigned bytes=tail-pos;
        if (bytes>32768) bytes=32768;
        if (!disc_read_sectors("FM2.BIN",(CAPACITY+pos)/2048,source,(bytes+2047)/2048)) return false;
        for (unsigned i=0;i<bytes/2;i++) *dst++=((const uint16_t *)source)[i];
    }
    scan_cached=disc_read_sectors("FM2.BIN",0,source,CAPACITY/2048);
    return scan_cached;
}

bool fm_effect_start(unsigned id)
{
    if (id==61) { fm_effect_stop(); return true; }
    static const char *const effects[] = {
        [5]="FM5.BIN", [6]="FM6.BIN", [14]="FM14.BIN", [13]="FM13.BIN", [8]="FM8.BIN", [9]="FM9.BIN", [10]="FM10.BIN", [26]="FM26.BIN",
        [21]="FM21.BIN", [35]="FM35.BIN", [33]="FM33.BIN", [42]="FM42.BIN", [46]="FM46.BIN", [48]="FM48.BIN", [53]="FM53.BIN", [59]="FM59.BIN"
    };
    if (id!=2 && (id>=sizeof(effects)/sizeof(effects[0]) || !effects[id])) return true;
    fm_effect_stop();
    microscope=id==2;
    sample_rate=(microscope || id==13 || id==14) ? 22050 : 44100;
    if (microscope && !fm_prepare_scan()) return false;
    if (!microscope) scan_cached=false;
    size_t bytes=microscope ? SCAN_SAMPLES*2 : disc_read(effects[id],source,CAPACITY);
    if (!bytes || (bytes&1)) return false;
    length=bytes/2;
    refill(0,HALF);
    refill(HALF,HALF);
    next=2*HALF;
    elapsed=0;
    fps=vdp2_tvmd_tv_standard_get()==VDP2_TVMD_TV_STANDARD_PAL ? 50 : 60;
    volatile uint16_t *slot=(volatile uint16_t *)SCSP(0)+16*SLOT;
    slot[0]=0x1000;
    slot[1]=slot[2]=0;
    slot[3]=2*HALF;
    slot[4]=slot[5]=31;
    slot[6]=slot[7]=slot[8]=slot[9]=slot[10]=0;
    slot[6]=script_audio_level(0);
    if (sample_rate==22050) slot[8]=15u<<11; /* Half the SCSP sample rate. */
    slot[11]=7<<13;
    slot[0]=0x1820|(BASE>>16); /* 16-bit forward-looped PCM at 44.1 kHz. */
    scan_playing=microscope;
    return true;
}

/* The CD reader may block across multiple VBlanks while staging a voice.
 * Keep the microscope’s independent sound slot fed during those reads. */
static volatile unsigned music_frames;

/* SP38's farewell voices occupy the first 166,866 bytes of low RAM.
 * Keep both music channels above them while VDP1 holds the current shot. */
enum { FAREWELL_COUNT=380100, FAREWELL_LOOP=3300, FAREWELL_PAGE=4096,
       FAREWELL_BASE=0x50000, FAREWELL_SLOT=11 };
static uint8_t *const farewell=(uint8_t *)0x00244000;
static unsigned farewell_at, farewell_page;
static volatile bool farewell_playing;
_Static_assert(2*FAREWELL_COUNT <= 0xbc000, "farewell music bank");

static void farewell_fill(unsigned page)
{
    unsigned filled=0;
    while (filled<FAREWELL_PAGE) {
        unsigned n=FAREWELL_COUNT-farewell_at;
        if (n>FAREWELL_PAGE-filled) n=FAREWELL_PAGE-filled;
        for (unsigned ch=0;ch<2;ch++)
            scd_sound_copy((volatile uint16_t *)SCSP_RAM(0),
                FAREWELL_BASE+(ch*4+page)*FAREWELL_PAGE+filled,
                farewell+ch*FAREWELL_COUNT+farewell_at,n);
        filled+=n;
        farewell_at+=n;
        if (farewell_at==FAREWELL_COUNT) farewell_at=FAREWELL_LOOP;
    }
}

static bool farewell_start(void)
{
    if (disc_read("FM80.BIN",farewell,0xbc000)!=2*FAREWELL_COUNT) return false;
    farewell_at=0;
    for (unsigned page=0;page<4;page++) farewell_fill(page);
    volatile uint16_t *slots=(volatile uint16_t *)SCSP(0)+16*FAREWELL_SLOT;
    for (unsigned ch=0;ch<2;ch++) {
        volatile uint16_t *slot=slots+16*ch;
        unsigned addr=FAREWELL_BASE+ch*4*FAREWELL_PAGE;
        slot[1]=addr&65535;
        slot[2]=0;
        slot[3]=4*FAREWELL_PAGE;
        slot[4]=slot[5]=31;
        slot[6]=script_audio_level(32);
        slot[7]=slot[9]=slot[10]=0;
        slot[8]=14u<<11;
        slot[11]=(7u<<13)|((ch?15u:31u)<<8);
        slot[0]=0x0830|(addr>>16)|(ch?0x1000:0);
    }
    farewell_page=0;
    farewell_playing=true;
    return true;
}

void fm_vblank(void)
{
    if (farewell_playing) {
        volatile uint16_t *monitor=(volatile uint16_t *)SCSP(0x408);
        *monitor=FAREWELL_SLOT<<11;
        unsigned page=(*monitor>>7)&3;
        while (farewell_page!=page) {
            farewell_fill(farewell_page);
            farewell_page=(farewell_page+1)&3;
        }
    }
    if (music_frames) --music_frames;
    if (!scan_playing) return;
    unsigned position=++elapsed*22050/fps;
    if (position>=length+735) { fm_effect_stop(); return; }
    if (position>=next-2*HALF+2048) {
        refill(next,512);
        next+=512;
    }
}

void fm_effect_tick(void)
{
    if (!length || microscope) return;
    unsigned position=++elapsed*sample_rate/fps;
    if (position>=length+735) { fm_effect_stop(); return; }
    if (position>=next-HALF+HALF/4) {
        refill(next,HALF);
        next+=HALF;
    }
}

void fm_effect_wait(void)
{
    for (unsigned frames=0;length && frames<600;frames++) scene_wait(1);
}

/* The inter-district turbocycle cue uses two one-shot SCSP slots. Keep it
 * resident in sound RAM while the drive animation reuses low work RAM. */
bool fm_music_start(unsigned id)
{
    enum { FIRST_SLOT=11, MUSIC_BASE=0x50000, CHANNEL_BYTES=0x18000 };
    static uint32_t buffer[2048];
    static unsigned samples;
    static unsigned cached_id;
    const char *file=id==69 ? "TRAVEL69.BIN" : id==70 ? "APT70.BIN" : NULL;
    if (!file && id!=80 && !music_frames && !farewell_playing) return true;
    farewell_playing=false;
    volatile uint16_t *slots=(volatile uint16_t *)SCSP(0)+16*FIRST_SLOT;
    slots[0]=0x1000;
    slots[16]=0x1000;
    music_frames=0;
    if (id==80) {
        cached_id=0;
        return farewell_start();
    }
    if (!file) return true;
    if (cached_id!=id) {
        cached_id=0;
        if (!disc_read_sectors(file,0,buffer,1)) return false;
        unsigned count=buffer[0];
        if (!count || count>CHANNEL_BYTES/2) return false;
        unsigned sectors=(count*2+2047)/2048;
        for (unsigned ch=0;ch<2;ch++) {
            for (unsigned at=0;at<sectors;) {
                unsigned n=sectors-at;
                if (n>sizeof(buffer)/2048) n=sizeof(buffer)/2048;
                if (!disc_read_sectors(file,1+ch*sectors+at,buffer,n)) return false;
                scd_sound_copy((volatile uint16_t *)SCSP_RAM(0),MUSIC_BASE+ch*CHANNEL_BYTES+at*2048,buffer,n*2048);
                at+=n;
            }
        }
        samples=count;
        cached_id=id;
    }
    for (unsigned ch=0;ch<2;ch++) {
        volatile uint16_t *slot=slots+ch*16;
        unsigned addr=MUSIC_BASE+ch*CHANNEL_BYTES;
        slot[1]=addr&65535;
        slot[2]=0;
        slot[3]=samples;
        slot[4]=slot[5]=31;
        slot[6]=script_audio_level(0);
        slot[7]=slot[9]=slot[10]=0;
        slot[8]=14u<<11;
        slot[11]=(7u<<13)|((ch?15u:31u)<<8);
        slot[0]=0x0800|(addr>>16)|(ch?0x1000:0);
    }
    unsigned hz=vdp2_tvmd_tv_standard_get()==VDP2_TVMD_TV_STANDARD_PAL?50:60;
    music_frames=(samples*hz+11024)/11025;
    return true;
}

void fm_music_wait(void)
{
    while (music_frames) scene_wait(1);
}
