#include "report.h"
#include "plaza.h"
#include "flashlight.h"
extern bool queens_light(bool);
extern bool chief_picture(bool);
extern bool ceiling_pan(void);
extern bool hospital_road_clip(const char *);
extern bool church_transition(bool);
extern bool hospital_stair_actor(unsigned);
extern bool cockpit_clip(const char *);
extern bool napoleon_pose(void);
#include "script.h"
#include "disc.h"
#include "save.h"
#include <string.h>
#include <stddef.h>

struct node { uint8_t code, modes; uint16_t a, b, c; };
/* One compiled script and its text pool reside in work RAM at a time. */
static union {
    uint32_t words[0x28000 / 4];
    struct { uint32_t code_bytes, text_bytes; struct node nodes[0x3800]; } story;
} module;
static const struct node *script_nodes = module.story.nodes;
static unsigned node_count;
const uint8_t *script_text;

static bool load_script(unsigned number)
{
    if (number > 38) return false;
    char filename[] = "SP00.BIN";
    filename[2] += number / 10;
    filename[3] += number % 10;
    size_t size = disc_read(filename, &module, sizeof(module));
    if (size < 8 || module.story.code_bytes > size - 8 ||
        module.story.code_bytes % sizeof(struct node) ||
        module.story.text_bytes != size - 8 - module.story.code_bytes) return false;
    node_count = module.story.code_bytes / sizeof(struct node);
    if (node_count > 0x3800) return false;
    script_text = (const uint8_t *)&module + 8 + module.story.code_bytes;
    return true;
}
#define NONE UINT16_MAX

static uint16_t flags(struct investigation *s, unsigned selector, bool write, unsigned value)
{
    unsigned start = selector >> 4, width = (selector & 15) + 1;
    if (start + width > 352 * 8) return 0;
    unsigned result = 0;
    for (unsigned i = 0; i < width; i++) {
        unsigned bit = start + i, mask = 128u >> (bit & 7);
        uint8_t *byte = &s->flags[bit >> 3];
        result = result * 2 + ((*byte & mask) != 0);
        if (write) {
            if ((value >> (width - 1 - i)) & 1) *byte |= mask;
            else *byte &= ~mask;
        }
    }
    return result;
}

extern bool scene_draw(unsigned command);
extern bool scene_draw_at(unsigned command,unsigned instruction);
extern bool act3_script_clip(unsigned key);
extern bool voice_play(unsigned id);

static bool ready(const struct investigation *s)
{
    return !s->count && (s->sentence_done || s->selected_pos == s->selected_count);
}

static uint16_t evaluate(struct investigation *, unsigned, unsigned);
static uint16_t operand(struct investigation *s, unsigned modes, unsigned v, unsigned depth)
{
    if (modes & 1) return evaluate(s, v, depth + 1);
    return modes & 8 ? flags(s, v, false, 0) : v;
}

