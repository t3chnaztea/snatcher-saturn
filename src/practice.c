#include "lightgun.h"
#include "practice.h"
#include <string.h>
#include "range_program.h"

extern void range_sound(unsigned id);
extern void clear_dialogue(void);
extern void scene_tick(void);
extern void scene_wait(unsigned);

struct target {
    unsigned kind, phase, pc, delay, hold;
};
struct practice {
    struct target targets[9];
    struct range_picture picture;
    struct practice_score score;
    uint16_t rng1, rng2;
    unsigned speed, civilians, cooldown, shot_age, required, next_spawn, spawn_phase, spawn_field;
    unsigned attack_ticks, damage_delay, side;
    int shot_field;
};

static unsigned random_field(struct practice *g)
{
    uint32_t a = g->rng1, b = g->rng2;
    a = (a + ((a & 255) << 8) + b + ((b & 255)<<8) + (b>>8)
         + (((b & 255) + (b>>8)) >> 8));
    b = (uint16_t)(b + ((b & 255)<<8));
    g->rng1 = (uint16_t)(a + (b == 65535));
    g->rng2 = (uint16_t)(b+1);
    return field_weights[g->rng1 & 31];
}

static void update_target(struct practice *g, unsigned i)
{
    struct target *t = &g->targets[i];
    if (!t->phase) return;
    const uint8_t (*program)[4] = g->picture.ceiling ? ceiling_target : g->picture.driver ? driver_target : g->picture.final_corridor ? corridor_targets[i] : g->picture.swarm ? swarm_targets[i] : g->picture.tunnel ? tunnel_targets[i] : g->picture.crawler ? crawler_target : g->picture.skeleton ? skeleton_target : g->picture.hostage ? hostage_target : g->picture.lisa ? lisa_targets[t->kind] : g->picture.factory ? factory_targets[i] : t->kind == 1 ? target_26 : target_27;
    const uint8_t *gates = (const uint8_t *)program;
    if (t->phase == 6) {
        t->pc = gates[6]; t->delay = 0; t->phase = 7;
    } else if (t->phase == 7 && t->pc == gates[7]) {
        t->phase = 0;
    } else if (t->phase <= 5) {
        if (t->hold) --t->hold;
        if (t->pc == gates[t->phase] && !t->hold) {
            if ((g->picture.skeleton || g->picture.driver || g->picture.ceiling) && t->phase==4) {
                /* These encounters keep the target active between attacks. */
                t->phase=3;
                t->pc=gates[2]+2;
                t->delay=0;
                t->hold=g->speed+2*random_field(g);
            } else if (t->phase == 5) t->phase = 0;
            else {
                ++t->phase;
                if (g->picture.factory && t->phase==4 && !g->damage_delay && !g->attack_ticks) {
                    if (!g->picture.hostage) range_sound(g->picture.ceiling ? ceiling_attack : g->picture.driver ? driver_attack : g->picture.final_corridor || g->picture.lisa || g->picture.skeleton ? lisa_attack : 47);
                    g->picture.attack_field=i;
                    g->attack_ticks=g->picture.final_corridor ? 18 : g->picture.swarm ? 10 : g->picture.ceiling ? 13 : g->picture.driver ? 7 : g->picture.crawler ? 14 : g->picture.skeleton ? 12 : g->picture.hostage ? 31 : g->picture.lisa ? 15 : 11;
                }
                t->pc += 2;
                t->delay = 0;
                if (t->phase <= 4) t->hold = g->speed + 2*random_field(g);
            }
        }
    }
    if (!t->phase) { g->picture.target[i] = g->picture.factory ? 255 : 7; return; }
    if (!t->delay) {
        if (program[t->pc][0] == 0x81) t->pc = program[t->pc][1];
        if (g->picture.lisa && program[t->pc][0]==0x88) {
            g->picture.pale=!g->picture.pale;
            ++t->pc;
        }
        if ((g->picture.driver || g->picture.crawler || g->picture.ceiling) && (program[t->pc][0]==0x94 || program[t->pc][0]==0x95)) ++t->pc;
        if (g->picture.skeleton && !g->picture.crawler && program[t->pc][0]==0x88) ++t->pc;
        g->picture.target[i] = program[t->pc][0];
        t->delay = program[t->pc][3];
    }
    if (--t->delay == 0) {
        ++t->pc;
        if (program[t->pc][0] == 0x81) t->pc = program[t->pc][1];
    }
}

