#ifndef SNATCHER_PLAZA_H
#define SNATCHER_PLAZA_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
bool plaza_open(unsigned scene,void *scratch,size_t capacity,volatile uint16_t *screen,unsigned stride);
bool act3_room_clip(unsigned key,bool clear,void *scratch,size_t capacity,volatile uint16_t *target,unsigned stride);
bool plaza_load(const char *file,bool clear,void *scratch,size_t capacity,volatile uint16_t *screen,unsigned stride);
bool plaza_ending(unsigned section,volatile uint16_t *target,unsigned stride);
bool plaza_briefing_load(unsigned track);
void plaza_briefing_start(volatile uint16_t *screen,unsigned stride);
bool plaza_played(void);
void plaza_close(void);
void plaza_tick(void);
void plaza_use_video_clock(void);
bool plaza_hospital_door(volatile uint16_t *target,unsigned stride);
bool plaza_mika_call(void *scratch,size_t capacity,volatile uint16_t *target,unsigned stride);
void plaza_mika_voice(unsigned id);
bool plaza_apartment_film(bool shower,volatile uint16_t *target,unsigned stride);
void plaza_apartment_voice(unsigned id);
void plaza_apartment_stop(void);
bool plaza_local_clip(const char *file,void *scratch,size_t capacity,volatile uint16_t *target,unsigned stride);
void plaza_wait_frames(unsigned);
#endif
