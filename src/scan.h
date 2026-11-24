#ifndef SNATCHER_SCAN_H
#define SNATCHER_SCAN_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
bool scan_open(unsigned command, uint8_t *buffer, size_t capacity, volatile uint16_t *screen, unsigned stride);
void scan_close(void);
bool scan_active(void);
bool scan_waiting(void);
void scan_tick(void);
void scan_redraw_portrait(void);
#endif
