ENTRY(c10_sleep_tick)
SECTIONS {
    . = 0x433670;
    .payload : { *(.text*) *(.rodata*) }
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.pdr) *(.MIPS.abiflags) *(.reginfo) }
}
