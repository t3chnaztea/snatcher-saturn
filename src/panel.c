#include "script.h"
#include <string.h>
extern const uint8_t script_font[], speaker_names[];
extern const uint8_t *script_text;

static void draw_text(volatile uint16_t *screen, unsigned stride, unsigned x, unsigned y,
                      const uint8_t *text, uint16_t color)
{
    unsigned left = x;
    const uint16_t normal_color = color;
    const uint8_t *end = script_page_end(text,y==72 ? 7 : 6);
    while (text < end && y + 7 < 224) {
        unsigned ch = *text++;
        if (ch == 0xf2) { x = left; y += 9; continue; }
        if (ch == 0xec || ch == 0xee || ch == 0xf0) ch = 'A' + (ch-0xec)/2;
        if (ch == 0xfc) { color = 0xffe0; continue; }
        if (ch == 0xfa) { color = 0x83ff; continue; }
        if (ch == 0xfb) { color = 0x8000 | (17 << 10) | (13 << 5) | 31; continue; }
        if (ch == 0xf9) { color = normal_color; continue; }
        if (ch < 32 || ch >= 134) continue;
        unsigned glyph = ch - 32;
        if (x + 8 <= 256) {
            for (unsigned row = 0; row < 8; row++) {
                unsigned bits = script_font[glyph * 8 + row];
                for (unsigned col = 0; col < 8; col++)
                    if (bits & (128 >> col)) screen[(y + row)*stride + x + col] = color;
            }
        }
        x += script_font[816 + glyph];
    }
}

static void dial_glyph(volatile uint16_t *screen,unsigned stride,unsigned x,unsigned y,
                       uint8_t ch,uint16_t color)
{
    const uint8_t text[]={ch,0xff};
    draw_text(screen,stride,x,y,text,color);
}

static void dial_panel(const struct investigation *s,volatile uint16_t *screen,unsigned stride)
{
    static const uint8_t keys[]="123456789*0#";
    for (unsigned i=0; i<12; ++i) {
        unsigned x=200+(i%3)*16,y=152+(i/3)*16;
        if (i==s->phone_cursor)
            for (unsigned dy=0; dy<9; ++dy)
                for (unsigned dx=0; dx<9; ++dx) screen[(y-1+dy)*stride+x+dx]=0xffff;
        dial_glyph(screen,stride,x+1+(8-script_font[816+keys[i]-32])/2,y,keys[i],0xfe31);
    }
    if (s->password_input) {
        for (unsigned i=0; i<s->password_limit; ++i) {
            if (i<s->password_length) dial_glyph(screen,stride,64+9*i,168,s->password[i],0xffff);
            if (i!=s->password_length) dial_glyph(screen,stride,64+9*i,177,'_',0xffff);
        }
        return;
    }
    for (unsigned i=0; i<10; ++i) {
        if (i<s->dial_length) dial_glyph(screen,stride,24+9*i,168,s->dial_digits[i],0xffff);
        if (i!=s->dial_length) dial_glyph(screen,stride,24+9*i,177,'_',0xffff);
    }
}

#include "keyboard_art.h"
static uint16_t password_list_background[18][120];
static bool password_list_saved;

void password_list_restore(volatile uint16_t *screen,unsigned stride)
{
    if (!password_list_saved) return;
    for (unsigned y=0;y<18;y++) memcpy((void *)(screen+(99+y)*stride+56),password_list_background[y],240);
    password_list_saved=false;
}

static void password_panel(const struct investigation *s,volatile uint16_t *screen,unsigned stride)
{
    if (s->module==28 && !password_list_saved) {
        for (unsigned y=0;y<18;y++) memcpy(password_list_background[y],(const void *)(screen+(99+y)*stride+56),240);
        password_list_saved=true;
    }
    unsigned key=s->phone_cursor;
    unsigned cx=password_key_x(key),cy=164+16*(key/13);
    unsigned radius=key<29?5:18;
    for (unsigned y=0; y<72; ++y) {
        for (unsigned x=0; x<256; ++x) {
            uint8_t pair=keyboard_pixels[y*128+x/2];
            unsigned index=(pair>>(x%2?0:4))&15;
            bool selected=index==0 && x>=cx-radius && x<cx+radius &&
                          144+y>=cy && 144+y<cy+7;
            screen[(144+y)*stride+x]=selected?0xffff:keyboard_colors[index];
        }
    }
    for (unsigned y=99; y<117; ++y)
        for (unsigned x=56; x<176; ++x) screen[y*stride+x]=0x8000;
    for (unsigned i=0; i<s->password_limit; ++i) {
        unsigned x=64+i*9;
        if (i<s->password_length) {
            unsigned ch=s->password[i], width=script_font[816+ch-32];
            dial_glyph(screen,stride,x+(width<8?(8-width)/2:0),104,ch,0xffff);
        }
        for (unsigned dx=1; dx<=6; ++dx) screen[113*stride+x+dx]=0xffff;
    }
}