static void spawn(struct practice *g)
{
    switch (g->spawn_phase) {
    case 0:
        if (g->picture.factory) {
            unsigned active=0;
            for (unsigned i=0; i<9; ++i) active += g->targets[i].phase != 0;
            if (active>=(g->picture.ceiling?ceiling_limit:g->picture.driver?driver_limit:g->picture.final_corridor?corridor_limit:g->picture.swarm?swarm_limit:g->picture.tunnel?tunnel_limit:g->picture.hostage?1:g->picture.lisa?lisa_limit:factory_limit) || g->score.enemies>=g->required) return;
        } else if (g->picture.announced == quota) return;
        if (g->next_spawn) { --g->next_spawn; return; }
        g->next_spawn = 16 + g->speed + 2*random_field(g);
        if (random_field(g) >= 7) g->next_spawn = 5;
        g->spawn_phase = 1;
        break;
    case 1: {
        unsigned field = random_field(g);
        if (g->targets[field].phase || (g->picture.ceiling ? field!=1 : g->picture.driver ? field!=5 : g->picture.crawler ? field!=6 : (g->picture.hostage || g->picture.skeleton) ? field!=1 : g->picture.lisa ? field!=1 && field!=4 : g->picture.final_corridor ? !corridor_targets[field] : g->picture.swarm ? !swarm_targets[field] : g->picture.factory && !g->picture.tunnel && !factory_targets[field])) return;
        unsigned kind = g->picture.factory ? 1 : kind_table[random_field(g)&3];
        if (g->picture.lisa) {
            kind=g->side+(field<3);
            g->side^=2;
            g->picture.resting_pose=g->side?16:5;
        }
        g->targets[field] = (struct target){.kind=kind, .pc=g->picture.driver ? driver_target[0][0]+2 : g->picture.crawler ? crawler_target[0][0]+2 : g->picture.factory && !g->picture.hostage ? 2 : 5};
        g->spawn_field = field;
        if (!g->picture.lisa && kind == 2) ++g->civilians;
        else ++g->picture.announced;
        g->spawn_phase = 2;
        break;
    }
    case 2:
        g->targets[g->spawn_field].phase = 1;
        g->spawn_phase = 0;
        break;
    }
}

/* The three central hostage positions and the two side positions carry
 * the damage bit in the retail field table. Side targets also count as hits. */
static const uint8_t mika_kind[9]={1,2,1,3,2,3,1,2,1};
extern unsigned mika_phase_length(unsigned field,unsigned phase);

static void mika_target_tick(struct practice *g)
{
    unsigned i=g->spawn_field;
    struct target *t=&g->targets[i];
    if (!t->phase) {
        if (g->next_spawn) { --g->next_spawn; return; }
        i=g->picture.announced ? random_field(g) : 8;
        g->spawn_field=i;
        t=&g->targets[i];
        *t=(struct target){.phase=1,.kind=mika_kind[i]};
        ++g->picture.announced;
    }
    g->picture.target[i]=t->pc++;
    if (t->phase==4 && !t->delay && (t->kind&1)) {
        range_sound(mika_attack);
        g->attack_ticks=11;
    }
    if (++t->delay==mika_phase_length(i,t->phase)) {
        t->delay=0;
        if (++t->phase==6) {
            t->phase=0;
            g->next_spawn=3+2*random_field(g);
        }
    }
}

static void mika_fire(struct practice *g,int field)
{
    struct target *t=&g->targets[field];
    unsigned kind=mika_kind[field];
    if (t->phase>=2 && t->phase<=4) {
        if (kind&1) {
            ++g->score.enemies;
            g->picture.enemies=g->score.enemies;
            range_sound(mika_hit);
        } else ++g->score.civilians;
        t->phase=0;
        g->picture.target[field]=255;
        g->next_spawn=24+2*random_field(g);
    }
    if (kind&2) {
        range_sound(50);
        ++g->score.damage;
        g->picture.damage=g->score.damage;
    } else ++g->score.misses; /* Original $790E also counts safe hits. */
}