static uint16_t evaluate(struct investigation *s, unsigned pos, unsigned depth)
{
    if (s->fault != NONE || s->jump != NONE) return 0;
    if (depth > 96 || pos >= node_count ||
        !script_nodes[pos].code) { s->fault = pos; return 0; }
    const struct node n = script_nodes[pos];
    unsigned op = n.code - 1;
    unsigned a = n.a, b = n.b;
    if (op >= 30 && op <= 39) {
        if (n.modes & 1) evaluate(s, a, depth + 1);
        if (n.modes & 2) evaluate(s, b, depth + 1);
        return 0;
    }
    switch (op) {
    case 1: case 2: case 3:
    case 6: case 7: case 8: case 9:
    case 16: case 17: case 18:
    case 49: case 50: case 51: {
        uint16_t left = operand(s, n.modes, a, depth);
        uint16_t right = operand(s, n.modes >> 1, b, depth);
        if (op <= 3) return left + right;
        if (op <= 9) return left & right;
        if (op <= 18) return left == right ? UINT16_MAX : 0;
        return left | right;
    }
    case 22: case 23: case 40: case 41: case 42: {
        uint16_t left = operand(s, n.modes, a, depth);
        uint16_t right = operand(s, n.modes >> 1, b, depth);
        bool result;
        switch (op) {
        case 22: result=right<left; break;
        case 23: result=right<=left; break;
        case 42: result=right>=left; break;
        default: result=right>left; break;
        }
        return result ? UINT16_MAX : 0;
    }
    case 52: case 53:
        if (n.modes & 2) return evaluate(s, b, depth + 1);
        return 0;
    case 54: case 55:
        /* SUBCODE 1702E keeps this menu prefix after a choice finishes.
         * Run its introduction once when the player first reaches it. */
        if (ready(s) && s->selected_pos>s->menu_floor) {
            if (s->menu_depth == sizeof(s->menu_parents)) { s->fault = pos; return 0; }
            s->menu_parents[s->menu_depth++] = s->menu_floor;
            s->menu_floor=s->selected_pos;
            if (n.modes&2) return evaluate(s,b,depth+1);
        }
        return 0;
    case 57:
        /* SUBCODE 17078 pops the last retained menu depth on Change Subject. */
        if (ready(s) && s->menu_depth)
            s->menu_floor = s->menu_parents[--s->menu_depth];
        return 0;
    case 14: {
        unsigned current = flags(s, a, false, 0);
        unsigned max = (1u << ((a & 15) + 1)) - 1;
        if (ready(s) && current < max) flags(s, a, true, current+1);
        return 0;
    }
    case 28: case 29:
        if (ready(s)) flags(s, a, true, operand(s, n.modes >> 1, b, depth));
        return 0;
    case 21:
        return a && a <= s->previous_count ? s->previous_roots[s->previous_count-a] : NONE;
    case 11:
        if (ready(s)) {
            if (a>=node_count || script_nodes[a].code!=34 || script_nodes[a].a<57 ||
                script_nodes[a].a>95 || s->saved_call) { s->fault=pos; return 0; }
            s->return_scene=s->scene;
            s->return_module=s->module;
            s->return_root=s->root;
            s->return_depth=s->previous_count;
            memcpy(s->return_history,s->previous_roots,sizeof(s->return_history));
            s->saved_call=true;
            s->next_module=script_nodes[a].a-57;
            s->jump=script_nodes[a].b;
        }
        return 0;
    case 58:
        if (ready(s)) {
            if (!s->saved_call) { s->fault=pos; return 0; }
            s->next_module=s->return_module;
            s->jump=s->return_root;
        }
        return 0;
    case 12: {
        if (s->caller_count == 16) { s->fault = pos; return 0; }
        s->callers[s->caller_count++] = s->current_routine;
        s->current_routine = a;
        uint16_t result = evaluate(s, a, depth + 1);
        s->current_routine = s->callers[--s->caller_count];
        return result;
    }
    case 59:
        for (unsigned i = 0; i < s->caller_count; ++i)
            if (s->callers[i] == a) return 1;
        return 0;
    case 60:
        if (!a) return s->current_routine;
        return a <= s->caller_count ? s->callers[s->caller_count-a] : NONE;
    case 48: return evaluate(s, a, depth + 1);
    case 19: case 20:
        if (ready(s)) flags(s, a, true, op == 20 ? NONE : 0);
        return 0;
    case 24: case 25: case 26: case 27:
        if (operand(s, n.modes, a, depth)) return evaluate(s, b, depth + 1);
        return op < 26 ? evaluate(s, n.c, depth + 1) : 0;
    case 45: return 0;
    case 43: if (ready(s)) s->jump = a; return 0;
    case 44:
        if (ready(s)) {
            const struct node target = script_nodes[a];
            if (target.code != 34 || target.a < 57 || target.a > 95) s->fault = pos;
            else { s->next_module = target.a - 57; s->jump = target.b; }
        }
        return 0;
    case 46: case 47: return operand(s, n.modes, a, depth) ? 0 : UINT16_MAX;
    case 56:
        if (s->sentence_done) return 0;
        if (s->selected_pos < s->selected_count) {
            if (s->selected[s->selected_pos] != a) return 0;
            ++s->selected_pos;
            evaluate(s, b, depth+1);
            if (s->selected_pos == s->selected_count && !s->count) s->sentence_done = true;
            --s->selected_pos;
            return 0;
        }
        if (s->count == MAX_CHOICES) { s->fault = pos; return 0; }
        s->choices[s->count++] = (struct choice){a, b};
        return 0;
    case 62: case 63: {
        unsigned count = 0, pc = b;
        while (pc < node_count) {
            const struct node *v = script_nodes + pc;
            if (count >= 64) { s->fault = pos; return 0; }
            if (v->code != 38 && v->code != 39 && v->code != 40) {
                ++count; break;
            }
            ++count;
            if (!(v->modes & 2)) break;
            pc = v->b;
        }
        if (!count) { s->fault = pos; return 0; }
        unsigned index = flags(s, a, false, 0);
        if (op == 62) {
            s->random = s->random * 1664525u + 1013904223u;
            index = (s->random >> 16) % count;
        }
        if (index >= count) { s->fault = pos; return 0; }
        pc=b;
        for (unsigned i=0;i<index;i++) pc=script_nodes[pc].b;
        const struct node *option=&script_nodes[pc];
        unsigned target=(option->code>=38 && option->code<=40) ? option->a : pc;
        evaluate(s,target,depth+1);
        /* The first HQ Move menu visits an empty sequential branch after
         * listing the other rooms. The next Move menu then offers Hallway. */
        bool empty_menu_branch=op==63 && script_nodes[target].code==46 &&
                               s->count && s->selected_pos==s->selected_count;
        if ((ready(s) || empty_menu_branch) && (op == 62 || index + 1 < count))
            flags(s, a, true, index + 1);
        return 0;
    }
    case 67: case 68:
        if (ready(s)) {
            if (s->line_count == MAX_LINES) { s->fault = pos; return 0; }
            struct line line = {0, a};
            if (op == 67) {
                const struct node pair = script_nodes[a];
                line = (struct line){pair.a, pair.b};
            }
            s->lines[s->line_count++] = line;
        }
        return 0;
    case 66:
        if (a < node_count && script_nodes[a].a == 5) {
            // SP06 reads the configured input device before Mika's briefing.
            if (script_nodes[a].b == 0x7972) return 0; /* joypad */
            unsigned address=script_nodes[a].b;
            if (address==0x79f0) return s->flags[353];
            if (address==0x79e0) return s->save_result;
            if (address>=0x79e2 && address<=0x79e8 && !(address&1))
                return save_exists(1+(address-0x79e2)/2);
            if (address==0x96dc && s->module==26) return flashlight_target();
            switch (address) {
            case 0x7908: return s->practice.shots;
            case 0x790a: return s->practice.enemies;
            case 0x790c: return s->practice.civilians;
            case 0x790e: return s->practice.misses;
            case 0x7910: return s->practice.damage;
            case 0x7916: return s->practice.all_civilians;
            case 0x7918: return s->practice.drawn;
            }
            if (ready(s)) s->fault = pos;
            return 0;
        }
        /* Other system commands take effect at their queued dialogue page. */
        /* fall through */
    case 0: case 4: case 5: case 10: case 71: case 13: case 15: case 61: case 69: case 70: case 72: case 73: case 74:
        if (ready(s)) {
            if (s->effect_count == 128) { s->fault = pos; return 0; }
            s->effects[s->effect_count].pos = pos;
            s->effects[s->effect_count++].page = s->line_count;
        }
        return 0;
    case 65:
        if (a==12) {
            /* SYS12 preserves the first 429 retail story bits at act transfer. */
            if (ready(s)) {
                s->flags[53]&=0xf8;
                memset(s->flags+54,0,352-54);
            }
            return 0;
        }
        if (s->module!=0 || !s->saved_call || a!=0) { if (ready(s)) s->fault=pos; }
        return 0;
    default:
        if (ready(s)) s->fault = pos;
        return 0;
    }
}

extern bool item_display(unsigned item, unsigned position);
extern void item_hide(void);
extern void clear_dialogue(void);
extern bool act2_title_fade(void);
extern bool room202_expression(unsigned);
extern void motion_start(unsigned, unsigned);
extern bool motion_wait(unsigned);
extern bool fm_music_start(unsigned);
extern void fm_music_wait(void);
extern bool music_start(unsigned);
extern bool music_wait(void);
extern bool fm_effect_start(unsigned);
extern void fm_effect_wait(void);
extern void resident_block(bool);
extern void scene_wait(unsigned);

/* The US interpreter stores its reduced sound level alongside the save flags.
 * The first 352 bytes belong to script-addressable bits. Version 1 records
 * already preserve the two trailing bytes and older builds wrote them as zero. */
