#include "filter_compare.h"
#include <assert.h>
#include <stdio.h>

struct chip { int id, control, mode, filter, writes, write_error, commit_error, fail_readback, read_error; };

static int read_reg(void *context, unsigned char reg) {
    struct chip *chip = context;
    switch (reg) {
    case 1: return chip->id;
    case 2: return chip->mode;
    case 7:
        if (chip->read_error) { chip->read_error = 0; return -5; }
        return chip->filter;
    case 8: return chip->control;
    default: assert(0); return -1;
    }
}

static int write_reg(void *context, unsigned char reg, unsigned char value) {
    struct chip *chip = context;
    assert(reg == 7 && (chip->filter ^ value) == 4);
    chip->writes++;
    if (chip->write_error) return -5;
    chip->filter = value;
    if (chip->fail_readback) { chip->fail_readback = 0; chip->read_error = 1; }
    return chip->commit_error ? -5 : 0;
}

int main(void) {
    struct chip chip;
    const struct chip stock = {.id=0x71,.control=0x40,.mode=0x10,.filter=0xb0};
    struct c10_filter_bus bus = {read_reg, write_reg, &chip};
    struct c10_filter_compare state = {0};

    chip=stock;
    assert(c10_filter_compare_start(&bus,&state)==C10_FILTER_OK);
    assert(state.active && chip.filter==0xb4 && chip.writes==1);
    assert(c10_filter_compare_start(&bus,&state)==C10_FILTER_UNAVAILABLE && chip.writes==1);
    assert(c10_filter_compare_restore(&bus,&state)==C10_FILTER_OK);
    assert(!state.active && chip.filter==0xb0 && chip.writes==2);

    chip=stock; chip.filter=0xb4;
    assert(c10_filter_compare_start(&bus,&state)==C10_FILTER_OK && chip.filter==0xb0);
    assert(c10_filter_compare_restore(&bus,&state)==C10_FILTER_OK && chip.filter==0xb4);

    chip=stock; chip.mode|=3;
    assert(c10_filter_compare_start(&bus,&state)==C10_FILTER_UNAVAILABLE && chip.writes==0);
    chip=stock; chip.control|=0x80;
    assert(c10_filter_compare_start(&bus,&state)==C10_FILTER_UNAVAILABLE && chip.writes==0);
    chip=stock; chip.filter&=~0x20;
    assert(c10_filter_compare_start(&bus,&state)==C10_FILTER_UNAVAILABLE && chip.writes==0);
    chip=stock; chip.id=0x60;
    assert(c10_filter_compare_start(&bus,&state)==C10_FILTER_UNAVAILABLE && chip.writes==0);

    chip=stock; chip.write_error=1;
    assert(c10_filter_compare_start(&bus,&state)==C10_FILTER_IO_ERROR);
    assert(chip.filter==0xb0 && !state.active);
    chip=stock; chip.commit_error=1;
    assert(c10_filter_compare_start(&bus,&state)==C10_FILTER_IO_ERROR);
    assert(chip.filter==0xb0 && !state.active && chip.writes==2);
    chip=stock; chip.fail_readback=1;
    assert(c10_filter_compare_start(&bus,&state)==C10_FILTER_IO_ERROR);
    assert(chip.filter==0xb0 && !state.active && chip.writes==2);

    chip=stock;
    assert(c10_filter_compare_start(&bus,&state)==C10_FILTER_OK);
    chip.write_error=1;
    assert(c10_filter_compare_restore(&bus,&state)==C10_FILTER_RESTORE_REQUIRED);
    assert(state.active && chip.filter==0xb4);
    chip.write_error=0;
    assert(c10_filter_compare_restore(&bus,&state)==C10_FILTER_OK && chip.filter==0xb0);

    chip=stock;
    assert(c10_filter_compare_start(&bus,&state)==C10_FILTER_OK);
    chip.filter ^= 0x80;
    assert(c10_filter_compare_restore(&bus,&state)==C10_FILTER_STOCK_CHANGED);
    assert(chip.filter==0x34 && chip.writes==1);
    chip=stock;
    assert(c10_filter_compare_start(&bus,&state)==C10_FILTER_OK);
    chip.mode |= 1;
    assert(c10_filter_compare_restore(&bus,&state)==C10_FILTER_STOCK_CHANGED);
    assert(chip.writes==1);
    puts("Filter comparison and restoration cases passed");
}
