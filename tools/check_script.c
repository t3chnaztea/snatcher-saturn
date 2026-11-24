/* Exercise the same story interpreter as the SH-2, using the compiled CD files.
 * This checks command order and flag-dependent choices. Beetle covers rendering. */
#include "../src/script.h"
#include "../src/disc.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern const uint8_t *script_text;
static struct investigation game;
bool save_exists(unsigned slot) { (void)slot; return false; }
unsigned save_write(unsigned slot,const struct investigation *s) { (void)slot; (void)s; return 0; }
static bool observe;
static unsigned event_index;
static const unsigned presentation[] = {95, 0x10009, 96, 97, 98, 99, 100, 101, 102, 0x20000};

static void fail(const char *reason)
{
    fprintf(stderr, "%s (SP%02u at %u, page %u, fault %u)\n",
            reason, game.module, game.root, game.page, game.fault);
    exit(1);
}

static void event(unsigned value)
{
    if (!observe) return;
    if (event_index >= sizeof(presentation)/sizeof(*presentation) ||
        presentation[event_index++] != value) fail("Unexpected presentation event");
}

bool practice_play(struct practice_score *score) { *score = (struct practice_score){0}; return true; }
bool mika_fight(struct practice_score *score) { (void)score; return true; }
bool office_or_taxi_fight(struct practice_score *score,bool ceiling) { (void)score; (void)ceiling; return false; }
bool ceiling_pan(void) { return true; }
void ceiling_sound(void) {}
bool crawler_fight(struct practice_score *score) { (void)score; return false; }
bool skeleton_fight(struct practice_score *score) { (void)score; return false; }
bool operating_room_actor(unsigned actor) { (void)actor; return false; }
void taxi_sound(void) {}
bool church_portrait_pan(void) { return true; }
bool church_transition(bool opening) { (void)opening; return true; }
void canopy_sound(void) {}
void plaza_use_video_clock(void) {}
void street_close(void) {}
void street_finish_pan(void) {}
bool swarm_fight(struct practice_score *score,unsigned stage) { (void)stage; (void)score; return false; }
bool tunnel_fight(struct practice_score *score) { (void)score; return false; }
bool factory_fight(struct practice_score *score) { (void)score; return false; }
/* These encounters and animations have separate Beetle tests. */
bool apartment_fight(struct practice_score *score) { (void)score; return false; }
bool bathroom_fight(struct practice_score *score) { (void)score; return false; }
bool hostage_fight(struct practice_score *score) { (void)score; return false; }
bool act2_title_fade(void) { return false; }
bool queens_light(bool on) { (void)on; return false; }
unsigned flashlight_target(void) { return 0; }
bool room202_expression(unsigned actor) { (void)actor; return false; }
bool report_start(unsigned actor) { (void)actor; return false; }
bool report_wait(unsigned actor) { (void)actor; return false; }
bool plaza_played(void) { fail("Unexpected plaza animation wait"); return false; }
void scream_sound(void) { fail("Unexpected bathroom sound"); }
bool fm_effect_start(unsigned id) { (void)id; return true; }
void fm_effect_wait(void) {}
bool fm_music_start(unsigned id) { (void)id; return true; }
void fm_music_wait(void) {}
void resident_block(bool blocked) { (void)blocked; }
bool disc_wait_track_sector(unsigned sector) { (void)sector; return false; }
bool music_wait(void) { return true; }
bool music_start(unsigned track) { return track>=2 && track<=21; }
bool scene_draw(unsigned command) { (void)command; return true; }
bool scene_draw_at(unsigned command,unsigned instruction) { (void)instruction; return scene_draw(command); }
bool act3_script_clip(unsigned key) { (void)key; return false; }
bool voice_play(unsigned id) { event(id); return true; }
bool motion_wait(unsigned object) { return object == 17; }
void motion_start(unsigned object, unsigned action) { (void)object; (void)action; }
void scene_wait(unsigned frames) { (void)frames; }
void clear_dialogue(void) {}
void item_hide(void) { event(0x20000); }
bool item_display(unsigned id, unsigned position)
{
    if (position != 5) return false;
    event(0x10000+id);
    return true;
}

static uint32_t read_word(const uint8_t *bytes)
{
    return ((uint32_t)bytes[0]<<24) | ((uint32_t)bytes[1]<<16) |
           ((uint32_t)bytes[2]<<8) | bytes[3];
}

size_t disc_read(const char *name, void *destination, size_t capacity)
{
    char path[64];
    snprintf(path, sizeof(path), "cd/%s", name);
    FILE *file = fopen(path, "rb");
    if (!file) return 0;
    uint8_t *bytes = destination;
    size_t length = fread(bytes, 1, capacity, file);
    bool complete = !ferror(file) && fgetc(file) == EOF;
    fclose(file);
    if (!complete || length < 8) return 0;
    uint32_t sizes[] = {read_word(bytes), read_word(bytes+4)};
    if (sizes[0] > length-8 || sizes[0]%8 || sizes[1] != length-8-sizes[0]) return 0;
    memcpy(bytes, sizes, sizeof(sizes));
    for (size_t offset = 8; offset < 8+sizes[0]; offset += 8) {
        for (unsigned i = 2; i < 8; i += 2) {
            uint8_t *field = bytes+offset+i;
            uint16_t value = (uint16_t)((field[0]<<8) | field[1]);
            memcpy(field, &value, sizeof(value));
        }
    }
    return length;
}

