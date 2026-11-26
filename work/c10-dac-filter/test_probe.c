#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

struct bus_type { int unused; } i2c_bus_type;
struct device { int unused; } device;
struct i2c_client { int unused; } client;

static int found, valid_client, releases, count;
static int register_values[9];
static unsigned registers[3];
static char logline[128];

extern int init_module(void);

struct device *bus_find_device_by_name(struct bus_type *bus, struct device *start, const char *name) {
    assert(bus == &i2c_bus_type && !start && strcmp(name, "0-004c") == 0);
    return found ? &device : NULL;
}
struct i2c_client *i2c_verify_client(struct device *device_arg) {
    assert(device_arg == &device);
    return valid_client ? &client : NULL;
}
int i2c_smbus_read_byte_data(const struct i2c_client *client_arg, unsigned char reg) {
    assert(client_arg == &client && count < 3 && (reg == 1 || reg == 7 || reg == 8));
    registers[count++] = reg;
    return register_values[reg];
}
void put_device(struct device *device_arg) {
    assert(device_arg == &device);
    releases++;
}
int printk(const char *format, ...) {
    va_list arguments;
    va_start(arguments, format);
    int result = vsnprintf(logline, sizeof(logline), format, arguments);
    va_end(arguments);
    return result;
}

static void expect(const char *message, int reads, int put) {
    count = releases = 0;
    assert(init_module() == 0);
    assert(strstr(logline, message));
    assert(count == reads && releases == put);
}

int main(void) {
    expect("no-device", 0, 0);
    found = 1;
    expect("not-i2c-client", 0, 1);
    valid_client = 1;
    register_values[1] = -5;
    expect("chip-id-read-error", 1, 1);
    register_values[1] = 0x60;
    expect("unexpected-chip-id", 1, 1);
    register_values[1] = 0x71;
    register_values[8] = 0;
    expect("control-port-disabled", 2, 1);
    register_values[8] = 0xc0;
    expect("powered-down", 2, 1);
    register_values[8] = -5;
    expect("control-read-error", 2, 1);
    register_values[8] = 0x40;
    register_values[7] = -5;
    expect("filter-read-error", 3, 1);
    register_values[7] = 0xb0;
    expect("filter=fast id=71 control=40 value=b0", 3, 1);
    register_values[7] = 0xb4;
    expect("filter=slow id=71 control=40 value=b4", 3, 1);
    assert(registers[0] == 1 && registers[1] == 8 && registers[2] == 7);
    puts("10 DAC probe cases passed");
}
