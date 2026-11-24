#include "city.h"
#include "disc.h"
#include "drive.h"
#include <string.h>

/* Both shots must be resident before CD audio Track 6 starts. */
static uint8_t *const bank=(uint8_t *)0x00200000;
struct counts { uint32_t palettes,poses,updates,tiles; };
struct frame { uint32_t first; uint16_t count,delay,palette,portrait_palette; };
static const struct counts *clip;
static const uint16_t *colors;
static const struct frame *frames;
static const struct update *updates;
static const uint8_t *tiles;
static const uint32_t (*color_use)[2];
static volatile uint16_t *screen;
static unsigned pitch,position,delay,palette[2],bytes,shot,cells;
static uint16_t visible[512], displayed[2][512];
static unsigned page, page_palette[2][2];

static void paint(unsigned cell,unsigned dest_page)
{
    unsigned x=32+8*(cell%24), y=8+8*(cell/24);
    if (cell>=384) {
        unsigned i=cell-384;
        x=(i<64 ? 168 : 24)+8*(i%8);
        y=149+8*((i%64)/8);
    }
    const uint8_t *pixel=tiles+64*visible[cell];
    const uint16_t *row=colors+64*palette[cell>=384];
    volatile uint16_t *dst=screen+dest_page*0x20000+y*pitch+x;
    for (unsigned i=0;i<8;++i,dst+=pitch)
        for (unsigned j=0;j<8;++j) dst[j]=row[*pixel++];
}

static void paint_page(unsigned dest)
{
    uint32_t changed[2][2]={{0,0},{0,0}};
    for (unsigned bank_id=0;bank_id<2;++bank_id) {
        unsigned prior=page_palette[dest][bank_id];
        if (prior<clip->palettes && prior!=palette[bank_id]) {
            for (unsigned i=0;i<64;++i)
                if (colors[64*prior+i]!=colors[64*palette[bank_id]+i])
                    changed[bank_id][i/32]|=1u<<(i%32);
        }
        page_palette[dest][bank_id]=palette[bank_id];
    }
    for (unsigned i=0;i<cells;++i) {
        const uint32_t *mask=changed[i>=384];
        unsigned tile=visible[i];
        if (displayed[dest][i]!=tile || (color_use[tile][0]&mask[0]) || (color_use[tile][1]&mask[1])) {
            paint(i,dest);
            displayed[dest][i]=tile;
        }
    }
}

void city_tick(void)
{
    if (!clip) return;
    if (delay) { --delay; return; }
    if (position>=clip->poses) return;
    const struct frame *f=&frames[position++];
    palette[0]=f->palette;
    palette[1]=f->portrait_palette;
    for (unsigned i=0;i<f->count;++i) {
        const struct update *u=&updates[f->first+i];
        visible[u->cell]=u->tile;
    }
    page^=1;
    paint_page(page);
    bitmap_page(page);
    delay=f->delay-1;
}

bool city_open(unsigned section,volatile uint16_t *target,unsigned stride)
{
    if (section>3) return false;
    if (!section) bytes=disc_read("RETURN.BIN",bank,0x100000);
    if (bytes<16) return false;
    const uint32_t *offset=(const uint32_t *)bank;
    unsigned first=offset[section],end=section==3 ? bytes : offset[section+1];
    if (first<16 || first%4 || end>bytes || end<=first || end-first<sizeof(struct counts)) return false;
    const struct counts *c=(const struct counts *)(bank+first);
    if (!c->palettes || c->palettes>256 || !c->poses || c->poses>65535 || c->tiles>65535 ||
        c->updates>0x40000 || sizeof(*c)+128*c->palettes+sizeof(*frames)*c->poses+
        sizeof(*updates)*c->updates+72*c->tiles != end-first) return false;
    colors=(const uint16_t *)(c+1);
    frames=(const struct frame *)(colors+64*c->palettes);
    updates=(const struct update *)(frames+c->poses);
    color_use=(const uint32_t (*)[2])(updates+c->updates);
    tiles=(const uint8_t *)(color_use+c->tiles);
    for (unsigned i=0;i<c->poses;++i)
        if (!frames[i].delay || frames[i].palette>=c->palettes || frames[i].portrait_palette>=c->palettes || frames[i].first>c->updates ||
            frames[i].count>c->updates-frames[i].first) return false;
    cells=section>=2 ? 512 : 384;
    for (unsigned i=0;i<c->updates;++i)
        if (updates[i].tile>=c->tiles || updates[i].cell>=cells) return false;
    if (!section) {
        for (unsigned y=0;y<224;++y)
            for (unsigned x=0;x<256;++x) target[y*stride+x]=0x8000;
    }
    for (unsigned y=0;y<224;++y)
        memcpy((void *)(target+0x20000+y*stride-32),(const void *)(target+y*stride-32),320*2);
    memset(displayed,0xff,sizeof(displayed));
    page=0;
    memset(page_palette,0xff,sizeof(page_palette));
    shot=section;
    screen=target;
    pitch=stride;
    position=delay=0;
    palette[0]=palette[1]=256;
    memset(visible,0,sizeof(visible));
    clip=c;
    city_tick();
    return true;
}

bool city_wait(void)
{
    if (!clip) return false;
    extern void scene_wait(unsigned);
    while (position<clip->poses || delay) scene_wait(1);
    /* The city fades to black at retail frame 3948. Track 6 continues
     * through the blackout until the lobby shot at CD audio frame 813. */
    return shot!=0 || disc_wait_track_frame(813);
}

void city_close(void)
{
    if (clip && page) {
        paint_page(0);
        bitmap_page(0);
    }
    clip=NULL;
}

bool city_dialogue(void) { return clip && shot==3; }