static bool quiet_audio;
unsigned script_audio_level(unsigned level)
{
    if (!quiet_audio) return level;
    /* SCSP total level 20 scales a full-volume sample by 111/254. */
    return level>235 ? 255 : level+20;
}

/* SP20 stores each CD time component as packed decimal. Its evidence cues
 * include frame 80, which the running 00..74 counter passes at the next second. */
static unsigned decimal_time(unsigned value)
{
    return 10*(value>>4)+(value&15);
}

static bool system_effect(struct investigation *s, unsigned pos)
{
    if (pos >= node_count) return false;
    const struct node command = script_nodes[pos];
    if (command.a == 4 && !(command.modes & 2) && command.b == 0)
        return practice_play(&s->practice);
    if (command.a==4 && !(command.modes&2) && command.b==1)
        return factory_fight(&s->practice);
    if (command.a==4 && !(command.modes&2) && command.b==2)
        return bathroom_fight(&s->practice);
    if (command.a==4 && !(command.modes&2) && command.b==4)
        return hostage_fight(&s->practice);
    if (command.a==4 && !(command.modes&2) && (command.b==7 || command.b==9))
        return office_or_taxi_fight(&s->practice,command.b==9) &&
               (command.b!=9 || s->practice.damage>=6 || hospital_road_clip("HQFALL.BIN"));
    if (command.a==4 && !(command.modes&2) && (command.b>=12 && command.b<=14))
        return swarm_fight(&s->practice,command.b);
    if (command.a==4 && !(command.modes&2) && command.b==10)
        return mika_fight(&s->practice);
    if (command.a==4 && !(command.modes&2) && command.b==8)
        return tunnel_fight(&s->practice);
    if (command.a==4 && !(command.modes&2) && command.b==6)
        return crawler_fight(&s->practice);
    if (command.a==4 && !(command.modes&2) && command.b==5)
        return skeleton_fight(&s->practice);
    if (command.a==4 && !(command.modes&2) && command.b==3)
        return apartment_fight(&s->practice);
    if (command.a==1 && !(command.modes&2) && command.b>=1 && command.b<=4) {
        unsigned result=save_write(command.b,s);
        s->save_result=result==0?0:1;
        return result==0 || result==4;
    }
    if (s->module==26 && command.a==10 && !(command.modes&2) && command.b<=1)
        return queens_light(command.b!=0);
    bool videophone=s->module==18 || s->module==35;
    if ((s->module==9 || s->module==27 || s->module==28 || videophone) && command.a==6 && (command.modes&2) && command.b<node_count) {
        const struct node setting=script_nodes[command.b];
        if (s->scene==0x070e && setting.a==0x971c && setting.b==1) return true;
        if (setting.a==0x971e && setting.b==255) return true;
        if (setting.a==0x9718 && setting.b && setting.b<=sizeof(s->password)) {
            s->password_input=true;
            s->password_limit=setting.b;
            /* The age question supplies a list of two-digit answers. Other
             * questions begin with the script's WRONG response. */
            s->numeric_answer=s->count && !memcmp(script_text+s->choices[0].text,"00\xff",3);
            s->phone_cursor=s->numeric_answer ? 10 : 0;
            s->password_length=0;
            return true;
        }
        if (setting.a==0x971a && setting.b==0) return true;
        if (setting.a==0x971a && setting.b==1) {
            s->phone_keypad=true;
            s->phone_cursor=10;
            s->dial_length=0;
            return true;
        }
    }
    if (command.a==6 && (command.modes&2) && command.b<node_count) {
        const struct node pair=script_nodes[command.b];
        if (pair.code!=35) return false;
        if (pair.a==0x79f0 && pair.b<=2) {
            s->flags[353]=pair.b;
            return true;
        }
        /* SP38 toggles the display during the flash before the two CD montages.
         * The changing frames are included in the 3203, 3207 and 3200 clips. */
        if (pair.a==0x79ee && s->module==38 && ((s->scene==0x3203 && pair.b==1) ||
                                                (s->scene==0x3200 && !pair.b))) return true;
        if (pair.a==0x79ee && s->module==37) {
            /* The numbered display changes during the snowy approach. */
            if (s->scene==0x2004 && pair.b>=3 && pair.b<=8) {
                char file[]="A3D0.BIN";
                file[3]+=(char)pair.b;
                return hospital_road_clip(file);
            }
            if (s->scene==0x2004 && (pair.b==9 || !pair.b)) return true;
            if (s->scene==0x2700 && pair.b<=1) return true;
        }
        /* SP33 switches the videophone display within the track 14 animation. */
        if (pair.a==0x79ee && s->module==33 && (s->scene==0x1504) &&
            (pair.b==2 || pair.b==0)) return true;
        if (pair.a!=0xffff || pair.b>1) return false;
        s->flags[352]=pair.b;
        quiet_audio=pair.b!=0;
        return true;
    }
    if (command.a==7 && !(command.modes&2) && command.b<=1) {
        resident_block(command.b!=0);
        return true;
    }
    if (s->module == 38 && command.a == 9 && command.b == 1) {
        extern bool credits_play(void);
        s->finished = credits_play();
        return s->finished;
    }
    if (((s->module==0 && s->saved_call) || (s->module==37 && s->scene==0x2905)) && command.a==9 && command.b==2) {
        s->finished=true;
        return true;
    }
    if (videophone && s->saved_call && command.a==11 && !(command.modes&2)) {
        if (command.b==0) return true;
        if (command.b!=1 || !scene_draw(s->return_scene)) return false;
        s->scene=s->return_scene;
        return true;
    }
    if ((s->module==20 && s->scene>=0x1100 && s->scene<=0x1111) ||
        (s->module==31 && s->scene>=0x1f00 && s->scene<=0x1f0c)) {
        if (command.a==13 && (command.modes&2) && command.b<node_count) {
            const struct node minute=script_nodes[command.b];
            if (minute.code!=32 || !(minute.modes&2) || minute.b>=node_count) return false;
            const struct node second=script_nodes[minute.b];
            if (second.code!=31) return false;
            unsigned frame=decimal_time(second.b);
            return disc_wait_track_sector((decimal_time(minute.a)*60+decimal_time(second.a))*75+
                                          (frame>75?75:frame));
        }
        /* SP20 includes the displayed evidence in its timed picture. */
        if (s->module==20 && command.a==8) return true;
    }
    if (command.a != 8) return false;
    if (!(command.modes & 2)) {
        if (command.b != 0) return false;
        item_hide();
        return true;
    }
    if (command.b >= node_count) return false;
    const struct node show = script_nodes[command.b];
    if (show.a != 1 || !(show.modes & 2) || show.b >= node_count) return false;
    const struct node args = script_nodes[show.b];
    return item_display(args.a, args.b);
}

