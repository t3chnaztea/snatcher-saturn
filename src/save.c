#include "save.h"
#include <yaul.h>
#include <bup.h>
#include <stddef.h>
#include <string.h>

/* The BIOS expects a four-byte device descriptor and 2048+30 work words.
 * These sizes follow Sonic CD Saturn's tested internal-memory backend. */
struct bios_unit { uint16_t unit, partitions; };
static struct { uint32_t library[4096], work[2078]; } bios;
extern bup_stub_t *__bup_stub;
extern void save_input_gate(bool);
static bool connected;

struct record {
    uint32_t magic, generation, random;
    uint16_t version, module, root, scene, previous_count, previous_roots[3];
    uint8_t flags[354];
    struct practice_score practice;
    uint32_t checksum;
};
_Static_assert(sizeof(struct record)==400,"version 1 on-disc layout");
_Static_assert(sizeof(bup_directory_t)==36,"BIOS directory stride");

static uint32_t checksum(const struct record *r)
{
    const uint8_t *bytes=(const uint8_t *)r;
    uint32_t value=2166136261u;
    for (size_t i=0;i<offsetof(struct record,checksum);i++) value=(value^bytes[i])*16777619u;
    return value;
}

void saves_init(void)
{
    struct bios_unit config[3]={{0}};
    typedef void (*bios_init)(void *,void *,struct bios_unit *);
    save_input_gate(false);
    smpc_smc_resdisa_call();
    ((bios_init)MEMORY_READ(32,0x06000358))(bios.library,bios.work,config);
    __bup_stub=(bup_stub_t *)MEMORY_READ(32,0x06000354);
    smpc_smc_resenab_call();
    connected=config[0].unit==1 && config[0].partitions && !bup_partition_select(BUP_DEVICE_INTERNAL,0);
    save_input_gate(true);
}

static void filename(char name[12], unsigned slot, unsigned bank)
{
    memcpy(name,"SNATCHERS1A",12);
    name[9]='1'+slot-1;
    name[10]='A'+bank;
}

static bool read_record(unsigned slot,unsigned bank,struct record *r)
{
    char name[12];
    filename(name,slot,bank);
    bup_directory_t dir={0};
    /* The BIOS directory and read calls issue SMPC commands. An INTBACK
     * interrupt here can wait forever on the interrupted command. */
    save_input_gate(false);
    bool found=bup_dir(BUP_DEVICE_INTERNAL,name,1,&dir)==1 && !memcmp(dir.filename,name,12) &&
               dir.data_size==sizeof(*r) && bup_read(BUP_DEVICE_INTERNAL,name,r)==0;
    save_input_gate(true);
    if (!found) return false;
    return r->magic==0x534e4348 && r->version==1 && r->previous_count<=3 &&
           r->module<=38 && r->root<0x3800 && r->checksum==checksum(r);
}

/* Keep the preceding verified generation until the new BIOS write is complete. */
static int newest(unsigned slot,struct record *result)
{
    if (!connected || slot<1 || slot>4) return -1;
    struct record other;
    bool a=read_record(slot,0,result), b=read_record(slot,1,&other);
    if (b && (!a || (int32_t)(other.generation-result->generation)>0)) {
        *result=other;
        return 1;
    }
    return a ? 0 : -1;
}

/* Keep BIOS read buffers out of every recursive script-evaluation frame under LTO. */
__attribute__((noinline)) bool save_exists(unsigned slot)
{
    struct record r;
    return newest(slot,&r)>=0;
}

bool save_load(unsigned slot,struct investigation *s)
{
    struct record r;
    if (newest(slot,&r)<0) return false;
    *s=(struct investigation){.module=r.module,.root=r.root,.scene=r.scene,
                             .random=r.random,.previous_count=r.previous_count,.practice=r.practice};
    memcpy(s->flags,r.flags,sizeof(r.flags));
    memcpy(s->previous_roots,r.previous_roots,sizeof(r.previous_roots));
    return script_resume(s);
}

unsigned save_write(unsigned slot,const struct investigation *s)
{
    if (!connected || slot<1 || slot>4) return BUP_BROKEN;
    struct record old;
    int bank=newest(slot,&old);
    struct record r={.magic=0x534e4348,.version=1,.generation=bank<0?1:old.generation+1,
        .random=s->random,.module=s->module,.root=s->root,.scene=s->scene,
        .previous_count=s->previous_count,.practice=s->practice};
    memcpy(r.flags,s->flags,sizeof(r.flags));
    memcpy(r.previous_roots,s->previous_roots,sizeof(r.previous_roots));
    r.checksum=checksum(&r);
    bup_directory_t dir={0};
    filename(dir.filename,slot,bank==0);
    memcpy(dir.comment,"SNATCHER",9);
    dir.language=BUP_LANG_ENGLISH;
    dir.data_size=sizeof(r);
    smpc_time_dec_t rtc;
    smpc_rtc_time_bcd_from(smpc_rtc_time_get(),&rtc);
    bup_date_t date={.year=rtc.year>=1980 && rtc.year<=2235?rtc.year-1980:0,
        .month=rtc.month>=1 && rtc.month<=12?rtc.month:1,.day=rtc.day>=1 && rtc.day<=31?rtc.day:1,
        .hour=rtc.hours<24?rtc.hours:0,.minute=rtc.minutes<60?rtc.minutes:0};
    save_input_gate(false);
    dir.date=bup_date_set(&date);
    smpc_smc_resdisa_call();
    int rc=bup_write(BUP_DEVICE_INTERNAL,&dir,&r,BUP_WRITE_MODE_OVERWRITE);
    if (!rc) rc=bup_verify(BUP_DEVICE_INTERNAL,dir.filename,&r);
    smpc_smc_resenab_call();
    save_input_gate(true);
    return rc;
}
