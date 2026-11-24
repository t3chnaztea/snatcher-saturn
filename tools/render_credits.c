/* Capture the display updates issued by the US staff-roll program. The
 * renderer runs from cold boot with the same retail choices as the ending. */
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const uint8_t *display_memory[4];
static const unsigned lengths[] = {65536, 128, 128, 32};
static const unsigned widths[] = {32, 2, 2, 1};
static uint8_t previous[65536 + 128 + 128 + 32];

static void *open_credits_core(const char *path, int flags)
{
    void *core = dlopen(path, flags);
    const char *const names[] = {"vram", "cram", "vsram", "reg"};
    if (!core) return NULL;
    for (unsigned i = 0; i < 4; ++i) {
        display_memory[i] = dlsym(core, names[i]);
        if (!display_memory[i]) {
            fprintf(stderr, "Missing Genesis Plus GX display memory %s\n", names[i]);
            exit(1);
        }
    }
    return core;
}

static void capture_changes(unsigned frame)
{
    static FILE *output;
    static unsigned first;
    if (!first) {
        const char *option = getenv("SNATCHER_DISPLAY_FIRST");
        first = option ? (unsigned)strtoul(option, NULL, 10) : 331080;
    }
    if (frame < first) return;
    if (!output) {
        output = fopen("changes.bin", "wb");
        if (!output) { perror("changes.bin"); exit(1); }
    }
    unsigned base = 0;
    for (unsigned area = 0; area < 4; ++area) {
        unsigned width = widths[area];
        for (unsigned offset = 0; offset < lengths[area]; offset += width) {
            const uint8_t *bytes = display_memory[area] + offset;
            uint8_t *saved = previous + base + offset;
            if (frame != first && !memcmp(saved, bytes, width)) continue;
            uint16_t header[] = {frame >> 16, frame & 65535, area, offset};
            if (fwrite(header, sizeof(header), 1, output) != 1 ||
                fwrite(bytes, width, 1, output) != 1) {
                perror("credits trace"); exit(1);
            }
            memcpy(saved, bytes, width);
        }
        base += lengths[area];
    }
    if (frame == 360500 && fclose(output)) { perror("credits trace"); exit(1); }
}

#define dlopen open_credits_core
static void capture_opening_text(unsigned number);
#define p_retro_run() (p_retro_run(), capture_changes(frame + 1), capture_opening_text(frame + 1))
#include "runner.c"

/* The dedication changes display enable during a scanline interrupt. End-of-frame
 * register snapshots lose that effect. Capture changed rows of the final picture. */
static void capture_opening_text(unsigned number)
{
    if (number < 7520 || number > 8060 || !getenv("SNATCHER_DISPLAY_FIRST")) return;
    if (!rgb || width != 256 || height != 224) fail("Unexpected dedication display mode");
    static FILE *rows;
    static uint16_t previous_rows[224][256];
    if (!rows) {
        rows = fopen("dedication.rows", "wb");
        if (!rows) fail("Cannot create dedication capture");
    }
    for (unsigned y = 0; y < 224; ++y) {
        uint16_t pixels[256];
        for (unsigned x = 0; x < 256; ++x) {
            const uint8_t *pixel = rgb + 3 * (y * 256 + x);
            pixels[x] = (pixel[0]+17)/34 | ((pixel[1]+17)/34)<<3 | ((pixel[2]+17)/34)<<6;
        }
        if (number != 7520 && !memcmp(previous_rows[y], pixels, sizeof(pixels))) continue;
        uint16_t header[] = {number, y};
        if (fwrite(header, sizeof(header), 1, rows) != 1 ||
            fwrite(pixels, sizeof(pixels), 1, rows) != 1) fail("Cannot write dedication rows");
        memcpy(previous_rows[y], pixels, sizeof(pixels));
    }
    if (number == 8060 && fclose(rows)) fail("Cannot close dedication capture");
}