/* The Sega CD queues the sound start separately from its wait. Apply visual
 * commands between them before blocking on the synchronous SCSP player. */
static bool play_script_voice(const struct investigation *s,unsigned voice)
{
    if (!voice_play(voice)) return false;
    if (s->module==33 && s->scene==0x0a02 && voice==741) {
        clear_dialogue();
        return cockpit_clip("HQCLEAR.BIN");
    }
    return true;
}

static void play_effects(struct investigation *s)
{
    unsigned voice = NONE, voice_pos = NONE;
    while (s->effect_index < s->effect_count && s->effects[s->effect_index].page == s->page) {
        unsigned pos = s->effects[s->effect_index++].pos;
        const struct node n = script_nodes[pos];
        unsigned op = n.code-1;
        if (voice != NONE && op != 66) {
            if (!play_script_voice(s,voice)) { s->fault = voice_pos; return; }
            voice = NONE;
        }
        bool ok = true;
        switch (op) {
        case 0:
            if (s->module==38 && pos==0x8c2)
                ok=hospital_road_clip("A3M8C2.BIN");
            else if (s->module==37 && pos==0xf73)
                ok=hospital_road_clip("A3RDOOR1.BIN");
            else if (s->module==37 && pos==0xf2d)
                ok=hospital_road_clip("A3FAILFX.BIN");
            else if (s->module==37 && (pos==0xc8e || pos==0xce5))
                ok=hospital_road_clip(pos==0xc8e ? "A3E12A.BIN" : "A3E13A.BIN");
            else if (s->module==37 && pos==0xc35)
                ok=hospital_road_clip("A3DOOR.BIN");
            else if (s->module==37 && pos==0x6ca)
                ok=hospital_road_clip("A3RFADE.BIN");
            else if (s->module==37 && pos==0x4e5)
                ok=hospital_road_clip("A3OUT.BIN");
            else if (s->module==37 && pos==0x2b9)
                ok=hospital_road_clip("A3REVEAL.BIN");
            else if (s->module==37 && (pos==0x50d || pos==0x5bd))
                ok=hospital_road_clip("A3LARGE.BIN");
            else if (s->module==37 && (pos==0x57a || pos==0x5ef))
                ok=hospital_road_clip("A3SMALL.BIN");
            else if (s->module==37 && pos==0x2c) {
                extern void canopy_sound(void);
                canopy_sound();
                ok=hospital_road_clip("A3CANOPY.BIN");
            } else if (s->module==37 && pos==0x249)
                ok=hospital_road_clip("A3EXIT.BIN");
            else if (s->module==37 && pos==0x10f)
                ok=hospital_road_clip("A3TAKE1.BIN");
            else if (s->module==36 && s->scene==0x260f && script_nodes[n.a].a==19 && !script_nodes[n.a].b)
                ok=cockpit_clip("A3CDOUT.BIN");
            else if (s->module==36 && (pos==0x3e0 || pos==0x447 || pos==0x5e0))
                ok=act3_script_clip(pos);
            else if (s->scene==0x1d01 && script_nodes[n.a].a==16 && !script_nodes[n.a].b)
                ok=cockpit_clip("QGREEN.BIN");
            else if (s->module==33 && s->scene==0x0a02 && script_nodes[n.a].a==31 && !script_nodes[n.a].b)
                ok=hospital_road_clip("HQALARM.BIN");
            else if (s->module==33 && s->scene==0x0a02 && script_nodes[n.a].a==25 && !script_nodes[n.a].b)
                ok=ceiling_pan();
            else if (s->module==33 && s->scene==0x1202 && !script_nodes[n.a].b &&
                     (script_nodes[n.a].a==20 || script_nodes[n.a].a==25))
                ok=hospital_road_clip(script_nodes[n.a].a==20?"SHUTUP.BIN":"SHUTOUT.BIN");
            else if (s->module==36 && s->scene==0x1603 && script_nodes[n.a].a==26 && !script_nodes[n.a].b)
                ok=hospital_road_clip("ACT3FADE.BIN");
            else if (s->module==33 && s->scene==0x1600 && script_nodes[n.a].a==26 && !script_nodes[n.a].b) {
                extern void street_close(void);
                street_close();
                ok=cockpit_clip("HQFADE.BIN");
            }
            else if (s->scene==0x2301 && !script_nodes[n.a].b && script_nodes[n.a].a==17)
                ok=true; /* The opening clip already contains the driver animation. */
            else if (s->scene==0x2301 && !script_nodes[n.a].b && script_nodes[n.a].a==20)
                ok=cockpit_clip("TAXIOUT.BIN");
            else if (s->scene==0x2300 && script_nodes[n.a].a==28 && !script_nodes[n.a].b)
                ok=cockpit_clip("TAXITURN.BIN");
            else if (s->module==32 && s->scene==0x2404 && script_nodes[n.a].a==16 && !script_nodes[n.a].b)
                ok=cockpit_clip("TUNHIDE.BIN");
            else if (s->module==32 && s->scene==0x0505 && pos==0x8eb)
                ok=hospital_road_clip("TUNBATH.BIN");
            else if (s->module==32 && s->scene==0x2400 && pos==0x294)
                ok=cockpit_clip("TUNLAMP.BIN");
            else if (s->module==32 && s->scene==0x2400 && pos==0x2d9)
                ok=cockpit_clip("TUNIDLE.BIN");
            else if (s->scene==0x1d0c && script_nodes[n.a].a==17 && !script_nodes[n.a].b)
                ok=cockpit_clip("QLABOUT.BIN");
            else if (s->scene==0x1d03 && !script_nodes[n.a].b &&
                (script_nodes[n.a].a==27 || script_nodes[n.a].a==28 || script_nodes[n.a].a==29)) {
                extern bool operating_room_actor(unsigned);
                ok=operating_room_actor(script_nodes[n.a].a);
            }
            else if (s->scene==0x1d0d && !script_nodes[n.a].b &&
                (script_nodes[n.a].a==21 || script_nodes[n.a].a==27))
                ok=hospital_stair_actor(script_nodes[n.a].a);
            else if (s->scene==0x2201 && script_nodes[n.a].a==19 && script_nodes[n.a].b==2)
                ok=cockpit_clip("CABIDLE.BIN");
            else if (s->scene==0x2203 && script_nodes[n.a].a==32 && !script_nodes[n.a].b)
                ok=hospital_road_clip("CARACCEL.BIN");
            else if (n.a >= node_count) ok = false;
            else if (s->scene==0x0a00 && script_nodes[n.a].a==48 &&
                     (script_nodes[n.a].b==0 || script_nodes[n.a].b==5)) {
                ok=chief_picture(script_nodes[n.a].b==5);
            }
            else if (s->scene==0x1b05 && script_nodes[n.a].a==17 && script_nodes[n.a].b==2) {
                ok=napoleon_pose();
            }
            else if (s->scene==0x1c06 && script_nodes[n.a].a>=33) {
                extern bool apartment_list_actor(unsigned,unsigned);
                ok=apartment_list_actor(script_nodes[n.a].a,script_nodes[n.a].b);
            }
            else if (s->scene==0x1b05 && !script_nodes[n.a].b) {
                extern bool benson_actor(unsigned);
                ok=benson_actor(script_nodes[n.a].a);
            }
            else if (!script_nodes[n.a].b && ((s->scene==0x1a02 && script_nodes[n.a].a==30) ||
                     (s->scene==0x1a07 && script_nodes[n.a].a==32))) {
                extern bool videophone_movie(const char *);
                ok=videophone_movie(s->scene==0x1a02?"NAPCALL.BIN":"MASKOFF.BIN");
            }
            else if (s->scene==0x0100 && script_nodes[n.a].a==16 && !script_nodes[n.a].b) {
                extern bool oleen_door(void);
                ok=oleen_door();
            }
            else if (s->scene==0x1601 && script_nodes[n.a].a==18 && !script_nodes[n.a].b) ok=act2_title_fade();
            else if (s->scene==0x070e) ok=report_start(script_nodes[n.a].a);
            else if (s->scene==0x0509 || (s->scene==0x0600 && script_nodes[n.a].a==18)) ok=room202_expression(script_nodes[n.a].a);
            else motion_start(script_nodes[n.a].a, script_nodes[n.a].b);
            break;
        case 4: case 5:
            clear_dialogue();
            if (op==5 && n.a==36 && ((s->module==33 && (s->scene==0x0a02 || s->scene==0x1400)) || (s->module==37 && s->scene==0x2805))) {
                extern void ceiling_sound(void);
                if (s->scene==0x1400) ok=hospital_road_clip("MIKA36.BIN");
                if (ok) ceiling_sound();
                break;
            }
            if (op==5 && (s->scene==0x2300 || s->scene==0x1202 || (s->module==37 && s->scene==0x2703)) && n.a==36) {
                extern void taxi_sound(void);
                if (s->scene==0x1202) ok=hospital_road_clip("SHUT36.BIN");
                taxi_sound();
                if (s->scene==0x1202 && ok) {
                    extern bool plaza_played(void);
                    while (!plaza_played()) scene_wait(1);
                }
                break;
            }
            if (s->module==33 && (s->scene==0x1201 || s->scene==0x1400) && n.a>=742 && n.a<=760) {
                char file[]="HQ000.BIN";
                file[2]+=(char)(n.a/100); file[3]+=(char)(n.a/10%10); file[4]+=(char)(n.a%10);
                ok=hospital_road_clip(file);
            }
            if (s->module==33 && s->scene==0x0a02 && n.a>=732 && n.a<=741) {
                static const char *const lines[]={"HQ732.BIN","HQ733.BIN","HQ734.BIN","HQ735.BIN","HQ736.BIN",
                                                  "HQ737.BIN","HQ738.BIN","HQ739.BIN","HQ740.BIN","HQ741.BIN"};
                ok=hospital_road_clip(lines[n.a-732]);
            }
            if (s->module==33 && s->scene==0x1202 && n.a>=709 && n.a<=731) {
                char file[]="SHUT000.BIN";
                file[4]+=(char)(n.a/100);
                file[5]+=(char)(n.a/10%10);
                file[6]+=(char)(n.a%10);
                ok=hospital_road_clip(file);
            }
            if (s->scene==0x2301 && n.a>=702 && n.a<=708) {
                static const char *const clips[]={"CAB702.BIN","CAB703.BIN","CAB704.BIN","CAB705.BIN",
                                                 "CAB706.BIN","CAB707.BIN","CAB708.BIN"};
                ok=cockpit_clip(clips[n.a-702]);
            }
            if (s->scene==0x2402 && n.a>=677 && n.a<=687) {
                static const char *const portraits[]={
                    "TUN677.BIN","TUN678.BIN","TUN679.BIN","TUN680.BIN","TUN681.BIN",
                    "TUN682.BIN","TUN683.BIN","TUN684.BIN","TUN685.BIN","TUN686.BIN","TUN687.BIN"
                };
                ok=cockpit_clip(portraits[n.a-677]);
            }
            if (s->module==32 && ((s->scene==0x2404 && n.a>=690 && n.a<=693) ||
                                 (s->scene==0x0505 && n.a>=694 && n.a<=701))) {
                char file[]="TUN000.BIN";
                file[3]+=(char)(n.a/100);
                file[4]+=(char)(n.a/10%10);
                file[5]+=(char)(n.a%10);
                ok=hospital_road_clip(file);
            }
            if (s->module==36 && s->scene==0x1603 && n.a==771) {
                /* Voice reads use low work RAM. Move the city to VDP1 before playback. */
                extern void street_finish_pan(void);
                street_finish_pan();
                ok=hospital_road_clip("ACT3LAMP.BIN");
            }
            if (s->module==36 &&
                ((s->scene>=0x2500 && s->scene<=0x2509 && n.a>=772 && n.a<=844) ||
                 (s->scene>=0x2600 && s->scene<=0x260a && n.a>=845 && n.a<=879)))
                ok=act3_script_clip(0x1000+n.a);
            if ((s->module==37 && ((n.a>=880 && n.a<=947) || n.a==950)) ||
                (s->module==38 && ((n.a>=951 && n.a<=1179) || (n.a>=1182 && n.a<=1184)))) {
                char file[]="A3V0000.BIN";
                unsigned last=n.a<1000 ? 5 : 6;
                memcpy(file+last+1,".BIN",5);
                for (unsigned value=n.a;value;value/=10)
                    file[last--]=(char)('0'+value%10);
                ok=hospital_road_clip(file);
                if (ok) plaza_use_video_clock();
            }
            if (s->scene==0x2101) plaza_mika_voice(n.a);
            if (s->scene==0x1c06 || s->scene==0x1c07) plaza_apartment_voice(n.a);
            if (s->scene==0x2201 && n.a>=565 && n.a<=569) {
                static const char *const cockpit[]={"CAB565.BIN","CAB566.BIN","CAB567.BIN","CAB568.BIN","CAB569.BIN"};
                ok=cockpit_clip(cockpit[n.a-565]);
            }
            if (s->scene==0x1f10 && n.a>=658 && n.a<=660) {
                static const char *const views[]={"QVIS658.BIN","QVIS659.BIN","QVIS660.BIN"};
                ok=hospital_road_clip(views[n.a-658]);
            }
            if (s->scene>=0x1e03 && s->scene<=0x1e06 && n.a>=608 && n.a<=645) {
                char file[]="QRC600.BIN";
                file[4]+=(char)((n.a/10)%10);
                file[5]+=(char)(n.a%10);
                ok=hospital_road_clip(file);
            }
            if (s->scene==0x2204 && n.a>=560 && n.a<=564) {
                static const char *const roads[]={"ROAD560.BIN","ROAD561.BIN","ROAD562.BIN","ROAD563.BIN","ROAD564.BIN"};
                ok=hospital_road_clip(roads[n.a-560]);
            }
            voice = n.a;
            voice_pos = pos;
            break;
        case 10:
            /* The farewell recording shares low RAM with other scene assets. */
            ok = fm_music_start(n.a==80 && s->module!=38 ? 255 : n.a);
            break;
        case 71: fm_music_wait(); break;
        case 13: ok = music_start(n.a); break;
        case 15:
            if (s->scene==0x1c06) plaza_apartment_stop();
            ok = fm_effect_start(n.a); break;
        case 61: ok = scene_draw_at(n.a,pos); if (ok) s->scene=n.a; break;
        case 66: ok = system_effect(s,n.a); break;
        case 69:
            if (s->module==38 && (pos==0x8be || pos==0x8db || pos==0x948 || pos==0xb38)) {
                extern bool plaza_played(void);
                while (!plaza_played()) scene_wait(1);
                break;
            }
            if (s->module==38 && n.a==15 && (pos==0xb40 || pos==0xb48 ||
                pos==0xb5e || pos==0xb6a || pos==0xb76 || pos==0xb7e)) {
                /* These actor boundaries are included in the CD-sector-timed shots. */
                break;
            }
            if (s->module==38 && ((pos==0x295 && n.a==18) ||
                                   ((pos==0x2a5 || pos==0x6a6) && n.a==32))) {
                /* The tail of line 1009 and the camera clips for actors 18 and 32 contain
                 * the actor animations that the retail script waits for. */
                extern bool plaza_played(void);
                while (!plaza_played()) scene_wait(1);
                break;
            }
            if (s->module==37 && (pos==0xf7a || pos==0xf82)) {
                static const char *const clips[]={"A3RDOOR2.BIN","A3RDOOR3.BIN","A3RDOOR4.BIN","A3RHALL2.BIN"};
                extern bool plaza_played(void);
                unsigned first=pos==0xf7a ? 0 : 3, last=pos==0xf7a ? 3 : 4;
                while (!plaza_played()) scene_wait(1);
                for (unsigned i=first;ok && i<last;++i) {
                    ok=hospital_road_clip(clips[i]);
                    if (ok) while (!plaza_played()) scene_wait(1);
                }
                break;
            }
            if (s->module==37 && (pos==0xc95 || pos==0xc9d || pos==0xcec || pos==0xcf4)) {
                extern bool plaza_played(void);
                while (!plaza_played()) scene_wait(1);
                const char *file=pos==0xc95 ? "A3E12B.BIN" : pos==0xc9d ? "A3DC99B.BIN" :
                                 pos==0xcec ? "A3E13B.BIN" : "A3DCF0BA.BIN";
                ok=hospital_road_clip(file);
                if (ok) while (!plaza_played()) scene_wait(1);
                if (ok && pos==0xcf4) {
                    ok=hospital_road_clip("A3DCF0BB.BIN");
                    if (ok) while (!plaza_played()) scene_wait(1);
                }
                break;
            }
            if (s->module==37 && (pos==0xaec || pos==0xc3c || pos==0xc44)) {
                extern bool plaza_played(void);
                while (!plaza_played()) scene_wait(1);
                if (pos!=0xaec) {
                    ok=hospital_road_clip(pos==0xc3c ? "A3DOOR2.BIN" : "A3HALL2.BIN");
                    if (ok) while (!plaza_played()) scene_wait(1);
                }
                break;
            }
            if (s->module==37 && pos==0x2f7) { ok=church_transition(true); break; }
            if (s->module==37 && pos==0x494) break; /* The aisle dissolve has finished. */
            if (s->module==37 && pos==0x4c7) {
                extern bool church_portrait_pan(void);
                ok=church_portrait_pan();
                break;
            }
            if (s->module==37 && (pos==0x33 || pos==0x11d)) {
                extern bool plaza_played(void);
                while (!plaza_played()) scene_wait(1);
                if (pos==0x11d) {
                    ok=hospital_road_clip("A3TAKE2.BIN");
                    if (ok) {
                        while (!plaza_played()) scene_wait(1);
                        ok=hospital_road_clip("A3TAKE3.BIN");
                    }
                }
                break;
            }
            if (s->module==36 && s->scene>=0x260b && s->scene<=0x260e && n.a==15) {
                static const unsigned cut_sectors[]={356,2958,4365,4732};
                ok=disc_wait_track_sector(cut_sectors[s->scene-0x260b]);
                break;
            }
            if (s->module==33 && s->scene==0x0a02 && n.a==25) break; /* ceiling_pan completed the scroll */
            if ((s->scene>=0x1e03 && s->scene<=0x1e06 && (n.a==38 || n.a==39)) ||
                (s->module==33 && s->scene==0x0a02 && n.a==31) ||
                (s->scene==0x2300 && n.a==28) || (s->scene==0x1202 && n.a==20)) {
                extern bool plaza_played(void);
                while (!plaza_played()) scene_wait(1);
                break;
            }
            if (s->scene==0x1f0d && n.a==16) { plaza_wait_frames(132); break; }
            if (s->scene==0x1f0e && n.a==30) { plaza_wait_frames(152); break; }
            if (s->scene==0x1f0f && n.a==31) { plaza_wait_frames(130); break; }
            if (s->scene==0x1d0d && (n.a==21 || n.a==27)) {
                plaza_wait_frames(n.a==21?50:67);
                break;
            }
            if (s->scene==0x2201 && n.a==19) { plaza_wait_frames(71); break; }
            if (s->scene==0x0a00 && n.a==48) { plaza_wait_frames(10); break; }
            if (s->scene==0x1c06 && (n.a==39 || n.a==40)) {
                extern bool plaza_played(void);
                while (!plaza_played()) scene_wait(1);
                break;
            }
            if (s->scene==0x1c07 && n.a==21) { plaza_wait_frames(604); break; }
            if (s->scene==0x1c06 && (n.a==16 || n.a==17 || n.a==23)) {
                plaza_wait_frames(n.a==16 ? 124 : n.a==17 ? 1927 : 5016);
                break;
            }
            if (s->scene==0x0100 && n.a==16) { plaza_wait_frames(105); break; }
            if (s->scene==0x0102 && n.a==31) { extern bool oleen_waiting_room(void); ok=oleen_waiting_room(); break; }
            if ((s->module==36 && s->scene==0x2508 && n.a==32) ||
                (s->scene==0x050a && n.a==8) || (s->scene==0x0600 && n.a==18) || (s->scene==0x0602 && n.a==31)) {
                extern bool plaza_played(void);
                while (!plaza_played()) scene_wait(1);
                break;
            }
            if (s->scene==0x0508 && n.a==25) { scene_wait(192); break; }
            if (s->scene==0x0509 && n.a==17) {
                extern void scream_sound(void);
                scene_wait(9);
                scream_sound();
                scene_wait(25+11+11+33);
                break;
            }
            ok = s->scene==0x070e ? report_wait(n.a) : motion_wait(n.a); break;
        case 72: ok = music_wait(); break;
        case 73: fm_effect_wait(); break;
        case 74:
            /* The room bank plays this delay and the Moscow cut during cue 807. */
            if (!(s->module==36 && pos==0x190 && s->scene==0x2509)) scene_wait(n.a);
            break;
        }
        if (!ok) { s->fault = pos; return; }
    }
    if (voice != NONE && !play_script_voice(s,voice)) s->fault = voice_pos;
}

