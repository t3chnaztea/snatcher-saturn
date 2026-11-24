#include <yaul.h>
#include "lightgun.h"

static void box(unsigned x, unsigned y, unsigned width, unsigned height, rgb1555_t color)
{
    volatile uint16_t *screen = (volatile uint16_t *)VDP2_VRAM_ADDR(0, 0);
    for (unsigned row = 0; row < height; row++)
        for (unsigned col = 0; col < width; col++)
            screen[(y + row) * 512 + x + col] = color.raw;
}

static void draw_grid(int field)
{
    for (int i = 0; i < 9; i++) {
        unsigned x = 64 + (i % 3) * 64, y = 8 + (i / 3) * 40;
        box(x + 1, y + 1, 62, 38, i == field ? RGB1555(1,0,24,7) : RGB1555(1,7,7,7));
        box(x + 30, y + 18, 4, 4, RGB1555(1,31,31,31));
    }
}

int main(void)
{
    const vdp2_scrn_bitmap_format_t fmt = {
        .scroll_screen = VDP2_SCRN_NBG0, .ccc = VDP2_SCRN_CCC_RGB_32768,
        .bitmap_size = VDP2_SCRN_BITMAP_SIZE_512X256, .bitmap_base = VDP2_VRAM_ADDR(0,0)
    };
    vdp2_scrn_bitmap_format_set(&fmt);
    vdp2_scrn_priority_set(VDP2_SCRN_NBG0, 6);
    vdp2_vram_cycp_t cycles = {0};
    for (unsigned i = 0; i < 4; i++) {
        cycles.pt[i].t0 = cycles.pt[i].t1 = cycles.pt[i].t2 = cycles.pt[i].t3 = VDP2_VRAM_CYCP_CHPNDR_NBG0;
        cycles.pt[i].t4 = cycles.pt[i].t5 = cycles.pt[i].t6 = cycles.pt[i].t7 = VDP2_VRAM_CYCP_NO_ACCESS;
    }
    vdp2_vram_cycp_set(&cycles);
    vdp2_tvmd_display_res_set(VDP2_TVMD_INTERLACE_NONE,VDP2_TVMD_HORZ_NORMAL_A,VDP2_TVMD_VERT_224);
    vdp2_scrn_back_color_set(VDP2_VRAM_ADDR(3,0x1fffe), RGB1555(1,0,0,0));
    box(0,0,320,224,RGB1555(1,0,0,0));
    draw_grid(-1);
    vdp2_scrn_display_set(VDP2_SCRN_DISP_NBG0);
    vdp2_tvmd_display_set();
    vdp2_sync();
    vdp2_sync_wait();
    lightgun_init();
    lightgun_begin();
    unsigned count = 0;
    for (;;) {
        int field;
        if (lightgun_shot(&field)) {
            draw_grid(field);
            box(64,144,192,8,RGB1555(1,0,0,0));
            box(64 + count % 10 * 18,144,14,8,
                field < 0 ? RGB1555(1,31,0,0) : RGB1555(1,0,24,7));
            count++;
        }
        vdp2_sync();
        vdp2_sync_wait();
    }
}
