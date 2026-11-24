#ifndef SNATCHER_FLASHLIGHT_H
#define SNATCHER_FLASHLIGHT_H
#include <stdbool.h>
#include <stddef.h>

bool flashlight_set(bool on, void *scratch, size_t capacity);
bool flashlight_aim(bool aiming, int horizontal, int vertical);
unsigned flashlight_target(void);
void flashlight_tick(void);
void flashlight_close(void);
#endif