static void run(struct investigation *s, unsigned pc)
{
    s->in_submenu = s->selected_count != 0;
    s->count = s->cursor = s->page = s->text_offset = s->line_count = 0;
    /* SP37 runs straight into SP38. The ending alone has 85 routines
     * before the farewell menu returns control to the player. */
    for (unsigned i = 0; i < (s->module == 38 ? 128u : 64u); i++) {
        s->jump = NONE;
        if (s->module != s->next_module) {
            if (!load_script(s->next_module)) { s->fault = pc; return; }
            s->module = s->next_module;
        }
        s->effect_count = s->effect_index = 0;
        s->selected_pos = 0;
        s->sentence_done = false;
        s->current_routine = pc;
        evaluate(s, pc, 0);
        if (s->fault == NONE) play_effects(s);
        if (s->fault != NONE || s->finished) return;
        if (s->jump != NONE) {
            s->menu_floor = 0;
            s->menu_depth = 0;
            s->selected_count = 0;
            if (s->previous_count == 3) {
                s->previous_roots[0] = s->previous_roots[1];
                s->previous_roots[1] = s->previous_roots[2];
                --s->previous_count;
            }
            s->previous_roots[s->previous_count++] = s->root;
            if (s->saved_call && s->module!=s->return_module && s->next_module==s->return_module) {
                s->previous_count=s->return_depth;
                memcpy(s->previous_roots,s->return_history,sizeof(s->previous_roots));
                s->saved_call=false;
            }
            s->root = s->jump;
            s->root_cursor = 0;
            s->in_submenu = false;
        }
        if (!s->count) s->selected_count = s->menu_floor;
        if (s->line_count || s->count) {
            if (!s->in_submenu && s->root_cursor < s->count) s->cursor = s->root_cursor;
            return;
        }
        s->in_submenu = false;
        pc = s->root;
    }
    s->fault = pc;
}

