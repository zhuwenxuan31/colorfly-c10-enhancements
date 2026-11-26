#include "feedback.h"
#include <assert.h>
#include <stdio.h>
#include <math.h>
static void simulate(int ppm,int period){
 unsigned prefill=(unsigned)period*2;if(prefill<2048)prefill=2048;if(prefill>8192)prefill=8192;
 dac_feedback f;dac_feedback_reset(&f);dac_feedback_receive(&f,prefill);
 double tx=0,play=0;unsigned rx=prefill,played=0;int min=20000,max=0;uint64_t sumq=0;
 for(unsigned ms=0;ms<1800000;ms++){
  tx+=(double)f.q16/8192.;unsigned n=(unsigned)tx;tx-=n;rx+=n;dac_feedback_receive(&f,n);
  play+=48.*(1.+ppm/1000000.);n=(unsigned)play;play-=n;played+=n;
  uint32_t hw=(played/(unsigned)period*(unsigned)period)%(1u<<20);
  uint32_t q=dac_feedback_tick(&f,1,hw,1u<<20,ms&2047);
  assert(q>=(6u<<16)-393 && q<=(6u<<16)+393);
  if(ms>=1740000)sumq+=q;
  int fill=(int)(rx-played);if(fill<min)min=fill;if(fill>max)max=fill;
  if(fill<0||fill>20000){fprintf(stderr,"unstable ppm=%d period=%d ms=%u fill=%d\n",ppm,period,ms,fill);assert(0);}
 }
 double measured=((double)sumq/60000./65536./6.-1.)*1000000.;
 printf("ppm=%d period=%d final=%.2f min=%d max=%d\n",ppm,period,measured,min,max);
 assert(min>256&&max<16384);assert(fabs(measured-ppm)<20);
}
int main(void){
 dac_feedback f;dac_feedback_reset(&f);unsigned char b[4];
 dac_feedback_encode(f.q16,1,b);assert(b[0]==0&&b[1]==0&&b[2]==6&&b[3]==0);
 dac_feedback_encode(f.q16,0,b);assert(b[0]==0&&b[1]==0&&b[2]==12&&b[3]==0);
 for(int i=0;i<4;i++)simulate((int[]){-500,-50,50,500}[i],256);
 simulate(200,2048);simulate(500,8192);simulate(-500,8192);
 dac_feedback_reset(&f);f.received=0xfffffff0u;dac_feedback_receive(&f,48);assert(f.received==32);
 puts("PASS feedback nominal/FS/HS/7x30min drift/DMA jitter/frame+hw+rx wraps");
}
