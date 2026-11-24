#include "drive.h"
#include "disc.h"
#include <yaul.h>
#include <string.h>

extern void scene_wait(unsigned frames);
static const struct sequence *const sequence=(const struct sequence *)0x00200000;
static unsigned size;
static bool track_timed;

bool drive_load(bool transit)
{
    /* PCM lines use this bank before and after the fixed CD-audio sequence. */
    extern void fm_effect_stop(void);
    fm_effect_stop();
    track_timed=!transit;
    size=disc_read(transit?"TRANSIT.BIN":"DRIVE.BIN",(void *)sequence,0x100000);
    return size>=sizeof(*sequence) && sequence->updates>=sizeof(*sequence) &&
           sequence->tiles>=sequence->updates && sequence->tiles<=size;
}

void bitmap_page(unsigned page)
{
    const vdp2_scrn_bitmap_format_t fmt={
        .scroll_screen=VDP2_SCRN_NBG0,.ccc=VDP2_SCRN_CCC_RGB_32768,
        .bitmap_size=VDP2_SCRN_BITMAP_SIZE_512X256,.bitmap_base=VDP2_VRAM_ADDR(page*2,0)
    };
    vdp2_scrn_bitmap_base_set(&fmt);
}

static void draw_tile(volatile uint16_t *screen,unsigned stride,unsigned cell,unsigned tile)
{
    const uint8_t *src=(const uint8_t *)sequence+sequence->tiles+tile*64;
    volatile uint16_t *dst=screen+(8+8*(cell/24))*stride+32+8*(cell%24);
    for (unsigned y=0;y<8;y++,dst+=stride)
        for (unsigned x=0;x<8;x++) dst[x]=sequence->colors[*src++];
}

bool drive_section(unsigned index,volatile uint16_t *screen,unsigned stride)
{
    if (index>=5 || !size) return false;
    const uint8_t *bytes=(const uint8_t *)sequence;
    const struct update *updates=(const struct update *)(bytes+sequence->updates);
    const struct section section=sequence->sections[index];
    if (section.first+section.count>(sequence->updates-sizeof(*sequence))/sizeof(struct pose)) return false;
    /* The middle shots follow the disc clock, including any missed VBlanks. */
    unsigned deadline=index==2 ? 427 : 0;
    /* Landing alternates the entire scrolling background every VBlank.
     * Finish each frame on the hidden VDP2 page before exposing it. */
    static uint16_t displayed[2][384], desired[384];
    volatile uint16_t *pages[2]={screen,screen+0x20000};
    unsigned page=0;
    bool flip=index==4 || !track_timed;
    if (flip) {
        memset(displayed,0xff,sizeof(displayed));
        for (unsigned y=0;y<224;y++)
            memcpy((void *)(pages[1]+y*stride-32),(const void *)(pages[0]+y*stride-32),320*2);
    }
    for (unsigned i=0;i<section.count;i++) {
        const struct pose *pose=&sequence->poses[section.first+i];
        unsigned count=(sequence->tiles-sequence->updates)/sizeof(struct update);
        if (pose->first>count || pose->count>count-pose->first) return false;
        for (unsigned j=0;j<pose->count;j++) {
            struct update u=updates[pose->first+j];
            if (u.cell>=384 || u.tile>=(size-sequence->tiles)/64) return false;
            if (flip) desired[u.cell]=u.tile;
            else draw_tile(screen,stride,u.cell,u.tile);
        }
        if (flip) {
            page^=1;
            for (unsigned cell=0;cell<384;cell++) {
                if (displayed[page][cell]==desired[cell]) continue;
                draw_tile(pages[page],stride,cell,desired[cell]);
                displayed[page][cell]=desired[cell];
            }
            bitmap_page(page);
        }
        if (track_timed && (index==1 || index==2)) {
            deadline+=pose->frames;
            if (!disc_wait_track_frame(deadline)) return false;
        } else scene_wait(pose->frames);
    }
    if (flip && page) {
        for (unsigned cell=0;cell<384;cell++)
            if (displayed[0][cell]!=desired[cell]) draw_tile(screen,stride,cell,desired[cell]);
        bitmap_page(0);
        scene_wait(1);
    }
    return true;
}
