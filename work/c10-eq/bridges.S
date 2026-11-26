.set noreorder
.option pic0
.include "build/module-addrs.inc"
.text

.globl c10_eq_startup_entry
c10_eq_startup_entry:
    addiu $sp,$sp,-32
    sw $ra,28($sp)
    sw $gp,16($sp)
    lui $t9,%hi(EQ_INIT)
    addiu $t9,$t9,%lo(EQ_INIT)
    jalr $t9
    nop
    lw $gp,16($sp)
    jal 0x418ef8
    nop
    lw $gp,16($sp)
    lw $ra,28($sp)
    addiu $sp,$sp,32
    jr $ra
    nop

.globl c10_eq_option_entry
c10_eq_option_entry:
    addiu $t8,$zero,11
    beq $a0,$t8,.Lopen_eq
    nop
    j OLD_OPTION_ENTRY
    nop
.Lopen_eq:
    addiu $sp,$sp,-32
    sw $gp,16($sp)
    sw $ra,28($sp)
    lui $t9,%hi(EQ_OPEN)
    addiu $t9,$t9,%lo(EQ_OPEN)
    jalr $t9
    nop
    lw $gp,16($sp)
    lw $ra,28($sp)
    addiu $sp,$sp,32
    jr $ra
    nop

.globl c10_eq_draw_dispatch_entry
c10_eq_draw_dispatch_entry:
    addiu $sp,$sp,-48
    sw $gp,32($sp)
    sw $a0,36($sp)
    sw $ra,44($sp)
    lui $t9,%hi(EQ_DRAW)
    addiu $t9,$t9,%lo(EQ_DRAW)
    jalr $t9
    nop
    lw $gp,32($sp)
    lw $a0,36($sp)
    lw $ra,44($sp)
    addiu $sp,$sp,48
    bnez $v0,.Ldraw_done
    nop
    /* Exact stock prologue for the ordinary settings main menu. */
    lui $gp,0x45
    addiu $sp,$sp,-0x50
    j 0x4276ac
    nop
.Ldraw_done:
    jr $ra
    nop

.globl c10_eq_key_dispatch_entry
c10_eq_key_dispatch_entry:
    addiu $sp,$sp,-48
    sw $gp,32($sp)
    sw $a0,36($sp)
    sw $a1,40($sp)
    sw $ra,44($sp)
    lui $t9,%hi(EQ_KEY)
    addiu $t9,$t9,%lo(EQ_KEY)
    jalr $t9
    nop
    lw $gp,32($sp)
    lw $a0,36($sp)
    lw $a1,40($sp)
    lw $ra,44($sp)
    addiu $sp,$sp,48
    bnez $v0,.Lkey_done
    nop
    lui $gp,0x45
    addiu $sp,$sp,-0x30
    j 0x425a38
    nop
.Lkey_done:
    jr $ra
    nop

.globl c10_eq_down_dispatch_entry
c10_eq_down_dispatch_entry:
    addiu $sp,$sp,-48
    sw $gp,32($sp)
    sw $a0,36($sp)
    sw $a1,40($sp)
    sw $ra,44($sp)
    lui $t9,%hi(EQ_DOWN)
    addiu $t9,$t9,%lo(EQ_DOWN)
    jalr $t9
    nop
    lw $gp,32($sp)
    lw $a0,36($sp)
    lw $a1,40($sp)
    lw $ra,44($sp)
    addiu $sp,$sp,48
    bnez $v0,.Ldown_done
    nop
    lui $gp,0x45
    addiu $sp,$sp,-0x28
    j 0x426238
    nop
.Ldown_done:
    jr $ra
    nop

.globl c10_eq_main_draw_entry
.globl c10_eq_fgets_entry
c10_eq_fgets_entry:
    addiu $sp,$sp,-32
    sw $gp,16($sp)
    sw $ra,28($sp)
    lui $t9,%hi(EQ_FGETS)
    addiu $t9,$t9,%lo(EQ_FGETS)
    jalr $t9
    nop
    lw $gp,16($sp)
    lw $ra,28($sp)
    addiu $sp,$sp,32
    jr $ra
    nop

c10_eq_main_draw_entry:
    addiu $sp,$sp,-32
    sw $gp,16($sp)
    lui $t0,0x44
    lw $t1,0x4b5c($t0)
    addiu $t2,$zero,11
    xor $t1,$t1,$t2
    sltiu $a1,$t1,1
    move $a0,$s0
    move $a2,$s3
    lui $t9,%hi(EQ_MAIN)
    addiu $t9,$t9,%lo(EQ_MAIN)
    jalr $t9
    nop
    lw $gp,16($sp)
    addiu $sp,$sp,32
    j 0x42790c
    nop

.section .rodata
.balign 4
.globl c10_eq_menu_table
c10_eq_menu_table:
    .incbin "build/menu-prefix.bin"
    .word c10_eq_main_draw_entry - 0x44c4d0
