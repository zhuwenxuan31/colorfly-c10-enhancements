#include "feedback.h"
#define NOMINAL (6u<<16)
#define MAX_CORRECTION 393 /* <=1000 ppm of 48kHz, Q16 samples/microframe */
void dac_feedback_reset(dac_feedback *f){*f=(dac_feedback){0};f->q16=NOMINAL;}
void dac_feedback_receive(dac_feedback *f,uint32_t n){f->received+=n;}
static int32_t clamp(int32_t v,int32_t lo,int32_t hi){return v<lo?lo:v>hi?hi:v;}
uint32_t dac_feedback_tick(dac_feedback *f,unsigned running,uint32_t hw,uint32_t boundary,unsigned frame){
 frame&=2047u;
 if(!f->clock_valid){f->last_frame=frame;f->last_hw=hw;f->clock_valid=1;return f->q16;}
 unsigned dt=(frame-f->last_frame)&2047u;
 if(!dt)return f->q16;
 f->last_frame=frame;
 if(!running || dt>100u){
  f->last_hw=hw;f->anchored=0;f->q16=NOMINAL;f->filtered_q8=f->integral=0;
  return f->q16;
 }
 uint32_t delta;
 if(hw>=f->last_hw)delta=hw-f->last_hw;
 else if(boundary>f->last_hw)delta=boundary-f->last_hw+hw;
 else delta=0xffffffffu;
 f->last_hw=hw;
 if(delta>48000u){f->anchored=0;f->consumed=f->received;f->resets++;f->q16=NOMINAL;return f->q16;}
 f->consumed+=delta;
 uint32_t queued=f->received-f->consumed;
 if(!f->anchored){
  f->target=queued;f->anchored=1;f->filtered_q8=f->integral=0;f->q16=NOMINAL;
  return f->q16;
 }
 /* Keep the controller arithmetic bounded even when an upstream fault has
  * made the counters inconsistent. Streaming code stops on a real overflow. */
 int32_t error=clamp((int32_t)(queued-f->target),-32768,32768);
 f->filtered_q8+=(error*256-f->filtered_q8)*(int32_t)dt/256;
 int32_t avg=f->filtered_q8/256;
 int32_t next=clamp(f->integral+avg*(int32_t)dt,-MAX_CORRECTION*2500,MAX_CORRECTION*2500);
 int32_t correction=-4*avg-next/2500;
 /* Anti-windup: do not integrate farther into an already saturated output. */
 if(!((correction< -MAX_CORRECTION && avg>0) || (correction>MAX_CORRECTION && avg<0)))f->integral=next;
 correction=clamp(-4*avg-f->integral/2500,-MAX_CORRECTION,MAX_CORRECTION);
 f->q16=(uint32_t)((int32_t)NOMINAL+correction);return f->q16;
}
void dac_feedback_encode(uint32_t q,unsigned hs,unsigned char b[4]){
 if(!hs)q<<=1; /* Q16 per microframe -> Q14 per 1ms frame */
 for(int i=0;i<4;i++)b[i]=(unsigned char)(q>>(i*8));
 if(!hs)b[3]=0;
}
