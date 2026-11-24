#ifndef SNATCHER_SCRIPT_H
#define SNATCHER_SCRIPT_H
#include <stdbool.h>
#include "practice.h"
#include <stdint.h>

enum { MAX_CHOICES = 24, MAX_LINES = 32 };
struct choice { uint16_t text, body; };
struct line { uint16_t speaker, text; };
struct investigation {
    struct choice choices[MAX_CHOICES];
    struct line lines[MAX_LINES];
    struct { uint16_t pos, page; } effects[128];
    unsigned effect_count, effect_index;
    unsigned count, line_count, page, text_offset, cursor, root_cursor;
    bool in_submenu, sentence_done;
    unsigned selected_count, selected_pos, menu_floor;
    uint8_t menu_parents[16], menu_depth;
    uint16_t selected[16];
    uint16_t previous_roots[3], callers[16], current_routine;
    unsigned previous_count, caller_count;
    uint16_t module, next_module, root, jump, fault;
    uint16_t scene, return_scene, return_module, return_root, return_history[3];
    unsigned return_depth, save_result;
    bool saved_call, finished, phone_keypad;
    uint8_t phone_cursor, dial_length, dial_digits[10];
    bool password_input, numeric_answer;
    uint8_t password_length, password_limit, password[13];
    uint8_t flags[354];
    uint32_t random;
    struct practice_score practice;
};
const uint8_t *script_page_end(const uint8_t *text,unsigned max_rows);
unsigned script_audio_level(unsigned level);
void script_start(struct investigation *s);
void script_input(struct investigation *s, int direction, bool confirm, bool back);
void script_dial(struct investigation *, int horizontal, int vertical, bool confirm, bool erase);
void script_password(struct investigation *,int horizontal,int vertical,bool confirm,bool erase,bool submit);
unsigned password_key_x(unsigned key);
void panel_draw(const struct investigation *s, volatile uint16_t *screen, unsigned stride);
#endif
