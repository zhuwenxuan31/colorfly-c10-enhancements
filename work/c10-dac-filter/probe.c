/* Read three documented registers through the stock I2C client's adapter. */
struct bus_type;
struct device;
struct i2c_client;

extern struct bus_type i2c_bus_type;
extern struct device *bus_find_device_by_name(struct bus_type *bus, struct device *start, const char *name);
extern struct i2c_client *i2c_verify_client(struct device *dev);
extern int i2c_smbus_read_byte_data(const struct i2c_client *client, unsigned char reg);
extern void put_device(struct device *dev);
extern int printk(const char *format, ...);

enum {
    CHIP_ID = 1, FILTER_CONTROL = 7, MISC_CONTROL = 8,
    PART_MASK = 0xf8, CS4398_ID = 0x70, FILTER_SLOW = 4, CPEN = 0x40, PDN = 0x80,
};

static void log_status(const char *status, int value) {
    printk("<5>C10DAC_PROBE1 status=%s value=%d\n", status, value);
}

static void probe(const struct i2c_client *client) {
    int id = i2c_smbus_read_byte_data(client, CHIP_ID);
    if (id < 0) { log_status("chip-id-read-error", id); return; }
    if ((id & PART_MASK) != CS4398_ID) { log_status("unexpected-chip-id", id); return; }
    int control = i2c_smbus_read_byte_data(client, MISC_CONTROL);
    if (control < 0) { log_status("control-read-error", control); return; }
    if (!(control & CPEN)) { log_status("control-port-disabled", control); return; }
    if (control & PDN) { log_status("powered-down", control); return; }
    int filter = i2c_smbus_read_byte_data(client, FILTER_CONTROL);
    if (filter < 0) { log_status("filter-read-error", filter); return; }
    printk("<5>C10DAC_PROBE1 filter=%s id=%02x control=%02x value=%02x\n",
           (filter & FILTER_SLOW) ? "slow" : "fast", (unsigned)id, (unsigned)control, (unsigned)filter);
}

int init_module(void) {
    struct device *dev = bus_find_device_by_name(&i2c_bus_type, (void *)0, "0-004c");
    if (!dev) { log_status("no-device", 0); return 0; }
    struct i2c_client *client = i2c_verify_client(dev);
    if (client) probe(client);
    else log_status("not-i2c-client", 0);
    put_device(dev);
    return 0;
}

void cleanup_module(void) {}
