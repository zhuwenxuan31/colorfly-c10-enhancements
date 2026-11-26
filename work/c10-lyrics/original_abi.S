.set noreorder
.abicalls
.option pic0
.text
.macro import name, slot
.globl \name
.ent \name
\name:
    lui $t9,0x44
    lw $t9,\slot($t9)
    lui $gp,0x45
    addiu $gp,$gp,-0x3b30
    jr $t9
    nop
.end \name
.endm
import orig_malloc, 0x48dc
import orig_free, 0x45f4
import orig_open, 0x499c
import orig_close, 0x476c
import orig_read, 0x4840
import orig_maprgb, 0x4814
import orig_fill_rect, 0x4894
import orig_measure, 0x49d4
import orig_render, 0x46b8
import orig_upper_blit, 0x47fc
import orig_free_surface, 0x4a00
import orig_flip, 0x4630

.globl orig_fstat64
.ent orig_fstat64
orig_fstat64:
    addiu $v0,$zero,4215
    syscall
    beqz $a3,1f
    nop
    addiu $v0,$zero,-1
1:
    jr $ra
    nop
.end orig_fstat64

.section .lyrics_entry,"ax",@progbits
.globl lyrics_flip
.ent lyrics_flip
lyrics_flip:
    lui $t9,%hi(lyrics_flip_c)
    addiu $t9,$t9,%lo(lyrics_flip_c)
    jr $t9
    nop
.end lyrics_flip
