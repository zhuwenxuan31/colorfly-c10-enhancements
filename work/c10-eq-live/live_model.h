#ifndef C10_LIVE_MODEL_H
#define C10_LIVE_MODEL_H
#include "eq_model.h"
/* Packet is one atomic <=512B FIFO write. All inputs are validated integers. */
int eq_live_change(const eq_config *,int,const eq_config *,char *,size_t);
int eq_live_install(int,char *,size_t);
#endif