static int dial_choice(const struct investigation *s, const uint8_t *value, unsigned length)
{
    for (unsigned i=0; i<s->count; ++i) {
        const uint8_t *label=script_text+s->choices[i].text;
        unsigned j=0;
        while (j<length && label[j]==value[j]) ++j;
        if (j==length && label[j]==0xff) return i;
    }
    return -1;
}

void script_dial(struct investigation *s,int horizontal,int vertical,bool confirm,bool erase)
{
    static const uint8_t keys[]="123456789*0#";
    if (!s->phone_keypad || s->page<s->line_count || s->fault!=NONE) return;
    int x=s->phone_cursor%3+horizontal, y=s->phone_cursor/3+vertical;
    if (x>=0 && x<3 && y>=0 && y<4) s->phone_cursor=y*3+x;
    if (erase && s->dial_length) --s->dial_length;
    if (!confirm || s->dial_length==sizeof(s->dial_digits)) return;
    s->dial_digits[s->dial_length++]=keys[s->phone_cursor];

    /* The retail script groups full numbers under their first digit. Inspect
     * that submenu without committing its actions until the number matches. */
    int prefix=dial_choice(s,s->dial_digits,1);
    if (prefix<0 && s->dial_length<sizeof(s->dial_digits)) return;
    const uint8_t zero='0';
    if (prefix<0) prefix=dial_choice(s,&zero,1);
    if (prefix<0 || s->selected_count+2>16) return;
    struct investigation probe=*s;
    probe.count=probe.line_count=probe.effect_count=probe.selected_pos=0;
    probe.sentence_done=false;
    probe.selected[probe.selected_count++]=s->choices[prefix].text;
    evaluate(&probe,probe.root,0);
    int number=dial_choice(&probe,s->dial_digits,s->dial_length);
    if (number<0 && s->dial_length==sizeof(s->dial_digits)) number=dial_choice(&probe,&zero,1);
    if (number<0) return;
    s->phone_keypad=false;
    s->selected[s->selected_count++]=s->choices[prefix].text;
    s->selected[s->selected_count++]=probe.choices[number].text;
    run(s,s->root);
}

