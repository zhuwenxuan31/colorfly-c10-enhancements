#ifndef C10_DAC_DESCRIPTORS_H
#define C10_DAC_DESCRIPTORS_H
#include <stdint.h>
#include <stddef.h>
typedef struct {
 uint8_t ac[9], header[9], input[12], output[9];
 uint8_t alt0[9],alt1[9],stream[7],format[11],out[9],iso[7],feedback[9];
 const uint8_t *list[12];
} dac_descriptors;
int dac_descriptors_init(dac_descriptors *,unsigned,unsigned,unsigned,unsigned,unsigned);
size_t dac_descriptors_flatten(const dac_descriptors *,uint8_t *,size_t);
#endif
