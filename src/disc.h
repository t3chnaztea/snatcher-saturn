#ifndef SNATCHER_DISC_H
#define SNATCHER_DISC_H
#include <stddef.h>
#include <stdbool.h>

bool disc_init(void);
bool disc_track_sector(unsigned *sector);
bool disc_wait_track_sector(unsigned sector);
bool disc_wait_track_frame(unsigned frame);
void disc_stop_track(void);
bool disc_play_track(unsigned track);
bool disc_read_sectors(const char *name, size_t sector, void *dest, size_t count);
size_t disc_read(const char *name, void *destination, size_t capacity);
#endif
