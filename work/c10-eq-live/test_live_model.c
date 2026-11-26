#include "live_model.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
int main(void){
 eq_config a,b;eq_default(&a);eq_default(&b);a.enabled=b.enabled=1;
 char out[512];
 assert(eq_live_change(&a,0,&b,out,sizeof(out))==0);
 b.gain[0]=1;
 int n=eq_live_change(&a,0,&b,out,sizeof(out));assert(n>0 && n<512);
 assert(strstr(out,"af_cmdline equalizer")<strstr(out,"af_cmdline volume"));
 a=b;b.gain[1]=12;
 n=eq_live_change(&a,eq_volume_tenths(&a),&b,out,sizeof(out));assert(n>0);
 assert(strstr(out,"af_cmdline volume")<strstr(out,"af_cmdline equalizer"));
 b.enabled=0;n=eq_live_change(&a,eq_volume_tenths(&a),&b,out,sizeof(out));assert(n>0);
 assert(strstr(out,"equalizer 0:0:0:0:0:0:0:0:0:0"));
 n=eq_live_install(1,out,sizeof(out));assert(n>0&&n<512&&out[0]=='\n'&&out[n-1]=='\n');
 assert(strstr(out,"af_add volume=-200.0:0:0,equalizer=0"));
 assert(strstr(out,"get_property pause"));assert(!strstr(out,"print_text"));
 n=eq_live_install(0,out,sizeof(out));assert(n>0&&!strstr(out,"af_add"));
 assert(eq_live_install(1,out,16)<0);
 puts("PASS live packet bounds/order/OFF/install/fence");
}
