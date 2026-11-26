#include "eq_model.h"
static const int curves[5][EQ_BANDS] = {
    {0,0,0,0,0,0,0,0,0,0},
    {0,0,-1,-3,-4,-4,-3,-3,-3,-3},
    {-4,-4,-3,-2,-1,0,0,-2,-3,-4},
    {-4,-3,-3,-2,-2,-1,0,0,0,-1},
    {0,0,0,0,-1,-2,-3,-4,-4,-5}
};
void eq_default(eq_config *c) {
    c->enabled=0;c->preset=0;
    for(int i=0;i<EQ_BANDS;i++)c->gain[i]=0;
}
int eq_valid(const eq_config *c) {
    if(c->enabled<0 || c->enabled>1 || c->preset<0 || c->preset>=EQ_PRESETS)return 0;
    for(int i=0;i<EQ_BANDS;i++)if(c->gain[i]<-12 || c->gain[i]>12)return 0;
    return 1;
}
int eq_set_preset(eq_config *c,int n) {
    if(n<0 || n>=EQ_PRESETS)return -1;
    c->preset=n;
    if(n<5)for(int i=0;i<EQ_BANDS;i++)c->gain[i]=curves[n][i];
    return 0;
}
int eq_adjust(eq_config *c,int n,int d) {
    if(n<0 || n>=EQ_BANDS || (d!=1 && d!=-1) || !eq_valid(c))return -1;
    int v=c->gain[n]+d;
    if(v>12)v=12;
    if(v< -12)v= -12;
    c->gain[n]=v;c->preset=5;
    return 0;
}
int eq_headroom(const eq_config *c) {
    int sum=0;
    for(int i=0;i<EQ_BANDS;i++)if(c->gain[i]>0)sum+=c->gain[i];
    return sum ? sum+3 : 0;
}
int eq_volume_tenths(const eq_config *c) {
    /* Rounded toward more attenuation. Compensate THIS factory equalizer's
     * gain_factor=.1+maxboost/12, then reserve conservative digital headroom.
     * Volume must be AFTER EQ so it operates in float, not premature S16.
     */
    static const int native_db_tenths_ceil[13]={0,-147,-114,-91,-72,-57,-44,-33,-23,-14,-5,2,9};
    int max=0;
    for(int i=0;i<EQ_BANDS;i++)if(c->gain[i]>max)max=c->gain[i];
    return -10*eq_headroom(c)-native_db_tenths_ceil[max];
}
typedef struct { char *p;size_t cap,len;int failed; } buffer;
static void put(buffer *b,char c) {
    if(b->len+1>=b->cap){b->failed=1;return;}
    b->p[b->len++]=c;
}
static void text(buffer *b,const char *s){while(*s)put(b,*s++);}
static void number(buffer *b,int v) {
    char temp[12];int n=0;
    if(v<0){put(b,'-');v=-v;}
    do{temp[n++]=(char)('0'+v%10);v/=10;}while(v);
    while(n)put(b,temp[--n]);
}
int eq_options(const eq_config *c,char *out,size_t cap) {
    if(!eq_valid(c) || !cap)return -1;
    out[0]=0;
    if(!c->enabled)return 0;
    buffer b={out,cap,0,0};
    text(&b," -af-add equalizer=");
    for(int i=0;i<EQ_BANDS;i++){if(i)put(&b,':');number(&b,c->gain[i]);}
    text(&b,",volume=");
    int v=eq_volume_tenths(c);
    if(v<0){put(&b,'-');v=-v;}
    number(&b,v/10);put(&b,'.');put(&b,(char)('0'+v%10));text(&b,":0:0");
    out[b.len]=0;
    return b.failed ? -1 : (int)b.len;
}
static uint32_t checksum(const unsigned char *p,size_t n) {
    uint32_t crc=0xffffffffu;
    for(size_t i=0;i<n;i++){
        crc^=p[i];
        for(int j=0;j<8;j++)crc=(crc>>1)^((0u-(crc&1u))&0xedb88320u);
    }
    return crc^0xffffffffu;
}
void eq_encode(const eq_config *c,unsigned char b[EQ_RECORD_SIZE]) {
    static const unsigned char magic[8]={'C','1','0','E','Q','0','0','1'};
    for(int i=0;i<EQ_RECORD_SIZE;i++)b[i]=0;
    for(int i=0;i<8;i++)b[i]=magic[i];
    b[8]=(unsigned char)c->enabled;b[9]=(unsigned char)c->preset;
    for(int i=0;i<EQ_BANDS;i++)b[12+i]=(unsigned char)c->gain[i];
    uint32_t crc=checksum(b,60);
    for(int i=0;i<4;i++)b[60+i]=(unsigned char)(crc>>(i*8));
}
int eq_decode(eq_config *c,const unsigned char *b,size_t n) {
    eq_default(c);
    if(n!=EQ_RECORD_SIZE)return -1;
    static const unsigned char magic[8]={'C','1','0','E','Q','0','0','1'};
    for(int i=0;i<8;i++)if(b[i]!=magic[i])return -1;
    uint32_t wanted=0;
    for(int i=0;i<4;i++)wanted|=(uint32_t)b[60+i]<<(i*8);
    if(wanted!=checksum(b,60) || b[10] || b[11])return -1;
    for(int i=22;i<60;i++)if(b[i])return -1;
    eq_config temp;
    temp.enabled=b[8];temp.preset=b[9];
    for(int i=0;i<EQ_BANDS;i++)temp.gain[i]=b[12+i]<128 ? b[12+i] : (int)b[12+i]-256;
    if(!eq_valid(&temp))return -1;
    *c=temp;
    return 0;
}
