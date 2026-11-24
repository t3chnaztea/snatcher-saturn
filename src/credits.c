#include <yaul.h>
#include <string.h>
#include "disc.h"

extern uint32_t video_clock(void);
extern void game_display_init(void);

/* The verified pack leaves the upper 256 KiB of low RAM for the VDP state
 * and sprite layer. Voices have finished when SP38 transfers control here. */
#define PACK_LIMIT 0xC0000u
static const uint8_t *const pack = (void *)0x00200000;
struct credits_work {
    uint16_t vram[32768];
    uint8_t sprites[224][256], used[2048];
    bool redraw;
};
static struct credits_work *const work = (void *)(0x00200000 + PACK_LIMIT);
_Static_assert(sizeof(struct credits_work) <= 0x40000, "credits work RAM");

static void display_init(void)
{
    vdp2_scrn_display_set(0);
    vdp2_vram_cycp_t cycles;
    memset(&cycles, 0xff, sizeof(cycles));
    cycles.pt[0].t0 = cycles.pt[0].t1 = VDP2_VRAM_CYCP_PNDR_NBG1;
    cycles.pt[0].t2 = cycles.pt[0].t3 = VDP2_VRAM_CYCP_PNDR_NBG2;
    cycles.pt[0].t4 = VDP2_VRAM_CYCP_CHPNDR_NBG1;
    cycles.pt[0].t5 = VDP2_VRAM_CYCP_CHPNDR_NBG2;
    cycles.pt[2].t0 = cycles.pt[2].t1 = VDP2_VRAM_CYCP_CHPNDR_NBG0;
    vdp2_vram_cycp_set(&cycles);
    /* The source has two 32 x 64 maps. Center both in the 320-pixel
     * Saturn picture, with a transparent character in the outer columns. */
    /* Gameplay shares this bank. Start from blank patterns, including
     * character 2048 used for the side borders, before installing the maps. */
    memset((void *)VDP2_VRAM_ADDR(0,0), 0, 0x10000+32);
    volatile uint16_t *colors=(volatile uint16_t *)VDP2_CRAM_ADDR(0);
    for (unsigned i=0;i<64;i++) colors[i]=0x8000;
    for (unsigned i = 0; i < 2; ++i) {
        vdp2_scrn_t screen = i ? VDP2_SCRN_NBG2 : VDP2_SCRN_NBG1;
        vdp2_vram_t map_base = VDP2_VRAM_ADDR(0, i ? 0x18000 : 0x14000);
        vdp2_scrn_cell_format_t fmt = {
            .scroll_screen=screen, .ccc=VDP2_SCRN_CCC_PALETTE_16,
            .char_size=VDP2_SCRN_CHAR_SIZE_1X1, .pnd_size=2,
            .plane_size=VDP2_SCRN_PLANE_SIZE_1X1, .cpd_base=VDP2_VRAM_ADDR(0,0),
            .palette_base=VDP2_CRAM_ADDR(0)
        };
        vdp2_scrn_normal_map_t map = {
            .plane_a=map_base,.plane_b=map_base,.plane_c=map_base,.plane_d=map_base
        };
        vdp2_scrn_cell_format_set(&fmt, &map);
        vdp2_scrn_sf_set(screen, VDP2_SCRN_SF_MODE_1,
                         VDP2_SCRN_SF_TYPE_CELL_PRIORITY, VDP2_SCRN_SF_CODE_A);
        vdp2_scrn_priority_set(screen, 2);
        vdp2_scrn_scroll_x_set(screen, 0);
        vdp2_scrn_scroll_y_set(screen, 0);
        volatile uint32_t *map_words = (volatile uint32_t *)map_base;
        for (unsigned n = 0; n < 4096; ++n) map_words[n] = 2048;
    }
    const vdp2_scrn_bitmap_format_t sprites = {
        .scroll_screen=VDP2_SCRN_NBG0, .ccc=VDP2_SCRN_CCC_PALETTE_256,
        .bitmap_size=VDP2_SCRN_BITMAP_SIZE_512X256, .bitmap_base=VDP2_VRAM_ADDR(2,0),
        .palette_base=VDP2_CRAM_ADDR(0)
    };
    memset((void *)sprites.bitmap_base, 0, 512 * 224);
    vdp2_scrn_bitmap_format_set(&sprites);
    vdp2_scrn_priority_set(VDP2_SCRN_NBG0, 2);
    vdp2_scrn_scroll_x_set(VDP2_SCRN_NBG0, 0);
    vdp2_scrn_scroll_y_set(VDP2_SCRN_NBG0, 0);
}