static void fire(struct practice *g, int field)
{
    struct target *t = &g->targets[field];
    if (t->phase < 2 || t->phase > 4) {
        ++g->score.misses;
        if (!g->picture.factory && g->speed < 32) ++g->speed;
        return;
    }
    t->phase = 6;
    if (!g->picture.lisa && t->kind == 2) {
        range_sound(14);
        ++g->score.civilians;
        if (g->speed >= 2) g->speed -= 2;
    } else {
        range_sound(g->picture.ceiling ? ceiling_hit : g->picture.driver ? driver_hit : g->picture.final_corridor || g->picture.lisa || g->picture.hostage || g->picture.skeleton ? lisa_hit : g->picture.apartment ? ivan_hit : g->picture.factory ? 45 : 13);
        ++g->score.enemies;
        g->picture.enemies = g->score.enemies;
        if (!(g->score.enemies % 8) && g->speed >= 2) g->speed -= 2;
    }
}

/* Sequence 3 exposes one target in the center field. It stays in the
 * doorway after firing. The player can still return fire after taking damage. */
static void apartment_target(struct practice *g)
{
    struct target *t=&g->targets[4];
    unsigned phase=t->phase;
    const uint8_t *gates=(const uint8_t *)ivan_target;
    if (t->delay && --t->delay) return;
    if (phase==0) { t->phase=1; t->delay=ivan_target[2][3]; return; }
    if (phase<=2) {
        ++t->phase;
        g->picture.target[4]=ivan_target[gates[t->phase-1]][0];
        t->delay=ivan_target[gates[t->phase-1]][3]+random_field(g);
        return;
    }
    if (phase==3) {
        t->phase=4;
        g->picture.target[4]=ivan_target[gates[3]][0];
        t->delay=ivan_target[gates[3]][3]+2*random_field(g);
        if (!g->damage_delay && !g->attack_ticks) {
            range_sound(ivan_attack);
            g->attack_ticks=5;
        }
    } else if (phase==4) {
        t->phase=3;
        g->picture.target[4]=ivan_target[gates[2]][0];
        t->delay=ivan_target[gates[2]][3]+random_field(g);
    }
}

