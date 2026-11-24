#include "gfx.h"

size_t gfx_unpack(const uint8_t *src, size_t size, uint8_t *dst, size_t capacity)
{
    if (size < 2) return 0;
    size_t length = ((size_t)src[0] << 8) | src[1];
    if (length > capacity) return 0;

    size_t in = 2, out = 0;
    while (in < size) {
        unsigned flags = src[in++];
        for (unsigned bit = 0; bit < 8; bit++, flags >>= 1) {
            if (in == size) return 0;
            unsigned token = src[in++];
            if (!(flags & 1)) {
                if (out == length) return 0;
                dst[out++] = (uint8_t)token;
            } else if (token == 0x1f) {
                return out == length ? in : 0;
            } else if (token >= 0xc0) {
                size_t count = token - 184;
                if (count > size - in || count > length - out) return 0;
                while (count--) dst[out++] = src[in++];
            } else {
                size_t distance, count;
                if (token >= 0x80) {
                    distance = token & 15;
                    count = (token >> 4) - 6;
                } else {
                    if (in == size) return 0;
                    distance = ((token & 0xe0) << 3) | src[in++];
                    count = (token & 31) + 3;
                }
                if (!distance || distance > out || count > length - out) return 0;
                while (count--) {
                    dst[out] = dst[out - distance];
                    out++;
                }
            }
        }
    }
    return 0;
}