static void set_tile(unsigned id, const uint16_t *pattern)
{
    memcpy(work->vram + id * 16, pattern, 32);
    memcpy((void *)VDP2_VRAM_ADDR(0,id * 32), pattern, 32);
    if (work->used[id] || id >= 0xfe00 / 32) work->redraw = true;
    unsigned base = id * 32;
    if (!((base >= 0xc000 && base < 0xd000) || (base >= 0xe000 && base < 0xf000))) return;
    volatile uint32_t *map = (volatile uint32_t *)VDP2_VRAM_ADDR(0,base >= 0xe000 ? 0x14000 : 0x18000);
    unsigned cell = (base & 0xfff) / 2;
    map += (cell / 32) * 64 + 4 + (cell % 32);
    for (unsigned i = 0; i < 16; ++i) {
        uint32_t entry = pattern[i];
        map[i] = ((entry & 0x8000) << 14) | ((entry & 0x1800) << 19) |
                 (((entry >> 13) & 3) << 16) | (entry & 2047);
    }
}

/* Bitmap special priority tests bit 3 of the palette index. Keep both
 * copies outside the 64 original colors used by the two cell planes. */
static unsigned sprite_color(unsigned index, bool high)
{
    return 128 + (index / 8) * 16 + (index % 8) + (high ? 8 : 0);
}

static void draw_sprites(bool per_dot_priority)
{
    const uint16_t *table = work->vram + 0xfe00 / 2;
    uint8_t order[80], seen[128] = {0};
    unsigned count = 0, link = 0;
    do {
        if (link >= 80 || seen[link]) break;
        seen[link] = 1;
        order[count++] = link;
        link = table[link * 4 + 1] & 127;
    } while (link);
    memset(work->used, 0, sizeof(work->used));
    memset(work->sprites, 0, sizeof(work->sprites));
    while (count) {
        const uint16_t *entry = table + order[--count] * 4;
        int x = (entry[3] & 511) - 128, y = (entry[0] & 511) - 128;
        unsigned attr = entry[2], h = 1 + ((entry[1] >> 8) & 3), w = 1 + ((entry[1] >> 10) & 3);
        if (x >= 256 || y >= 224 || x + (int)(8*w) <= 0 || y + (int)(8*h) <= 0) continue;
        for (unsigned row = 0; row < 8*h; ++row) {
            if ((unsigned)(y + row) >= 224) continue;
            unsigned sy = attr & 0x1000 ? 8*h-1-row : row;
            for (unsigned col = 0; col < 8*w; ++col) {
                if ((unsigned)(x + col) >= 256) continue;
                unsigned sx = attr & 0x800 ? 8*w-1-col : col;
                unsigned id = (attr + (sx/8)*h + sy/8) & 2047;
                work->used[id] = 1;
                unsigned bits = work->vram[id*16 + (sy%8)*2 + (sx%8)/4];
                unsigned color = (bits >> (12 - (sx%4)*4)) & 15;
                if (color) {
                    unsigned index = ((attr >> 9) & 48) + color;
                    work->sprites[y+row][x+col] = per_dot_priority ?
                        sprite_color(index, (attr & 0x8000) != 0) : index;
                }
            }
        }
    }
    uint8_t *output = (uint8_t *)VDP2_VRAM_ADDR(2,0) + 32;
    for (unsigned y = 0; y < 224; ++y)
        memcpy(output + y*512, work->sprites[y], 256);
    work->redraw = false;
}

