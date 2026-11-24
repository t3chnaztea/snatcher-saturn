#ifndef SNATCHER_CITY_H
#define SNATCHER_CITY_H
#include <stdbool.h>
#include <stdint.h>
bool city_open(unsigned section,volatile uint16_t *target,unsigned stride);
void city_tick(void);
void city_close(void);
bool city_wait(void);
bool city_dialogue(void);
#endif
