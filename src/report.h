#ifndef SNATCHER_REPORT_H
#define SNATCHER_REPORT_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
bool report_open(uint8_t *buffer,size_t size,volatile uint16_t *screen,unsigned stride);
void report_close(void);
bool report_start(unsigned actor);
bool report_wait(unsigned actor);
void report_tick(void);
#endif