bool credits_play(void)
{
    unsigned size = disc_read("CREDITS.BIN", (void *)pack, PACK_LIMIT);
    if (size < 16) return false;
    const uint32_t *header = (const uint32_t *)pack;
    unsigned patterns = header[0], offset = header[1], end = header[2];
    if (patterns > (size-12)/32 || offset != 12+32*patterns || offset > size-4 || end > 65534) return false;
    const uint16_t *next = (const uint16_t *)(pack + offset);
    const uint16_t *limit = (const uint16_t *)(pack + size);
    memset(work, 0, sizeof(*work));
    display_init();
    bool music = false, logo_music = false, ok = true;
    unsigned epoch = video_clock(), epoch_frame = 0, frame = 0;
    unsigned last_sector = 0, next_poll = epoch;
    bool pal = vdp2_tvmd_tv_standard_get() == VDP2_TVMD_TV_STANDARD_PAL;
    while (ok) {
        while (limit-next >= 2 && next[0] <= frame && next[0] != 65535) {
            unsigned updates = next[1];
            next += 2;
            if (updates > (unsigned)(limit-next)/2) { ok = false; break; }
            while (updates--) {
                unsigned key = *next++, value = *next++, index = key & 0x3fff;
                switch (key >> 14) {
                case 0:
                    if (index >= 2048 || value >= patterns) { ok = false; break; }
                    set_tile(index, (const uint16_t *)(pack + 12 + 32*value));
                    break;
                case 1:
                    if (index < 64) {
                        uint16_t r = (value & 7)*31/7, g = ((value>>3)&7)*31/7, b = ((value>>6)&7)*31/7;
                        ((volatile uint16_t *)VDP2_CRAM_ADDR(0))[index] = 0x8000 | r | (g<<5) | (b<<10);
                    }
                    break;
                case 2:
                    if (index < 2) {
                        vdp2_scrn_scroll_y_set(index ? VDP2_SCRN_NBG2 : VDP2_SCRN_NBG1,
                                               (int32_t)(value & 511) << 16);
                    }
                    break;
                case 3:
                    if (index == 1) vdp2_scrn_display_set(value & 64 ?
                        VDP2_SCRN_DISPTP_NBG0 | VDP2_SCRN_DISPTP_NBG1 | VDP2_SCRN_DISPTP_NBG2 : 0);
                    break;
                }
            }
        }
        if (work->redraw) draw_sprites(false);
        if (!music && frame >= 179) { ok = disc_play_track(19); music = true; }
        if (!logo_music && frame >= 25824) { ok = disc_play_track(2); logo_music = true; }
        vdp2_sync();
        vdp2_sync_wait();
        if (limit-next < 2) { ok = false; break; }
        if (next[0] == 65535 && frame >= end) {
            smpc_peripheral_digital_t pad;
            smpc_peripheral_process();
            smpc_peripheral_digital_port(1, &pad);
            if (pad.held.button.c || pad.held.button.start) break;
        }
        unsigned now = video_clock();
        unsigned ticks = now - epoch;
        /* Genesis Plus GX renders the US disc at 59.923 Hz. Anchor the
         * pictures to CD playback: the first audio sample follows 240
         * reference frames, including the retail drive startup delay. */
        unsigned candidate = epoch_frame + (pal ? ticks * 59923 / 50000 :
                                                  ticks * 59923 / 59827);
        if (music && !logo_music && now >= next_poll && frame < 25451) {
            unsigned sector;
            next_poll = now + 8;
            if (disc_track_sector(&sector) && sector > last_sector && sector <= 31547) {
                last_sector = sector;
                epoch_frame = 240 + (sector * 59923u + 37500u) / 75000u;
                epoch = now;
                candidate = epoch_frame;
            }
        }
        if (candidate > frame) frame = candidate;
    }
    /* Pattern RAM shares the gameplay bitmap. Clear the 32-pixel borders
     * before the title screen redraws the center of the display. */
    vdp2_scrn_display_set(0);
    vdp2_sync();
    vdp2_sync_wait();
    memset((void *)VDP2_VRAM_ADDR(0,0), 0, 512 * 224 * sizeof(uint16_t));
    game_display_init();
    vdp2_scrn_display_set(VDP2_SCRN_DISP_NBG0);
    return ok;
}

static unsigned prologue_length(const uint8_t **src, const uint8_t *end, unsigned n)
{
    if (n == 15) {
        unsigned v;
        do {
            if (*src == end)
                return 0x10000;
            v = *(*src)++;
            n += v;
        } while (v == 255 && n < 0x10000);
    }
    return n;
}

