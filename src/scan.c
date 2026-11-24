#include "scan.h"
#include "disc.h"
#include "drive.h"

/* The microscope and talking portrait share the display. The scanline
 * palette split from the Sega CD is baked into their separate tile colors. */
static const struct sequence *scan;
static volatile uint16_t *screen;
static unsigned pitch, pose, delay, elapsed, initial_scan;
static uint16_t portrait[128];
static unsigned portrait_cells;

static void draw(unsigned cell, unsigned tile)
{
    const uint8_t *pixels=(const uint8_t *)scan + scan->tiles + tile*64;
    unsigned x, y;
    if (cell<384) {
        x=32+cell%24*8;
        y=8+cell/24*8;
    } else {
        cell-=384;
        portrait[cell]=tile;
        x=(cell<64 ? 168 : 24)+cell%8*8;
        y=149+(cell%64)/8*8;
    }
    volatile uint16_t *dst=screen+y*pitch+x;
    for (unsigned row=0;row<8;row++,dst+=pitch)
        for (unsigned col=0;col<8;col++) dst[col]=scan->colors[*pixels++];
}

void scan_tick(void)
{
    if (!scan) return;
    ++elapsed;
    if (delay) { --delay; return; }
    if (pose>=scan->sections[0].count) return;
    const struct pose *p=&scan->poses[pose++];
    const struct update *u=(const struct update *)((const uint8_t *)scan+scan->updates)+p->first;
    for (unsigned i=0;i<p->count;i++) draw(u[i].cell,u[i].tile);
    delay=p->frames-1;
}

bool scan_open(unsigned command, uint8_t *buffer, size_t capacity, volatile uint16_t *target, unsigned stride)
{
    size_t bytes=disc_read(command==0x190b ? "HAIR.BIN" : command==0x190c ? "SKIN.BIN" : "ORGANIC.BIN",buffer,capacity);
    const struct sequence *s=(const struct sequence *)buffer;
    if (bytes<sizeof(*s) || s->updates<sizeof(*s) || s->tiles<s->updates || s->tiles>bytes ||
        !s->sections[0].count || s->sections[0].count>(s->updates-sizeof(*s))/sizeof(struct pose)) return false;
    portrait_cells = command==0x190d ? 128 : 64;
    unsigned count=(s->tiles-s->updates)/sizeof(struct update);
    const struct update *u=(const struct update *)(buffer+s->updates);
    for (unsigned i=0;i<count;i++)
        if (u[i].cell>=384+portrait_cells || u[i].tile>=(bytes-s->tiles)/64) return false;
    for (unsigned i=0;i<s->sections[0].count;i++) {
        const struct pose *p=&s->poses[i];
        if (!p->frames || p->first>count || p->count>count-p->first) return false;
    }
    extern bool fm_prepare_scan(void);
    if (!fm_prepare_scan()) return false;
    scan=s;
    screen=target;
    pitch=stride;
    for (unsigned y=142;y<224;y++)
        for (unsigned x=16;x<240;x++) screen[y*pitch+x]=0x8000;
    pose=delay=elapsed=0;
    /* The microscope controller signals before voice cue 151. */
    initial_scan=command==0x190b ? 319 : command==0x190c ? 385 : 533;
    scan_tick();
    return true;
}

void scan_close(void)
{
    extern void scene_wait(unsigned);
    /* Disc reads take different amounts of time on the two machines. Finish
     * the final analysis poses before replacing the monitor with Gibson. */
    while (scan && (pose<scan->sections[0].count || delay)) scene_wait(1);
    scan=NULL;
}
bool scan_active(void) { return scan!=NULL; }
bool scan_waiting(void) { return elapsed<initial_scan; }
void scan_redraw_portrait(void)
{
    if (!scan) return;
    for (unsigned i=0;i<portrait_cells;i++) draw(384+i,portrait[i]);
}
