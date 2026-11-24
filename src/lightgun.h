#ifndef SNATCHER_LIGHTGUN_H
#define SNATCHER_LIGHTGUN_H
#include <stdbool.h>
void lightgun_init(void);
void lightgun_begin(void);
void lightgun_end(void);
/* A completed trigger pull returns true. Field -1 means an off-screen miss. */
bool lightgun_shot(int *field);
#endif
