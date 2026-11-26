#include "filter_compare.h"

struct bus_type;
struct device;
struct i2c_client;
extern struct bus_type i2c_bus_type;
extern struct device *bus_find_device_by_name(struct bus_type *, struct device *, const char *);
extern struct i2c_client *i2c_verify_client(struct device *);
extern int i2c_smbus_read_byte_data(const struct i2c_client *, unsigned char);
extern int i2c_smbus_write_byte_data(const struct i2c_client *, unsigned char, unsigned char);
extern void put_device(struct device *);
extern int printk(const char *, ...);

static struct c10_filter_compare comparison;
static struct device *held_device;
static struct c10_filter_bus bus;

static int read_register(void *context, unsigned char reg) {
    return i2c_smbus_read_byte_data(context, reg);
}

static int write_filter(void *context, unsigned char reg, unsigned char value) {
    /* Restrict writes to the two register states from the verified C10. */
    if (reg != 7 || (value != 0xb0 && value != 0xb4)) return -22;
    return i2c_smbus_write_byte_data(context, reg, value);
}

int init_module(void) {
    struct device *dev = bus_find_device_by_name(&i2c_bus_type, (void *)0, "0-004c");
    if (!dev) { printk("<5>C10DAC_AB1 no-device\n"); return 0; }
    struct i2c_client *client = i2c_verify_client(dev);
    if (!client || read_register(client, 1) != 0x72 || read_register(client, 7) != 0xb0) {
        printk("<5>C10DAC_AB1 baseline-mismatch\n");
        put_device(dev);
        return 0;
    }
    bus = (struct c10_filter_bus){read_register, write_filter, client};
    enum c10_filter_result result = c10_filter_compare_start(&bus, &comparison);
    if (comparison.active) held_device = dev;
    else put_device(dev);
    if (result == C10_FILTER_OK)
        printk("<5>C10DAC_AB1 active=slow before=%02x after=%02x\n",
               (unsigned)comparison.original, (unsigned)comparison.alternate);
    else
        printk("<5>C10DAC_AB1 start-status=%d\n", result);
    return 0;
}

void cleanup_module(void) {
    if (!held_device) return;
    enum c10_filter_result result = c10_filter_compare_restore(&bus, &comparison);
    for (unsigned attempt = 0; attempt < 2 && result == C10_FILTER_RESTORE_REQUIRED; attempt++)
        result = c10_filter_compare_restore(&bus, &comparison);
    if (result == C10_FILTER_OK) printk("<5>C10DAC_AB1 restored=fast value=b0\n");
    else printk("<5>C10DAC_AB1 restore-status=%d\n", result);
    put_device(held_device);
    held_device = (void *)0;
}
