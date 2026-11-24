/* Render the player's DATA_A0 with its original graphics interpreter.
 * Export tile references and the tile dictionary for the native SH-2 player. */
#include <libretro.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static void plaza_video(const void *,unsigned,unsigned,size_t);
#define p_retro_set_video_refresh(cb) p_retro_set_video_refresh(plaza_video)
#include "runner.c"

#ifndef RECORD_TRANSPORT
#define RECORD_TRANSPORT(frame) ((void)0)
#endif
static uint16_t dictionary[65535][64], buckets[131072];
static unsigned used;
static void plaza_video(const void *data,unsigned w,unsigned h,size_t pitch)
{
    video(data,w,h,pitch);
    if (!rgb || w!=256 || h!=224) return;
    static FILE *frames,*tiles;
    const char *first=getenv("SNATCHER_SCENE_FIRST");
    if (first && frame+1<(unsigned)strtoul(first,NULL,10)) return;
    RECORD_TRANSPORT(frame+1);
    static uint16_t levels[256];
    if (!frames) {
        /* Two constant background pixels identify the first fully lit plaza.
         * The build checks the entire first viewport before accepting output. */
        if (!first && (memcmp(rgb+3*(40*256+53),(uint8_t[]){98,206,0},3) ||
            memcmp(rgb+3*(28*256+200),(uint8_t[]){0,32,65},3))) return;
        frames=fopen("frames.raw","wb");
        tiles=fopen("tiles.raw","wb");
        if (!frames || !tiles) fail("Cannot create plaza graphics files");
        for (unsigned c=0;c<256;c++) levels[c]=((c+17)/34)*255/7*31/255;
        fprintf(stderr,"First plaza frame %u\n",frame+1);
    }
    /* SP16 draws the three speaking portraits below the investigation view. */
    bool full=getenv("SNATCHER_FULL_SCREEN")!=NULL;
    unsigned cells=full ? 32*28 : getenv("SNATCHER_SCENE_PORTRAITS") ? 384+28*11 : 384;
    uint16_t map[32*28];
    for (unsigned cell=0;cell<cells;cell++) {
        uint16_t tile[64];
        uint32_t hash=2166136261u;
        unsigned x=32+8*(cell%24), y=8+8*(cell/24);
        if (full) { x=8*(cell%32); y=8*(cell/32); }
        else if (cell>=384) {
            x=16+8*((cell-384)%28);
            y=136+8*((cell-384)/28);
        }
        for (unsigned row=0;row<8;row++)
            for (unsigned col=0;col<8;col++) {
                const uint8_t *pixel=rgb+3*((y+row)*256+x+col);
                uint16_t color=0x8000|levels[pixel[0]]|(levels[pixel[1]]<<5)|(levels[pixel[2]]<<10);
                tile[8*row+col]=color;
                hash=(hash^color)*16777619u;
            }
        unsigned slot=(hash^(hash>>16))&131071;
        while (buckets[slot] && memcmp(dictionary[buckets[slot]-1],tile,sizeof(tile)))
            slot=(slot+1)&131071;
        if (!buckets[slot]) {
            if (used>=65535) fail("Plaza tile dictionary overflow");
            memcpy(dictionary[used],tile,sizeof(tile));
            buckets[slot]=++used;
            uint8_t bytes[128];
            for (unsigned i=0;i<64;i++) {bytes[2*i]=tile[i]>>8;bytes[2*i+1]=tile[i];}
            if (fwrite(bytes,1,128,tiles)!=128) fail("Cannot write plaza tiles");
        }
        map[cell]=buckets[slot]-1;
    }
    uint8_t bytes[2*32*28];
    for (unsigned i=0;i<cells;i++) {bytes[2*i]=map[i]>>8;bytes[2*i+1]=map[i];}
    if (fwrite(bytes,2,cells,frames)!=cells) fail("Cannot write plaza frame");
}