static void advance(void)
{
    if (game.page >= game.line_count) fail("Expected dialogue");
    script_input(&game, 0, true, false);
    if (game.fault != UINT16_MAX) fail("Script stopped");
}

static void finish_dialogue(void)
{
    for (unsigned i = 0; game.page < game.line_count; i++) {
        if (i == 64) fail("Dialogue did not end");
        advance();
    }
}

static unsigned choice(const char *label)
{
    size_t n = strlen(label);
    for (unsigned i = 0; i < game.count; i++) {
        const uint8_t *p = script_text + game.choices[i].text;
        size_t j = 0;
        while (j < n && p[j] == (uint8_t)label[j]) j++;
        if (j == n && p[n] == 255) return i;
    }
    fail(label);
    return 0;
}

static void choose(const char *label)
{
    unsigned index = choice(label);
    if (game.page < game.line_count) fail("Menu obscured by dialogue");
    while (game.cursor != index) script_input(&game, 1, false, false);
    script_input(&game, 0, true, false);
    if (game.fault != UINT16_MAX) fail(label);
}

static void ask(const char *topic)
{
    choose("ASK"); choose(topic); finish_dialogue();
}

int main(void)
{
    script_start(&game);
    if (game.fault != UINT16_MAX) fail("Run tools/build.sh first");
    finish_dialogue();
    choose("ENTER"); finish_dialogue(); choose("TALK");
    ask("ABOUT JUNKERS"); ask("ABOUT NEO KOBE"); ask("ABOUT MIKA");
    choose("ENTER"); finish_dialogue(); choose("CHIEF'S OFFICE");
    ask("ABOUT JUNKERS"); ask("ABOUT JUNKER AUTHORITY");
    ask("ABOUT JUNKER DUTIES"); ask("ABOUT JUNKER STAFF");
    choose("ASK"); observe = true; choose("ABOUT SNATCHERS");
    for (unsigned page = 0; page < 3; page++) {
        if (event_index != 0 || game.page != page) fail("Speech started before reading finished");
        advance();
    }
    if (event_index != sizeof(presentation)/sizeof(*presentation)) fail("Presentation incomplete");
    observe = false;
    choice("POSSESSIONS");
    ask("ABOUT NAVIGATORS");
    const char *verbs[] = {"LOOK", "INVESTIGATE", "SHOW"};
    const char *items[] = {"JUNKER I.D.", "CASH"};
    for (unsigned v = 0; v < 3; ++v) {
        for (unsigned i = 0; i < 2; ++i) {
            choose("POSSESSIONS"); choose(verbs[v]); choose(items[i]);
            finish_dialogue();
            choice("EXIT");
        }
    }
    const char *rooms[] = {"ENGINEERING ROOM", "DETECTIVE'S ROOM", "COMPUTER ROOM", "SHOOTING RANGE"};
    const char *topics[] = {"ABOUT HARRY", "ABOUT KATRINA", "HOW TO USE", "HOW TO PRACTICE"};
    for (unsigned i = 0; i < 4; ++i) {
        choose("EXIT"); finish_dialogue(); choose(rooms[i]); finish_dialogue();
        ask(topics[i]);
    }
    choose("PRACTICE");
    unsigned breaks = 0;
    bool reached_range = false;
    for (unsigned i = 0; i < 24 && game.page < game.line_count; ++i) {
        const uint8_t *text = script_text + game.lines[game.page].text + game.text_offset;
        if (!memcmp(text, "Be careful you don't hit any", 28)) {
            if (!game.text_offset) fail("Missing in-line page break");
            ++breaks;
        }
        if (!memcmp(text, "Good luck!", 10)) {
            reached_range = true;
            break;
        }
        advance();
    }
    if (breaks != 1 || !reached_range) fail("Incomplete practice briefing");
    advance();
    const uint8_t *response = script_text + game.lines[game.page].text;
    if (game.page >= game.line_count || response[0] != 0xfc ||
        memcmp(response+1, "You have to press", 17)) fail("Expected holstered feedback");
    finish_dialogue();
    choice("PRACTICE");
    puts("Chief, inventory, four tour rooms, briefing and practice return verified.");
    return 0;
}

bool oleen_door(void) { return true; }
void plaza_wait_frames(unsigned f) { (void)f; }
bool oleen_waiting_room(void) { return true; }
bool hospital_stair_actor(unsigned actor) { (void)actor; return true; }
bool cockpit_clip(const char *name) { (void)name; return true; }
bool hospital_road_clip(const char *name) { (void)name; return true; }
bool credits_play(void) { return true; }
bool chief_picture(bool repeat) { (void)repeat; return true; }
bool benson_actor(unsigned id) { (void)id; return true; }
bool napoleon_pose(void) { return true; }
bool videophone_movie(const char *file) { (void)file; return true; }
bool apartment_list_actor(unsigned object,unsigned action) { (void)object; (void)action; return true; }
void plaza_apartment_stop(void) {}
void plaza_apartment_voice(unsigned id) { (void)id; }
void plaza_mika_voice(unsigned id) { (void)id; }
