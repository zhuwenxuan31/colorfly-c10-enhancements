ENTRY(eq_popen)
SECTIONS {
    . = 0x450000;
    .module : { *(.eq_entry) *(.text*) *(.rodata*) *(.data.rel.ro*) *(.got) }
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.pdr) *(.MIPS.abiflags) *(.reginfo) }
}
