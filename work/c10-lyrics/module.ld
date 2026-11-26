ENTRY(lyrics_flip)
SECTIONS {
    . = 0x455000;
    .lyrics : { *(.lyrics_entry) *(.text*) *(.rodata*) *(.data.rel.ro*) *(.got) }
    /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.pdr) *(.MIPS.abiflags) *(.reginfo) }
}
