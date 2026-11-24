#include "lightgun.h"
#include <yaul.h>

/* Port one remains under INTBACK for investigation menus and pad aiming.
 * In direct mode port two supplies the Stunner trigger and TH light pulse. */
static volatile bool active;
static volatile struct { uint16_t port, valid, h, v; } sample;
static bool trigger_down;
static unsigned flash_frames;
static uint16_t original_exten,offset_enable,offset_select,red,green,blue;

static void capture(void *unused)
{
    (void)unused;
    if (!active) return;
    sample.port=MEMORY_READ(8,SMPC(PDR2));
    sample.valid=MEMORY_READ(16,VDP2(TVSTAT)) & 0x0200;
    sample.h=MEMORY_READ(16,VDP2(HCNT));
    sample.v=MEMORY_READ(16,VDP2(VCNT));
}

void lightgun_init(void)
{
    vdp_sync_vblank_in_set(capture,NULL);
}

void lightgun_begin(void)
{
    vdp2_ioregs_t *regs=vdp2_regs_get();
    original_exten=regs->exten;
    offset_enable=regs->clofen;
    offset_select=regs->clofsl;
    red=regs->coar; green=regs->coag; blue=regs->coab;
    flash_frames=0;
    trigger_down=false;
    sample.port=0xff;
    sample.valid=0;
    regs->exten |= 0x0200;
    MEMORY_WRITE(8,SMPC(DDR2),0);
    MEMORY_WRITE(8,SMPC(IOSEL2),2);
    MEMORY_WRITE(8,SMPC(EXLE2),2);
    active=true;
}

static void flash_end(void)
{
    vdp2_ioregs_t *regs=vdp2_regs_get();
    regs->clofen=offset_enable;
    regs->clofsl=offset_select;
    regs->coar=red; regs->coag=green; regs->coab=blue;
}

void lightgun_end(void)
{
    active=false;
    flash_end();
    vdp2_regs_get()->exten=original_exten;
    MEMORY_WRITE(8,SMPC(EXLE2),0);
    MEMORY_WRITE(8,SMPC(IOSEL2),0);
}

bool lightgun_shot(int *field)
{
    unsigned port=sample.port;
    bool pressed=(port & 0x1f)==0x0c;
    bool edge=pressed && !trigger_down;
    trigger_down=pressed;
    if (flash_frames) {
        if (--flash_frames) return false;
        flash_end();
        /* At 320 dots the horizontal latch counts half dots. The 192-dot
         * combat window starts at counter 188. Its three rows span 40 lines. */
        int x=(int)sample.h-188, y=(int)sample.v-8;
        *field=sample.valid && x>=0 && x<384 && y>=0 && y<120 ? 3*(y/40)+x/128 : -1;
        return true;
    }
    if (edge) {
        vdp2_ioregs_t *regs=vdp2_regs_get();
        regs->coar=regs->coag=regs->coab=255;
        regs->clofsl &= ~1u;
        regs->clofen |= 1;
        flash_frames=2;
    }
    return false;
}
