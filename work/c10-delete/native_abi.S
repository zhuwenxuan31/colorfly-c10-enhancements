.set noreorder
.abicalls
.option pic0
.text

.macro stock_call name, slot
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

stock_call delete_malloc, 0x48dc
stock_call delete_ticks, 0x48f0
stock_call delete_maprgb, 0x4814
stock_call delete_fill, 0x4894
stock_call delete_text, 0x46b8
stock_call delete_blit, 0x47fc
stock_call delete_free_surface, 0x4a00
stock_call delete_flip, 0x4630

.macro linux_call name, number
.globl \name
.ent \name
\name:
    addiu $v0,$zero,\number
    syscall
    beqz $a3,1f
    nop
    subu $v0,$zero,$v0
1:
    jr $ra
    nop
.end \name
.endm

linux_call delete_rename, 4038
linux_call delete_mkdir, 4039
linux_call delete_lstat64, 4214

.globl delete_original_down
.ent delete_original_down
delete_original_down:
    j 0x433b28
    nop
.end delete_original_down

.macro modal_key name, handler, original
.globl \name
.ent \name
\name:
    addiu $sp,$sp,-48
    sw $gp,32($sp)
    sw $a0,36($sp)
    sw $a1,40($sp)
    sw $ra,44($sp)
    lui $t9,%hi(\handler)
    addiu $t9,$t9,%lo(\handler)
    jalr $t9
    nop
    lw $gp,32($sp)
    lw $a0,36($sp)
    lw $a1,40($sp)
    lw $ra,44($sp)
    addiu $sp,$sp,48
    bnez $v0,1f
    nop
    j \original
    nop
1:
    jr $ra
    nop
.end \name
.endm

.section .delete_entry,"ax",@progbits
modal_key c10_delete_down, c10_delete_down_c, 0x433b28
modal_key c10_delete_up, c10_delete_up_c, 0x433ad0

.globl c10_delete_flip
.ent c10_delete_flip
c10_delete_flip:
    lui $t9,%hi(c10_delete_flip_c)
    addiu $t9,$t9,%lo(c10_delete_flip_c)
    jr $t9
    nop
.end c10_delete_flip