/* Jordan prints terminal messages into the monitor. Restore its pixels
 * before the next input can change scenes or show a different page. */
static bool terminal_page_visible;
static uint16_t terminal_background[7*9][168];
void terminal_page_clear(volatile uint16_t *screen,unsigned stride)
{
    if (!terminal_page_visible) return;
    for (unsigned y=0;y<7*9;y++)
        for (unsigned x=0;x<168;x++) screen[(72+y)*stride+40+x]=terminal_background[y][x];
    terminal_page_visible=false;
}

void panel_draw(const struct investigation *s, volatile uint16_t *screen, unsigned stride)
{
    const uint16_t white = 0xffff, cyan = 0xffe0, yellow = 0x83ff;
    unsigned offset=s->scene==0x070e ? 25 : 0;
    for (unsigned y = 142+offset; y < 224; y++)
        for (unsigned x = 0; x < 256; x++) screen[y*stride+x] = 0x8000;
    if (s->fault != UINT16_MAX) {
        uint8_t message[] = "SCRIPT OFFSET 0000\xff";
        const char hex[] = "0123456789ABCDEF";
        for (unsigned i = 0; i < 4; i++) message[14+i] = hex[(s->fault >> (12-4*i)) & 15];
        draw_text(screen, stride, 16, 144, message, white);
    } else if (s->page < s->line_count) {
        struct line line = s->lines[s->page];
        if ((s->scene==0x0c01 || s->scene==0x0c02 || s->scene==0x0c05)
                && script_text[line.text]==0xfe) {
            for (unsigned y=0;y<7*9;y++)
                for (unsigned x=0;x<168;x++)
                    terminal_background[y][x]=screen[(72+y)*stride+40+x];
            terminal_page_visible=true;
            draw_text(screen,stride,40,72,script_text+line.text+s->text_offset,0xa3e0);
            return;
        }
        if (line.speaker && line.speaker <= 48)
            draw_text(screen, stride, 16, 144+offset, speaker_names+(line.speaker-1)*24, yellow);
        draw_text(screen, stride, 24, 153+offset, script_text+line.text+s->text_offset, white);
    } else if (s->password_input) {
        if (s->numeric_answer) dial_panel(s,screen,stride);
        else password_panel(s,screen,stride);
    } else if (s->phone_keypad) {
        dial_panel(s,screen,stride);
    } else {
        unsigned first = s->cursor >= 8 ? s->cursor - 7 : 0;
        for (unsigned i = first; i < s->count && i < first+8; i++) {
            unsigned y = 144+(i-first)*9;
            if (i == s->cursor) {
                for (unsigned row = y-1; row < y+8; row++)
                    for (unsigned x = 16; x < 240; x++) screen[row*stride+x] = 0xfd04;
            }
            draw_text(screen, stride, 16, y, script_text+s->choices[i].text,
                      i == s->cursor ? white : cyan);
        }
    }
}

void panel_slots(volatile uint16_t *screen,unsigned stride,unsigned occupied,unsigned cursor)
{
    for (unsigned y=142;y<224;y++)
        for (unsigned x=16;x<240;x++) screen[y*stride+x]=0x8000;
    draw_text(screen,stride,16,144,(const uint8_t *)"LOAD GAME\xff",0x83ff);
    for (unsigned i=0;i<4;i++) {
        unsigned y=155+9*i;
        if (i==cursor)
            for (unsigned row=y-1;row<y+8;row++)
                for (unsigned x=16;x<240;x++) screen[row*stride+x]=0xfd04;
        uint8_t label[]="SAVE 1\xff";
        label[5]+=(uint8_t)i;
        draw_text(screen,stride,20,y,label,occupied&(1u<<i) ? 0xffff : 0xad6b);
    }
}
