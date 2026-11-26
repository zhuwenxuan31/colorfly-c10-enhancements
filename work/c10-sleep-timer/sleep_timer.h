#ifndef C10_SLEEP_TIMER_H
#define C10_SLEEP_TIMER_H
typedef unsigned int c10_u32;
typedef struct {
    c10_u32 initialized;
    c10_u32 selection;
    c10_u32 armed_at;
} c10_sleep_state;
int c10_sleep_step(volatile c10_sleep_state *, volatile c10_u32 *, c10_u32);
#endif
