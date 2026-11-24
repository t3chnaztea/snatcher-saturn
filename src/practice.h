#ifndef SNATCHER_PRACTICE_H
#define SNATCHER_PRACTICE_H
#include <stdbool.h>
#include <stdint.h>

struct practice_score {
    uint16_t shots, enemies, civilians, misses, damage, all_civilians, drawn;
};
struct range_picture {
    uint8_t target[9], announced, enemies, sign, damage;
    bool factory, apartment, lisa, pale, hostage, skeleton, crawler, tunnel, swarm, final_corridor, driver, ceiling, mika;
    unsigned resting_pose, light;
    int aim, flash_field, flash_frame, attack_field, attack_frame;
};
bool mika_fight(struct practice_score *score);
bool office_or_taxi_fight(struct practice_score *score,bool ceiling);
bool swarm_fight(struct practice_score *score,unsigned stage);
bool tunnel_fight(struct practice_score *score);
bool crawler_fight(struct practice_score *score);
bool skeleton_fight(struct practice_score *score);
bool hostage_fight(struct practice_score *score);
bool bathroom_fight(struct practice_score *score);
bool apartment_fight(struct practice_score *score);
bool factory_fight(struct practice_score *score);
bool practice_play(struct practice_score *score);
void range_present(const struct range_picture *picture);
void range_pad(bool *draw, bool *fire, int *field);
#endif