unsigned password_key_x(unsigned key)
{
    static const unsigned bottom[]={32,48,64,96,152,208};
    return key<26 ? 32+16*(key%13) : bottom[key-26];
}

void script_password(struct investigation *s,int h,int v,bool confirm,bool erase,bool submit)
{
    if (!s->password_input || s->fault!=NONE || s->page<s->line_count) return;
    static const uint8_t keys[]="ABCDEFGHIJKLMNOPQRSTUVWXYZ-.'\b \r";
    unsigned key=s->phone_cursor, row=key/13;
    uint8_t ch;
    if (s->numeric_answer) {
        int x=key%3+h, y=key/3+v;
        if (x>=0 && x<3 && y>=0 && y<4) key=y*3+x;
        ch=(uint8_t)"123456789*0#"[key];
    } else {
        if (h) {
            unsigned count=row==2 ? 6 : 13;
            key=row*13+((int)(key%13)+h+(int)count)%count;
        }
        if (v) {
            unsigned x=password_key_x(key);
            row=((int)row+v+3)%3;
            key=row*13;
            unsigned best=256;
            for (unsigned i=key;i<(row==2?32:(row+1)*13);++i) {
                unsigned other=password_key_x(i);
                unsigned delta=x>other?x-other:other-x;
                if (delta<best) { best=delta; key=i; }
            }
        }

        ch=keys[key];
    }
    s->phone_cursor=key;
    if (erase || (confirm && ch=='\b')) {
        if (s->password_length) --s->password_length;
    } else if (submit || (confirm && ch=='\r')) {
        int choice=dial_choice(s,s->password,s->password_length);
        if (choice<0 && s->module==27 && s->password_length)
            choice=dial_choice(s,(const uint8_t *)"OTHER THAN BENSON",17);
        if (choice<0 && s->module==28 && s->password_length)
            choice=dial_choice(s,(const uint8_t *)"OTHER THAN QUEEN",16);
        if (choice<0) choice=s->password_length ? dial_choice(s,(const uint8_t *)(s->numeric_answer?"00":"WRONG"),s->numeric_answer?2:5)
                                                : dial_choice(s,(const uint8_t *)" ",1);
        if (choice<0) { s->fault=s->root; return; }
        s->password_input=false;
        s->cursor=choice;
        script_input(s,0,true,false);
    } else if (confirm && s->password_length<s->password_limit) {
        s->password[s->password_length++]=ch;
    }
}

