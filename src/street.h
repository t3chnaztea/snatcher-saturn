#ifndef SNATCHER_STREET_H
#define SNATCHER_STREET_H
#include <stdbool.h>
#include <stdint.h>
bool street_open(volatile uint16_t *target,unsigned stride,const char *file,bool returning);
void street_tick(void);
void street_close(void);
void street_finish_pan(void);
#endif
