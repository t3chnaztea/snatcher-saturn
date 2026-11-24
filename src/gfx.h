#ifndef SNATCHER_GFX_H
#define SNATCHER_GFX_H
#include <stddef.h>
#include <stdint.h>

/* Decode a length-prefixed retail graphics block. Return consumed bytes,
 * including the length and terminator, or zero for an invalid block. */
size_t gfx_unpack(const uint8_t *src, size_t size, uint8_t *dst, size_t capacity);
#endif
