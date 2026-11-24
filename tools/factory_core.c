/* Compare the scene and the dialogue separately so scrolling weather cannot
 * conceal an incorrect menu. Frame numbers use the runner's one-based captures. */
#include <libretro.h>
#include <stdint.h>
static void factory_video(const void *,unsigned,unsigned,size_t);
#define p_retro_set_video_refresh(callback) p_retro_set_video_refresh(factory_video)
#include "backup_core.c"
static void factory_video(const void *data,unsigned w,unsigned h,size_t pitch)
{
    video(data,w,h,pitch);
    if (!rgb || (width!=256 && width!=330) || height!=224) return;
    static FILE *trace;
    static uint8_t colors[256];
    if (!trace) {
        trace=fopen(getenv("SNATCHER_FRAME_HASHES"),"w");
        if (!trace) fail("Could not open frame hashes");
        for (unsigned n=0;n<256;n++) colors[n]=(((n+17)/34)*255/7*31/255)<<3;
    }
    uint64_t hashes[2];
    for (unsigned part=0;part<2;part++) {
        uint64_t value=14695981039346656037ULL;
        unsigned top=part?142:8, bottom=part?224:136;
        unsigned left=part?16:32, right=part?232:224;
        for (unsigned y=top;y<bottom;y++) {
            unsigned offset=(y*width+left+(width==330?37:0))*3;
            for (unsigned i=0;i<(right-left)*3;i++) {
                unsigned color=rgb[offset+i];
                value=(value^(width==330?color:colors[color]))*1099511628211ULL;
            }
        }
        hashes[part]=value;
    }
    fprintf(trace,"%u %016llx %016llx\n",frame+1,(unsigned long long)hashes[0],(unsigned long long)hashes[1]);
}
