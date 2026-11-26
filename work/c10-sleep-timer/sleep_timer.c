#include "sleep_timer.h"
int c10_sleep_step(volatile c10_sleep_state *s, volatile c10_u32 *option, c10_u32 now) {
    c10_u32 selected = *option;
    c10_u32 duration;
    if (!s->initialized) {
        s->initialized = 1;
        s->selection = 0;
        s->armed_at = now;
        *option = 0;
        return 0;
    }
    if (selected > 3) {
        selected = 0;
        *option = 0;
    }
    if (selected != s->selection) {
        s->selection = selected;
        s->armed_at = now;
    }
    if (!selected) return 0;
    duration = selected * 1800000u;
    if ((c10_u32)(now - s->armed_at) < duration) return 0;
    *option = 0;
    s->selection = 0;
    return 1;
}
