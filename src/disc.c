#include "disc.h"
#include "track_lengths.h"
#include <yaul.h>
#include <string.h>

struct disc_entry {
    char name[13];  /* ISO level 1: eight characters, a dot, three characters. */
    uint32_t starting_fad, size;
};
static struct disc_entry entries[DISC_ROOT_CAPACITY];
static unsigned entry_count;
static uint32_t sector_words[512];

/* Track numbers are one-based. The lead-out supplies the last end FAD. */
static uint32_t track_starts[22];
static unsigned audio_tracks, playing_start, playing_end;

static void read_audio_toc(void)
{
    uint16_t words=0;
    if (cd_block_cmd_toc_get(NULL,&words)) return;
    uint32_t entry=0;
    for (unsigned i=0;i<words;i++) {
        entry=(entry<<16)|MEMORY_READ(16,CD_BLOCK(0));
        if (!(i&1)) continue;
        unsigned index=i/2;
        if (index<21) track_starts[index]=entry;
        if (index==100) audio_tracks=(entry>>16)&255;
        if (index==101) track_starts[21]=entry;
    }
    if (cd_block_cmd_data_transfer_end() || words!=204 || audio_tracks!=21) audio_tracks=0;
}

void disc_stop_track(void)
{
    if (playing_start) cd_block_cmd_disk_seek(0xffffff);
    playing_start = playing_end = 0;
}

bool disc_play_track(unsigned track)
{
    if (track<2 || track>audio_tracks) return false;
    uint32_t entry=track_starts[track-1];
    uint32_t start=entry&0xffffff, end=track_starts[track]&0xffffff;
    if ((entry&0x40000000) || start<150 || end<=start) return false;
    unsigned sectors=track_sectors[track-2];
    if (sectors>end-start || cd_block_cmd_disk_play(0,start,sectors)) return false;
    playing_start=start;
    playing_end=start+sectors;
    return true;
}

bool disc_wait_track_frame(unsigned frame)
{
    return disc_wait_track_sector((frame*75+59)/60);
}

bool disc_track_sector(unsigned *sector)
{
    cd_block_status_t state;
    if (!playing_start || cd_block_cmd_status_get(&state)) return false;
    unsigned status=state.cd_status&15;
    if ((status!=CD_STATUS_PLAY && status!=CD_STATUS_PAUSE) || state.fad<playing_start || state.fad>playing_end)
        return false;
    *sector=state.fad-playing_start;
    return true;
}

bool disc_wait_track_sector(unsigned sector)
{
    extern void scene_wait(unsigned);
    if (!playing_start) return false;
    uint32_t target=playing_start+sector;
    if (target>playing_end) target=playing_end;
    unsigned last=0,stalled=0;
    while (stalled<600) {
        cd_block_status_t state;
        if (cd_block_cmd_status_get(&state)) return false;
        unsigned status=state.cd_status&15;
        if (status==CD_STATUS_PLAY && state.fad>=playing_start && state.fad>=target) return true;
        if (status==CD_STATUS_PAUSE && state.fad>=playing_end-1) return true;
        if (status==CD_STATUS_OPEN || status==CD_STATUS_NO_DISC || status>=CD_STATUS_ERROR) return false;
        if (state.fad!=last) stalled=0;
        last=state.fad;
        ++stalled;
        scene_wait(1);
    }
    return false;
}

static uint32_t iso_u32(const uint8_t *le)
{
    return le[0] | (uint32_t)le[1]<<8 | (uint32_t)le[2]<<16 | (uint32_t)le[3]<<24;
}

/* The port has one flat ISO directory. A record can end exactly at byte
 * 2048. Read it before advancing to the following sector. */
static bool read_root(void)
{
    uint8_t *block=(uint8_t *)sector_words;
    if (cd_block_sectors_read(150+16,block,2048) || block[0]!=1 || memcmp(block+1,"CD001",5))
        return false;
    uint32_t lba=iso_u32(block+158), remaining=iso_u32(block+166);
    entry_count=0;
    while (remaining) {
        if (cd_block_sectors_read(150+lba++,block,2048)) return false;
        unsigned limit=remaining<2048 ? remaining : 2048;
        for (unsigned pos=0;pos<limit && block[pos];pos+=block[pos]) {
            uint8_t *record=block+pos;
            unsigned length=record[0];
            if (length<34 || length>limit-pos || record[32]>length-33) return false;
            if (record[25]&2) continue;
            unsigned chars=record[32];
            if (chars>=2 && record[33+chars-2]==';' && record[33+chars-1]=='1') chars-=2;
            if (!chars || chars>=sizeof(entries[0].name) || entry_count>=sizeof(entries)/sizeof(entries[0]))
                return false;
            struct disc_entry *e=&entries[entry_count++];
            memcpy(e->name,record+33,chars);
            e->name[chars]=0;
            e->starting_fad=150+iso_u32(record+2);
            e->size=iso_u32(record+10);
        }
        remaining-=limit;
    }
    return entry_count!=0;
}

bool disc_init(void)
{
    if (cd_block_init() != 0) return false;
    read_audio_toc();
    return read_root();
}

static const struct disc_entry *lookup(const char *name)
{
    for (unsigned i = 0; i < entry_count; i++)
        if (!strcmp(entries[i].name, name)) return &entries[i];
    return NULL;
}

bool disc_read_sectors(const char *name, size_t sector, void *dest, size_t count)
{
    const struct disc_entry *file = lookup(name);
    if (!file || !count) return false;
    size_t total = (file->size + 2047u) / 2048u;
    if (sector >= total || count > total - sector) return false;
    return cd_block_sectors_read(file->starting_fad + sector, dest, count * 2048u) == 0;
}

size_t disc_read(const char *name, void *destination, size_t capacity)
{
    const struct disc_entry *file = lookup(name);
    if (!file || !file->size) return 0;
    size_t count = (file->size + 2047u) / 2048u;
    return count <= capacity/2048 && disc_read_sectors(name, 0, destination, count)
        ? file->size : 0;
}
