#ifndef SNATCHER_CRASH_H
#define SNATCHER_CRASH_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

void crash_decode(const uint8_t *vram,uint8_t *atlas,unsigned offset);
void crash_background(const uint8_t *state,const uint8_t *atlas,uint8_t *pixels);
void crash_sprites(const uint8_t *state,const uint8_t *atlas,uint8_t *pixels);
bool crash_play(void *scratch,size_t capacity,volatile uint16_t *screen,unsigned pitch);
#endif
