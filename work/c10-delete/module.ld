ENTRY(c10_delete_down)
SECTIONS {
    . = 0x457000;
    .delete : { *(.delete_entry) *(.text*) *(.rodata*) *(.data.rel.ro*) *(.got) }
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.pdr) *(.MIPS.abiflags) *(.reginfo) }
}
