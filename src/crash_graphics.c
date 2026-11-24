#include "crash.h"
#include <string.h>

static unsigned crash_word(const uint8_t *p)
{
    return p[0] | (unsigned)p[1]<<8;
}

/* Genesis Plus GX exposes VRAM in host word order on the build host.
 * Each eight-byte update contains two tile rows. Expand it once so moving
 * sprites and scrolling backgrounds can share the same decoded patterns. */
void crash_decode(const uint8_t *vram,uint8_t *atlas,unsigned offset)
{
    for (unsigned i=0;i<8;i++) {
        unsigned pair=vram[(offset+i)^1];
        atlas[2*(offset+i)]=pair>>4;
        atlas[2*(offset+i)+1]=pair&15;
    }
}

void crash_background(const uint8_t *state,const uint8_t *atlas,uint8_t *out)
{
    const uint8_t *reg=state,*vs=state+160,*vram=state+288;
    static const unsigned sizes[]={32,64,32,128};
    unsigned width=sizes[reg[16]&3],height=sizes[(reg[16]>>4)&3];
    unsigned base[2]={(reg[2]&56)<<10,(reg[4]&7)<<13};
    unsigned hbase=(reg[13]&63)<<10,mode=reg[11]&3;
    memset(out,reg[7]&63,192*128);
    for (int plane=1;plane>=0;plane--) {
        for (unsigned row=0;row<128;row++) {
            unsigned y=row+8,line=mode==3?y:mode==2?(y&~7u):0;
            unsigned scroll=crash_word(vram+((hbase+line*4+plane*2)&65535));
            unsigned col=0;
            while (col<192) {
                unsigned x=col+32,px=(x-scroll)&(8*width-1);
                unsigned voff=(reg[11]&4)?(x/16)*4:0;
                unsigned py=(y+crash_word(vs+voff+plane*2))&(8*height-1);
                unsigned address=base[plane]+2*((py>>3)*width+(px>>3));
                unsigned word=crash_word(vram+(address&65535)),tx=px&7;
                unsigned stop=8-tx;
                if (stop>192-col) stop=192-col;
                if ((reg[11]&4) && stop>16-(x&15)) stop=16-(x&15);
                unsigned ty=(py&7)^((word&4096)?7:0),flip=(word&2048)?7:0;
                const uint8_t *src=atlas+(word&2047)*64+ty*8;
                uint8_t *dst=out+row*192+col;
                unsigned attr=((word>>9)&48) | ((word>>8)&128);
                for (unsigned k=0;k<stop;k++) {
                    unsigned c=src[(tx+k)^flip];
                    if (c && ((attr&128)||!(dst[k]&128))) dst[k]=attr|c;
                }
                col+=stop;
            }
        }
    }
}

/* Walk front to back. An opaque sprite masks later sprites even when a
 * high-priority plane covers that sprite on screen. */
void crash_sprites(const uint8_t *state,const uint8_t *atlas,uint8_t *out)
{
    const uint8_t *vram=state+288;
    const uint8_t *table=vram+((state[5]&127)<<9);
    unsigned si=0;
    for (unsigned count=0;count<80;count++) {
        const uint8_t *entry=table+si*8;
        unsigned link=crash_word(entry+2),word=crash_word(entry+4);
        int sx=(int)(crash_word(entry+6)&511)-160,sy=(int)(crash_word(entry)&511)-136;
        unsigned w=((link>>10)&3)+1,h=((link>>8)&3)+1;
        for (unsigned tx=0;tx<w;tx++) {
            int x=sx+8*(int)tx;
            if (x>=192 || x<=-8) continue;
            unsigned start=x<0?(unsigned)-x:0,stop=x>184?(unsigned)(192-x):8;
            unsigned u=(word&2048)?w-1-tx:tx;
            unsigned flip=(word&2048)?7:0;
            for (unsigned ty=0;ty<h;ty++) {
                int y=sy+8*(int)ty;
                if (y>=128 || y<=-8) continue;
                unsigned v=(word&4096)?h-1-ty:ty;
                const uint8_t *tile=atlas+((word+u*h+v)&2047)*64;
                unsigned top=y<0?(unsigned)-y:0,bottom=y>120?(unsigned)(128-y):8;
                for (unsigned row=top;row<bottom;row++) {
                    const uint8_t *src=tile+8*(row^((word&4096)?7:0));
                    uint8_t *dst=out+((y+(int)row)*192+x+(int)start);
                    for (unsigned k=start;k<stop;k++,dst++) {
                        unsigned c=src[k^flip];
                        if (!c || (*dst&64)) continue;
                        if ((word&32768)||!(*dst&128)) *dst=((word>>9)&48)|c;
                        *dst|=64;
                    }
                }
            }
        }
        si=link&127;
        if (!si || si>=80) break;
    }
}