static bool encounter(struct practice_score *score, unsigned stage)
{
    bool factory=stage!=0, apartment=stage==3, lisa=stage==2, hostage=stage==4, skeleton=stage==5 || stage==6, crawler=stage==6;
    struct practice g = {.speed=crawler ? crawler_speed : skeleton ? skeleton_speed : hostage ? hostage_speed : lisa ? lisa_speed : factory ? factory_speed : initial_speed,
                         .next_spawn=crawler ? crawler_delay : skeleton ? skeleton_delay : hostage ? hostage_delay : lisa ? lisa_delay : factory ? factory_delay : first_delay, .shot_field=-1};
    if (stage==10) {
        g.picture.mika=true;
        g.speed=0;
        g.next_spawn=mika_delay;
    }
    if (stage==9) {
        g.picture.ceiling=true;
        g.speed=ceiling_speed;
        g.next_spawn=ceiling_delay;
    }
    if (stage==12 || stage==13) {
        g.picture.final_corridor=stage==13;
        g.picture.swarm=true;
        g.speed=g.picture.final_corridor ? corridor_speed : swarm_speed;
        g.next_spawn=g.picture.final_corridor ? corridor_delay : swarm_delay;
    }
    if (stage==8) {
        g.picture.tunnel=true;
        g.speed=tunnel_speed;
        g.next_spawn=tunnel_delay;
    }
    if (stage==7) {
        g.picture.driver=true;
        g.speed=driver_speed;
        g.next_spawn=driver_delay;
    }
    g.picture.factory=factory;
    g.picture.apartment=apartment;
    g.picture.hostage=hostage;
    g.picture.skeleton=skeleton;
    g.picture.crawler=crawler;
    g.required=g.picture.mika?mika_quota:g.picture.ceiling?ceiling_quota:g.picture.driver?driver_quota:g.picture.final_corridor?corridor_quota:g.picture.swarm?swarm_quota:g.picture.tunnel?tunnel_quota:crawler?crawler_quota:skeleton?skeleton_quota:hostage?hostage_quota:lisa?lisa_quota:apartment?ivan_quota:factory_quota;
    g.picture.lisa=lisa;
    g.picture.resting_pose=5;
    if (apartment) { g.targets[4].delay=6; g.speed=0; }
    memset(g.picture.target, factory ? 255 : 7, sizeof(g.picture.target));
    g.picture.aim = g.picture.flash_field = g.picture.attack_field = -1;
    clear_dialogue();
    range_present(NULL);
    range_present(&g.picture);
    lightgun_begin();
    bool drawn = false;
    for (unsigned frame = 0;; ++frame) {
        bool toggle, trigger;
        int field;
        range_pad(&toggle, &trigger, &field);
        if (factory || frame >= 128) {
            g.picture.sign = 1;
            if (toggle) {
                drawn = !drawn;
                if (drawn) { g.score.drawn = 1; range_sound(g.picture.mika ? mika_draw : g.picture.ceiling ? ceiling_draw : g.picture.driver ? driver_draw : g.picture.final_corridor || lisa || hostage || skeleton ? lisa_draw : apartment ? ivan_draw : factory ? 48 : 15); }
            }
            int optical_field;
            bool optical=lightgun_shot(&optical_field);
            if (optical) {
                if (g.picture.mika && !g.score.drawn) g.required=mika_gun_quota;
                if (g.picture.ceiling && !g.score.drawn) g.required=ceiling_gun_quota;
                if (g.picture.driver && !g.score.drawn) g.required=driver_gun_quota;
                if (g.picture.swarm && !g.score.drawn) g.required=g.picture.final_corridor ? corridor_gun_quota : swarm_gun_quota;
                if (g.picture.tunnel && !g.score.drawn) g.required=tunnel_gun_quota;
                if (lisa && !g.score.drawn) g.required=lisa_gun_quota;
                if (!drawn) {
                    drawn=true;
                    g.score.drawn=1;
                    range_sound(g.picture.mika ? mika_draw : g.picture.ceiling ? ceiling_draw : g.picture.driver ? driver_draw : g.picture.final_corridor || lisa || hostage || skeleton ? lisa_draw : apartment ? ivan_draw : factory ? 48 : 15);
                }
                field=optical_field;
                trigger=true;
            }
            g.picture.aim = drawn ? field : -1;
            if (g.cooldown) --g.cooldown;
            if (trigger && !toggle && drawn && !g.cooldown) {
                g.shot_field = field<0 ? -2 : field; g.shot_age = 0; g.cooldown = 10;
                ++g.score.shots;
            }
            g.picture.flash_field = -1;
            if (g.shot_field != -1) {
                ++g.shot_age;
                if (g.shot_age == 3) range_sound(g.picture.mika ? mika_shot : g.picture.ceiling ? ceiling_shot : g.picture.driver ? driver_shot : g.picture.final_corridor || lisa || hostage || skeleton ? lisa_shot : apartment ? ivan_shot : factory ? 46 : 16);
                if (g.shot_age >= 3 && g.shot_field>=0) {
                    g.picture.flash_field = g.shot_field;
                    g.picture.flash_frame = g.shot_age-3;
                }
                if (g.shot_age == 7) {
                    if (g.shot_field<0) ++g.score.misses;
                    else if (g.picture.mika) mika_fire(&g,g.shot_field);
                    else fire(&g,g.shot_field);
                    g.shot_field = -1;
                }
            }
            bool active = false;
            if (g.picture.mika) {
                if (!g.targets[g.spawn_field].phase) g.picture.target[g.spawn_field]=255;
                mika_target_tick(&g);
            } else if (apartment) apartment_target(&g);
            else for (unsigned i = 0; i < 9; ++i) {
                update_target(&g,i);
                if (g.targets[i].phase) active = true;
            }
            if (lisa && !(frame&1)) {
                if (g.picture.pale && g.picture.light<7) ++g.picture.light;
                if (!g.picture.pale && g.picture.light) --g.picture.light;
            }
            if (g.damage_delay) --g.damage_delay;
            if (g.attack_ticks) {
                static const uint8_t attack_frames[]={28,29,30,31,31,32,32,33,33,34,34};
                if (g.picture.ceiling) {
                    static const uint8_t frames[]={12,12,12,13,13,13,14,14,15,15,16,16,17};
                    g.picture.attack_frame=frames[13-g.attack_ticks];
                } else if (g.picture.driver) {
                    static const uint8_t frames[]={7,7,8,8,9,10,11};
                    g.picture.attack_frame=frames[7-g.attack_ticks];
                } else if (crawler) g.picture.attack_frame=9+(14-g.attack_ticks)/2;
                else if (skeleton) g.picture.attack_frame=1+(12-g.attack_ticks)/2;
                else if (lisa) {
                    static const uint8_t frames[]={6,6,6,6,6,6,6,7,7,7,8,8,8,9,10};
                    g.picture.attack_frame=frames[15-g.attack_ticks];
                } else if (g.picture.final_corridor) {
                    static const uint8_t frames[]={6,6,6,6,7,7,7,7,8,8,8,9,9,9,10,10,11,11};
                    g.picture.attack_frame=frames[18-g.attack_ticks];
                } else if (g.picture.swarm) {
                    static const uint8_t frames[]={42,43,44,45,45,46,46,47,47,48};
                    g.picture.attack_frame=frames[10-g.attack_ticks];
                } else if (!hostage && !g.picture.mika) g.picture.attack_frame=attack_frames[11-g.attack_ticks];
            }
            if (g.attack_ticks && !--g.attack_ticks) {
                g.picture.attack_field=-1;
                if (hostage) range_sound(52);
                ++g.score.damage;
                g.picture.damage=g.score.damage;
                g.damage_delay=28+24+g.speed/4;
            }
            if (factory && ((g.score.enemies>=g.required && ((!hostage && !lisa && !skeleton) || !active)) || g.score.damage>=factory_health)) break;
            if (!apartment && !g.picture.mika) spawn(&g);
            if (!factory && !g.spawn_phase && g.picture.announced == quota && !active && g.shot_field < 0) break;
        }
        scene_tick();
        range_present(&g.picture);
        scene_wait(1);
    }
    g.picture.aim = g.picture.flash_field = g.picture.attack_field = -1;
    if (factory) memset(g.picture.target,255,sizeof(g.picture.target));
    lightgun_end();
    if (apartment && g.score.enemies) {
        g.picture.target[4]=ivan_target[((const uint8_t *)ivan_target)[6]][0];
        range_present(&g.picture);
        scene_wait(20);
    }
    g.picture.sign = 2;
    range_present(&g.picture);
    scene_wait(64);
    g.score.all_civilians = g.civilians > 0 && g.score.civilians == g.civilians;
    *score = g.score;
    return true;
}

