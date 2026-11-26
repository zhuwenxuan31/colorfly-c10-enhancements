#include "live_model.h"
typedef struct {char *p;size_t n,cap;int fail;} buf;
static void put(buf *b,char c){if(b->n+1>=b->cap || b->n>=511){b->fail=1;return;}b->p[b->n++]=c;}
static void text(buf *b,const char *s){while(*s)put(b,*s++);}
static void num(buf *b,int v){char d[12];int n=0;if(v<0){put(b,'-');v=-v;}do{d[n++]=(char)('0'+v%10);v/=10;}while(v);while(n)put(b,d[--n]);}
static void volume(buf *b,int v){text(b,"pausing_keep_force af_cmdline volume ");if(v<0){put(b,'-');v=-v;}num(b,v/10);put(b,'.');put(b,(char)('0'+v%10));text(b,":0:0\n");}
static void equalizer(buf *b,const eq_config *c){text(b,"pausing_keep_force af_cmdline equalizer ");for(int i=0;i<EQ_BANDS;i++){if(i)put(b,':');num(b,c->enabled?c->gain[i]:0);}put(b,'\n');}
static int done(buf *b){if(b->cap)b->p[b->n]=0;return b->fail?-1:(int)b->n;}
int eq_live_change(const eq_config *old,int oldvolume,const eq_config *target,char *out,size_t cap){
 if(!eq_valid(old)||!eq_valid(target)||!cap||oldvolume< -2000||oldvolume>200)return -1;
 int same=1;for(int i=0;i<EQ_BANDS;i++)if((old->enabled?old->gain[i]:0)!=(target->enabled?target->gain[i]:0))same=0;
 int v=target->enabled?eq_volume_tenths(target):0;
 buf b={out,0,cap,0};out[0]=0;
 if(same&&v==oldvolume)return 0;
 put(&b,'\n');
 /* Each intermediate gain is bounded by one endpoint: lower amplification
  * precedes a boost; higher amplification follows the new EQ. */
 if(v<oldvolume)volume(&b,v);
 if(!same)equalizer(&b,target);
 if(v>oldvolume)volume(&b,v);
 return done(&b);
}
int eq_live_install(int add,char *out,size_t cap){
 if(!cap)return -1;
 buf b={out,0,cap,0};put(&b,'\n');
 if(add)text(&b,"pausing_keep_force af_add volume=-200.0:0:0,equalizer=0:0:0:0:0:0:0:0:0:0\n");
 volume(&b,-2000);eq_config flat;eq_default(&flat);equalizer(&b,&flat);
 text(&b,"pausing_keep_force get_property pause\n");return done(&b);
}
