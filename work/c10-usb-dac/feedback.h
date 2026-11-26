#ifndef C10_DAC_FEEDBACK_H
#define C10_DAC_FEEDBACK_H
#include <stdint.h>
typedef struct {
 uint32_t received, consumed, last_hw, last_frame, target, q16;
 int32_t filtered_q8, integral;
 unsigned clock_valid, anchored, resets;
} dac_feedback;
void dac_feedback_reset(dac_feedback *);
void dac_feedback_receive(dac_feedback *,uint32_t);
uint32_t dac_feedback_tick(dac_feedback *,unsigned,uint32_t,uint32_t,unsigned);
void dac_feedback_encode(uint32_t,unsigned,unsigned char [4]);
#endif
