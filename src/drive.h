#ifndef SNATCHER_DRIVE_H
#define SNATCHER_DRIVE_H
#include <stdbool.h>
#include <stdint.h>
struct section { uint16_t first, count; };
struct pose { uint32_t first; uint16_t count, frames; };
struct update { uint16_t cell, tile; };
struct sequence {
    uint32_t updates, tiles;
    struct section sections[5];
    uint16_t colors[256];
    struct pose poses[];
};
_Static_assert(sizeof(struct sequence)==540,"drive file header");
void bitmap_page(unsigned page);
bool drive_load(bool transit);
bool drive_section(unsigned section, volatile uint16_t *screen, unsigned stride);
#endif
