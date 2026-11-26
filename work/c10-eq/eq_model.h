#ifndef C10_EQ_MODEL_H
#define C10_EQ_MODEL_H
#include <stddef.h>
#include <stdint.h>
#define EQ_BANDS 10
#define EQ_PRESETS 6
#define EQ_RECORD_SIZE 64
typedef struct {
    int enabled;
    int preset;
    int gain[EQ_BANDS];
} eq_config;
void eq_default(eq_config *);
int eq_valid(const eq_config *);
int eq_set_preset(eq_config *, int);
int eq_adjust(eq_config *, int, int);
int eq_headroom(const eq_config *);
int eq_volume_tenths(const eq_config *);
int eq_options(const eq_config *, char *, size_t);
void eq_encode(const eq_config *, unsigned char [EQ_RECORD_SIZE]);
int eq_decode(eq_config *, const unsigned char *, size_t);
#endif
