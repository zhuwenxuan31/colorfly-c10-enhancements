#include "eq_model.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    eq_config c, d;
    char options[256], small[5] = {'X','X','X','X','X'};
    unsigned char record[EQ_RECORD_SIZE];
    eq_default(&c);
    assert(eq_valid(&c) && c.enabled == 0 && c.preset == 0);
    assert(eq_options(&c, options, sizeof options) == 0 && options[0] == 0);
    for (int i=0; i<5; i++) {
        assert(eq_set_preset(&c,i) == 0);
        for (int k=0;k<EQ_BANDS;k++) assert(c.gain[k] <= 0);
        assert(eq_headroom(&c) == 0 && eq_volume_tenths(&c) == 0);
    }
    eq_default(&c);
    assert(eq_adjust(&c,5,1) == 0 && c.preset == 5 && c.gain[5] == 1);
    assert(eq_headroom(&c) == 4 && eq_volume_tenths(&c) == 107);
    for (int i=0;i<40;i++) assert(eq_adjust(&c,5,1) == 0);
    assert(c.gain[5] == 12 && eq_volume_tenths(&c) == -159);
    for (int i=0;i<40;i++) assert(eq_adjust(&c,5,-1) == 0);
    assert(c.gain[5] == -12);
    assert(eq_adjust(&c,-1,1) == -1 && eq_adjust(&c,10,1) == -1);
    eq_default(&c);c.enabled=1;
    assert(eq_options(&c,options,sizeof options) > 0);
    assert(strcmp(options," -af-add equalizer=0:0:0:0:0:0:0:0:0:0,volume=0.0:0:0") == 0);
    c.gain[5]=1;c.preset=5;
    assert(eq_options(&c,options,sizeof options) > 0);
    assert(strstr(options,"equalizer=0:0:0:0:0:1:0:0:0:0,volume=10.7:0:0"));
    assert(eq_options(&c,small,4) == -1 && small[4] == 'X');
    eq_encode(&c,record);
    assert(eq_decode(&d,record,sizeof record) == 0);
    assert(d.enabled==c.enabled && d.preset==c.preset);
    for(int k=0;k<EQ_BANDS;k++) assert(d.gain[k]==c.gain[k]);
    record[12]^=1;
    assert(eq_decode(&d,record,sizeof record)==-1 && d.enabled==0);
    assert(eq_decode(&d,record,sizeof record-1)==-1 && d.enabled==0);
    c.gain[0]=13;
    assert(!eq_valid(&c) && eq_options(&c,options,sizeof options)==-1);
    puts("PASS: EQ defaults, cut-only presets, manual limits, native scaling compensation, bounded options, config roundtrip/corruption");
    return 0;
}