bool mika_fight(struct practice_score *score)
{
    extern bool mika_prepare(void);
    return mika_prepare() && encounter(score,10);
}

bool practice_play(struct practice_score *score)
{
    return encounter(score,0);
}

bool office_or_taxi_fight(struct practice_score *score,bool ceiling)
{
    extern bool office_or_taxi_prepare(bool);
    return office_or_taxi_prepare(ceiling) && encounter(score,ceiling?9:7);
}

bool swarm_fight(struct practice_score *score,unsigned stage)
{
    extern bool swarm_prepare(unsigned);
    if (!swarm_prepare(stage)) return false;
    if (stage!=14) return encounter(score,stage);

    struct range_picture picture={.factory=true,.swarm=true,.sign=1,
                                  .aim=-1,.flash_field=-1,.attack_field=-1};
    memset(picture.target,255,sizeof(picture.target));
    *score=(struct practice_score){0};
    clear_dialogue();
    range_present(NULL);
    lightgun_begin();
    bool drawn=false;
    /* SUBCODE 123E8 advances the final encounter until timer 0100. */
    for (unsigned ticks=0;ticks<256;++ticks) {
        bool toggle,fire;
        int field,optical;
        range_pad(&toggle,&fire,&field);
        if (toggle) {
            drawn=!drawn;
            if (drawn) { score->drawn=1; range_sound(73); }
        }
        if (lightgun_shot(&optical)) {
            if (!drawn) { drawn=true; score->drawn=1; range_sound(73); }
            fire=true;
            field=optical;
        }
        picture.aim=drawn ? field : -1;
        if (drawn && fire && !toggle) {
            /* The native shot handler sets 790C before SP37 checks its branch. */
            score->shots=score->civilians=1;
            range_sound(72);
            picture.flash_field=field;
            picture.flash_frame=0;
            range_present(&picture);
            scene_wait(1);
            break;
        }
        range_present(&picture);
        scene_wait(1);
    }
    lightgun_end();
    picture.aim=picture.flash_field=-1;
    picture.sign=2;
    range_present(&picture);
    return true;
}

bool tunnel_fight(struct practice_score *score)
{
    return encounter(score,8);
}

bool factory_fight(struct practice_score *score)
{
    return encounter(score,1);
}

bool bathroom_fight(struct practice_score *score)
{
    return encounter(score,2);
}

bool crawler_fight(struct practice_score *score)
{
    extern bool crawler_prepare(void);
    return crawler_prepare() && encounter(score,6);
}

bool skeleton_fight(struct practice_score *score)
{
    return encounter(score,5);
}

bool hostage_fight(struct practice_score *score)
{
    return encounter(score,4);
}

bool apartment_fight(struct practice_score *score)
{
    return encounter(score,3);
}