/* Each block carries its own LZ4 history. The file is local to the player's disc. */
static bool prologue_unpack(const uint8_t *src, unsigned size, uint8_t *dst, unsigned capacity)
{
    const uint8_t *end = src + size;
    unsigned out = 0;
    while (src < end) {
        unsigned token = *src++, literal = prologue_length(&src, end, token >> 4);
        if (literal > (unsigned)(end - src) || literal > capacity - out)
            return false;
        memcpy(dst + out, src, literal);
        out += literal;
        src += literal;
        if (src == end)
            break;
        if (end - src < 2)
            return false;
        unsigned distance = src[0] + 256u * src[1];
        src += 2;
        unsigned match = 4 + prologue_length(&src, end, token & 15);
        if (!distance || distance > out || match > capacity - out)
            return false;
        while (match--) {
            dst[out] = dst[out - distance];
            ++out;
        }
    }
    return out == capacity;
}

static void prologue_plane(unsigned page)
{
    vdp2_vram_t base = VDP2_VRAM_ADDR(0, page == 7 ? 0x14000 : 0x18000);
    vdp2_scrn_normal_map_t map = {
        .plane_a = base, .plane_b = base, .plane_c = base, .plane_d = base};
    vdp2_scrn_cell_format_t fmt = {.scroll_screen = VDP2_SCRN_NBG2,
                                   .ccc = VDP2_SCRN_CCC_PALETTE_16,
                                   .char_size = VDP2_SCRN_CHAR_SIZE_1X1,
                                   .pnd_size = 2,
                                   .plane_size = VDP2_SCRN_PLANE_SIZE_1X1,
                                   .cpd_base = VDP2_VRAM_ADDR(0, 0),
                                   .palette_base = VDP2_CRAM_ADDR(0)};
    vdp2_scrn_cell_format_set(&fmt, &map);
}

static int prologue_part(const char *name)
{
    size_t size = disc_read(name, (void *)pack, PACK_LIMIT);
    if (size < 12 || memcmp(pack, "PRO1", 4))
        return -1;
    const uint32_t *header = (const uint32_t *)pack;
    unsigned start = header[1], last = header[2];
    const uint8_t *block = pack + 12, *file_end = pack + size;
    uint8_t *scratch = (void *)0x002fa000;
    const uint16_t *cursor = (const uint16_t *)scratch, *end = cursor;
    unsigned due = start, frame = start, epoch = video_clock(), origin = start;
    unsigned stage = 0, anchor = 0, sector_seen = 0, poll = epoch, track_end = 0;
    bool pal = vdp2_tvmd_tv_standard_get() == VDP2_TVMD_TV_STANDARD_PAL;
    unsigned backdrop_index = 0;
    volatile uint16_t *const palette = (volatile uint16_t *)VDP2_CRAM_ADDR(0);
    while (frame <= last) {
        while (due <= frame) {
            if (cursor == end) {
                if (block == file_end)
                    break;
                if (file_end - block < 4)
                    return -1;
                unsigned packed_len = (block[0] << 8) | block[1],
                         length = (block[2] << 8) | block[3];
                block += 4;
                unsigned padded = (packed_len + 1) & ~1u;
                if (!packed_len || !length || (length & 1) || length > 16384 ||
                    (unsigned)(file_end - block) < padded ||
                    !prologue_unpack(block, packed_len, scratch, length))
                    return -1;
                block += padded;
                cursor = (uint16_t *)scratch;
                end = cursor + length / 2;
            }
            unsigned key = *cursor++;
            if (cursor == end)
                return -1;
            if (key == 0xffff) {
                due = start + *cursor++;
                continue;
            }
            unsigned index = key & 0x3fff;
            if ((key >> 14) == 0) {
                if (index >= 2048 || end - cursor < 16)
                    return -1;
                set_tile(index, cursor);
                cursor += 16;
                continue;
            }
            unsigned value = *cursor++;
            switch (key >> 14) {
            case 1:
                if (index >= 64)
                    return -1;
                palette[index] =
                    0x8000 | ((value & 7) * 31 / 7) | ((((value >> 3) & 7) * 31 / 7) << 5) |
                    ((((value >> 6) & 7) * 31 / 7) << 10);
                palette[sprite_color(index, false)] = palette[index];
                palette[sprite_color(index, true)] = palette[index];
                break;
            case 2:
                if (index < 2)
                    vdp2_scrn_scroll_y_set(index ? VDP2_SCRN_NBG2 : VDP2_SCRN_NBG1,
                                           (int32_t)(value & 511) << 16);
                break;
            case 3:
                if (index == 7) backdrop_index = value & 63;
                if (index == 4)
                    prologue_plane(value & 7);
                if (index == 1)
                    vdp2_scrn_display_set(value & 64
                                              ? VDP2_SCRN_DISPTP_NBG0 | VDP2_SCRN_DISPTP_NBG1 |
                                                    VDP2_SCRN_DISPTP_NBG2
                                              : 0);
                break;
            }
        }
        if (work->redraw)
            draw_sprites(true);
        MEMORY_WRITE(16, VDP2_VRAM_ADDR(3, 0x1fffe), palette[backdrop_index]);
        unsigned track = 0;
        if (start == 6170 && !stage && frame >= 6225) {
            track = 3;
            anchor = 6285;
            track_end = 14247;
        }
        if (start == 14250 && !stage && frame >= 14349) {
            track = 5;
            anchor = 14409;
            track_end = 15573;
        }
        if (start == 14250 && stage == 1 && frame >= 15560) {
            track = 4;
            anchor = 15575;
            track_end = 31784;
        }
        if (track) {
            ++stage;
            sector_seen = 0;
            if (!disc_play_track(track))
                track_end = 0;
        }
        vdp2_sync();
        vdp2_sync_wait();
        smpc_peripheral_digital_t pad;
        smpc_peripheral_process();
        smpc_peripheral_digital_port(1, &pad);
        if (pad.held.button.start)
            return 1;
        unsigned now = video_clock(),
                 candidate = origin + (now - epoch) * 59923 / (pal ? 50000 : 59827);
        if (track_end && frame < track_end - 30 && now >= poll) {
            unsigned sector;
            poll = now + 8;
            if (disc_track_sector(&sector) && sector > sector_seen && sector < 30000) {
                sector_seen = sector;
                epoch = now;
                origin = anchor + (sector * 59923u + 37500) / 75000;
                candidate = origin;
            }
        }
        if (candidate > frame)
            frame = candidate;
    }
    return 0;
}

