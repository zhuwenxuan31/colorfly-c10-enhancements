#include "filter_compare.h"

enum {
    CHIP_ID = 1, MODE = 2, FILTER = 7, CONTROL = 8,
    PART_MASK = 0xf8, CS4398 = 0x70, CONTROLS_MASK = 0xe0, CONTROL_PORT = 0x40,
    FUNCTION_MODE_MASK = 3, SOFT_RAMPS = 0xb0, FILTER_BIT = 4,
};

enum c10_filter_result c10_filter_compare_restore(const struct c10_filter_bus *bus,
                                                 struct c10_filter_compare *trial) {
    if (!trial->active) return C10_FILTER_OK;
    int control = bus->read(bus->context, CONTROL);
    int mode = bus->read(bus->context, MODE);
    int current = bus->read(bus->context, FILTER);
    if (control < 0 || mode < 0 || current < 0) return C10_FILTER_RESTORE_REQUIRED;
    if (control != trial->control || mode != trial->mode ||
        (current != trial->alternate && current != trial->original)) {
        trial->active = 0;
        return C10_FILTER_STOCK_CHANGED;
    }
    if (current != trial->original) {
        bus->write(bus->context, FILTER, trial->original);
        if (bus->read(bus->context, FILTER) != trial->original) return C10_FILTER_RESTORE_REQUIRED;
    }
    trial->active = 0;
    return C10_FILTER_OK;
}

enum c10_filter_result c10_filter_compare_start(const struct c10_filter_bus *bus,
                                               struct c10_filter_compare *trial) {
    if (trial->active) return C10_FILTER_UNAVAILABLE;
    int id = bus->read(bus->context, CHIP_ID);
    if (id < 0) return C10_FILTER_IO_ERROR;
    if ((id & PART_MASK) != CS4398) return C10_FILTER_UNAVAILABLE;
    int control = bus->read(bus->context, CONTROL);
    int mode = bus->read(bus->context, MODE);
    if (control < 0 || mode < 0) return C10_FILTER_IO_ERROR;
    if ((control & CONTROLS_MASK) != CONTROL_PORT || (mode & FUNCTION_MODE_MASK))
        return C10_FILTER_UNAVAILABLE;
    int filter = bus->read(bus->context, FILTER);
    if (filter < 0) return C10_FILTER_IO_ERROR;
    if ((filter & SOFT_RAMPS) != SOFT_RAMPS) return C10_FILTER_UNAVAILABLE;

    *trial = (struct c10_filter_compare){(unsigned char)control, (unsigned char)mode,
        (unsigned char)filter, (unsigned char)(filter ^ FILTER_BIT), 1};
    int status = bus->write(bus->context, FILTER, trial->alternate);
    if (!status && bus->read(bus->context, FILTER) == trial->alternate) return C10_FILTER_OK;
    enum c10_filter_result restored = c10_filter_compare_restore(bus, trial);
    return restored == C10_FILTER_OK ? C10_FILTER_IO_ERROR : restored;
}
