ENTRY(c10_eq_startup_entry)
SECTIONS {
    . = 0x433a00;
    .bridges : { *(.text*) *(.rodata*) *(.got) }
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.pdr) *(.MIPS.abiflags) *(.reginfo) }
}
