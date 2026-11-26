#include "descriptors.h"
#include <assert.h>
#include <stdio.h>
int main(void){
 dac_descriptors d;unsigned char b[128];
 for(unsigned hs=0;hs<2;hs++){
  assert(!dac_descriptors_init(&d,hs,0,1,1,0x81));size_t n=dac_descriptors_flatten(&d,b,sizeof(b));assert(n==109);
  assert(dac_descriptors_flatten(&d,b,108)==0);
  FILE *f=fopen(hs?"build/hs.bin":"build/fs.bin","wb");assert(f);assert(fwrite(b,1,n,f)==n);assert(!fclose(f));
 }
 assert(dac_descriptors_init(&d,1,0,0,1,0x81)<0);
 assert(dac_descriptors_init(&d,1,0,1,0x81,1)<0);
 puts("PASS descriptor generation and bounds");
}
