#include "descriptors.h"
static void copy(uint8_t *d,const uint8_t *s,unsigned n){for(unsigned i=0;i<n;i++)d[i]=s[i];}
int dac_descriptors_init(dac_descriptors *d,unsigned hs,unsigned ac,unsigned as,unsigned epout,unsigned epin){
 if(hs>1 || ac>255 || as>255 || ac==as || !epout || epout>15 || epin<129 || epin>143)return -1;
 static const uint8_t a[]={9,4,0,0,0,1,1,0,0},h[]={9,0x24,1,0,1,30,0,1,1};
 static const uint8_t in[]={12,0x24,2,1,1,1,0,2,3,0,0,0},out[]={9,0x24,3,3,1,3,0,1,0};
 static const uint8_t z[]={9,4,1,0,0,1,2,0,0},s[]={9,4,1,1,2,1,2,0,0};
 static const uint8_t stream[]={7,0x24,1,1,1,1,0},fmt[]={11,0x24,2,1,2,2,16,1,0x80,0xbb,0};
 static const uint8_t ep[]={9,5,1,5,200,0,4,0,0x81},iso[]={7,0x25,1,0,0,0,0},fb[]={9,5,0x81,0x11,4,0,4,4,0};
 copy(d->ac,a,9);copy(d->header,h,9);copy(d->input,in,12);copy(d->output,out,9);
 copy(d->alt0,z,9);copy(d->alt1,s,9);copy(d->stream,stream,7);copy(d->format,fmt,11);
 copy(d->out,ep,9);copy(d->iso,iso,7);copy(d->feedback,fb,9);
 d->ac[2]=(uint8_t)ac;d->header[8]=(uint8_t)as;d->alt0[2]=d->alt1[2]=(uint8_t)as;
 d->out[2]=(uint8_t)epout;d->out[6]=hs?4:1;d->out[8]=(uint8_t)epin;
 d->feedback[2]=(uint8_t)epin;d->feedback[4]=hs?4:3;d->feedback[6]=hs?4:1;
 const uint8_t *list[]={d->ac,d->header,d->input,d->output,d->alt0,d->alt1,d->stream,d->format,d->out,d->iso,d->feedback,0};
 for(unsigned i=0;i<12;i++)d->list[i]=list[i];return 0;
}
size_t dac_descriptors_flatten(const dac_descriptors *d,uint8_t *out,size_t cap){
 size_t n=9;for(unsigned i=0;d->list[i];i++)n+=d->list[i][0];
 if(n>cap)return 0;
 const uint8_t cfg[]={9,2,(uint8_t)n,(uint8_t)(n>>8),2,1,0,0x80,250};copy(out,cfg,9);
 unsigned pos=9;for(unsigned i=0;d->list[i];i++){unsigned len=d->list[i][0];copy(out+pos,d->list[i],len);pos+=len;}
 return n;
}
