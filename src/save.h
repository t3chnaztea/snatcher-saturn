#ifndef SNATCHER_SAVE_H
#define SNATCHER_SAVE_H
#include "script.h"

void saves_init(void);
bool save_exists(unsigned slot);
bool save_load(unsigned slot, struct investigation *s);
unsigned save_write(unsigned slot, const struct investigation *s);
bool script_resume(struct investigation *s);
#endif
