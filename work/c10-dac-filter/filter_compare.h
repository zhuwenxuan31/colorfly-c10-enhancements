#ifndef C10_DAC_FILTER_COMPARE_H
#define C10_DAC_FILTER_COMPARE_H

/* A comparison is volatile. The caller owns one session and its transport. */
struct c10_filter_bus {
    int (*read)(void *context, unsigned char register_number);
    int (*write)(void *context, unsigned char register_number, unsigned char value);
    void *context;
};

struct c10_filter_compare {
    unsigned char control;
    unsigned char mode;
    unsigned char original;
    unsigned char alternate;
    int active;
};

enum c10_filter_result {
    C10_FILTER_OK,
    C10_FILTER_UNAVAILABLE,
    C10_FILTER_IO_ERROR,
    C10_FILTER_RESTORE_REQUIRED,
    C10_FILTER_STOCK_CHANGED,
};

enum c10_filter_result c10_filter_compare_start(const struct c10_filter_bus *, struct c10_filter_compare *);
enum c10_filter_result c10_filter_compare_restore(const struct c10_filter_bus *, struct c10_filter_compare *);

#endif
