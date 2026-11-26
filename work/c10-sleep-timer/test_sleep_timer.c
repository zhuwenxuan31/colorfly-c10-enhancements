#include "sleep_timer.h"
#include <assert.h>
#include <stdio.h>

static void boundaries(unsigned selection, unsigned duration) {
    c10_sleep_state s = {0};
    unsigned option = selection;
    assert(!c10_sleep_step(&s, &option, 123));
    assert(option == 0); /* Stored selection from an earlier boot never arms. */
    option = selection;
    assert(!c10_sleep_step(&s, &option, 500));
    assert(!c10_sleep_step(&s, &option, 500 + duration - 1));
    assert(c10_sleep_step(&s, &option, 500 + duration));
    assert(option == 0);
    assert(!c10_sleep_step(&s, &option, 501 + duration));
}

int main(void) {
    c10_sleep_state s = {0};
    unsigned option = 0;
    boundaries(1, 1800000);
    boundaries(2, 3600000);
    boundaries(3, 5400000);
    assert(!c10_sleep_step(&s, &option, 0));
    option = 1;
    assert(!c10_sleep_step(&s, &option, 100));
    option = 0;
    assert(!c10_sleep_step(&s, &option, 1000));
    assert(!c10_sleep_step(&s, &option, 7200000));
    option = 1;
    assert(!c10_sleep_step(&s, &option, 8000000));
    option = 2;
    assert(!c10_sleep_step(&s, &option, 9000000));
    assert(!c10_sleep_step(&s, &option, 9000000 + 3599999));
    assert(c10_sleep_step(&s, &option, 9000000 + 3600000));
    option = 1;
    assert(!c10_sleep_step(&s, &option, 0xffff0000u));
    assert(!c10_sleep_step(&s, &option, 0xffff0000u + 1799999u));
    assert(c10_sleep_step(&s, &option, 0xffff0000u + 1800000u));
    option = 0xffffffffu;
    assert(!c10_sleep_step(&s, &option, 10));
    assert(option == 0);
    puts("PASS: 30/60/90 minute boundaries, boot reset, cancel, rearm, tick wrap, invalid selection, one-shot");
    return 0;
}