bool prologue_play(void)
{
    memset(work, 0, sizeof(*work));
    display_init();
    vdp2_ioregs_t *regs = vdp2_regs_get();
    uint16_t saved_mode = regs->sfprmd, saved_code = regs->sfcode;
    uint16_t saved_select = regs->sfsel, saved_bitmap = regs->bmpna;
    vdp2_scrn_sf_set(VDP2_SCRN_NBG0, VDP2_SCRN_SF_MODE_2,
                     VDP2_SCRN_SF_TYPE_BITMAP_PRIORITY, VDP2_SCRN_SF_CODE_B);
    vdp2_scrn_sf_codes_set(VDP2_SCRN_SF_CODE_B, 0xf0);
    /* Reserve black side borders around the 256-pixel Sega CD picture. */
    ((volatile uint16_t *)VDP2_CRAM_ADDR(0))[64] = 0x8000;
    uint8_t *bitmap = (void *)VDP2_VRAM_ADDR(2, 0);
    for (unsigned y = 0; y < 224; ++y) {
        memset(bitmap + y * 512, 64, 32);
        memset(bitmap + y * 512 + 288, 64, 32);
    }
    int result = prologue_part("PRO0.BIN");
    if (!result)
        result = prologue_part("PRO1.BIN");
    regs->sfprmd = saved_mode;
    regs->sfcode = saved_code;
    regs->sfsel = saved_select;
    regs->bmpna = saved_bitmap;
    disc_stop_track();
    MEMORY_WRITE(16, VDP2_VRAM_ADDR(3, 0x1fffe), 0x8000);
    vdp2_scrn_display_set(0);
    vdp2_sync();
    vdp2_sync_wait();
    memset((void *)VDP2_VRAM_ADDR(0, 0), 0, 512 * 224 * sizeof(uint16_t));
    game_display_init();
    vdp2_scrn_display_set(VDP2_SCRN_DISP_NBG0);
    return result >= 0;
}