void script_start(struct investigation *s)
{
    quiet_audio=false;
    *s = (struct investigation){.module = NONE, .next_module = 6, .root = 49, .fault = NONE, .random = 1};
    run(s, s->root);
}

bool script_resume(struct investigation *s)
{
    quiet_audio=s->flags[352]!=0;
    s->next_module=s->module;
    s->fault=NONE;
    if (!load_script(s->module) || s->root>=node_count || !scene_draw(s->scene)) return false;
    if (s->module==33 && s->scene==0x0a02 && flags(s,0x6300,false,0) &&
        !cockpit_clip("HQCLEAR.BIN")) return false;
    /* SP08 leaves the open furniture on screen until Gillian exits the room.
     * A cold load reconstructs the two held poses from those same story flags. */
    if (s->module==22 && s->scene==0x0a00 && flags(s,0x2b30,false,0)) {
        if (!chief_picture(false)) return false;
        plaza_wait_frames(10);
    }
    /* SP32's dark and lit investigation menus share a scene number. */
    if (s->module==32 && s->scene==0x2400 && s->root==0x2e2 &&
        !cockpit_clip("TUNIDLE.BIN")) return false;
    if (s->module==27 && s->scene==0x1b05 && s->root==0x3db && !napoleon_pose()) return false;
    if (s->module==26 && s->scene==0x1d0d && flags(s,0x3fb0,false,0) && !queens_light(true)) return false;
    if (s->module==8 && s->scene==0x0d00) {
        if (flags(s,14256,false,0)) motion_start(24,0);
        if (flags(s,14288,false,0)) motion_start(27,0);
    }
    /* SP30 normally opens the three basement doors before its menu. A
     * loaded game resumes at the menu and must restore the same actors. */
    if (s->module==30 && (s->scene==0x1d07 || s->scene==0x1d08)) {
        for (unsigned door=0;door<3;door++)
            if (flags(s,0x5490+16*door,false,0)) motion_start(32+door,0);
    }
    if (s->module==9 && s->scene==0x0708) {
        if (!flags(s,864,false,0)) motion_start(22,0);
        if (!flags(s,848,false,0)) motion_start(23,0);
    }
    /* The room entry script loads the sound bank before reaching its menu.
     * Continue resumes at that menu, after the original bank-load command. */
    if (s->scene==0x1907 && !voice_play(6)) return false;
    run(s,s->root);
    return s->fault==NONE;
}

const uint8_t *script_page_end(const uint8_t *text,unsigned max_rows)
{
    unsigned rows = 1;
    while (*text != 0xff && *text != 0xf6) {
        if (*text == 0xf2 && ++rows > max_rows) break;
        ++text;
    }
    return text;
}

void script_input(struct investigation *s, int direction, bool confirm, bool back)
{
    if (s->fault != NONE) return;
    if (s->page < s->line_count) {
        if (confirm) {
            const uint8_t *text = script_text + s->lines[s->page].text;
            bool terminal=(s->scene==0x0c01 || s->scene==0x0c02 || s->scene==0x0c05) && *text==0xfe;
            const uint8_t *end = script_page_end(text+s->text_offset,terminal?7:6);
            if (*end != 0xff) {
                s->text_offset = (unsigned)(end-text)+1;
                return;
            }
            s->text_offset = 0;
            ++s->page;
            play_effects(s);
            if (s->fault == NONE && s->page == s->line_count && !s->count) run(s, s->root);
        }
    } else if (s->count) {
        if (back) {
            if (s->selected_count>s->menu_floor) --s->selected_count;
            run(s, s->root);
        }
        else if (confirm) {
            if (!s->in_submenu) s->root_cursor = s->cursor;
            if (s->selected_count >= 16) { s->fault = s->root; return; }
            s->selected[s->selected_count++] = s->choices[s->cursor].text;
            run(s, s->root);
        }
        else if (direction) s->cursor = ((int)s->cursor + direction + s->count) % s->count;
    }
}
