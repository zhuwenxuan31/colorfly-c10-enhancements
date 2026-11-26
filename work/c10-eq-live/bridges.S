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

.set noat
.globl c10_eq_poll_entry
c10_eq_poll_entry:
    addiu $sp,$sp,-112
    sw $at,16($sp)
    sw $v0,20($sp)
    sw $v1,24($sp)
    sw $a0,28($sp)
    sw $a1,32($sp)
    sw $a2,36($sp)
    sw $a3,40($sp)
    sw $t0,44($sp)
    sw $t1,48($sp)
    sw $t2,52($sp)
    sw $t3,56($sp)
    sw $t4,60($sp)
    sw $t5,64($sp)
    sw $t6,68($sp)
    sw $t7,72($sp)
    sw $t8,76($sp)
    sw $t9,80($sp)
    sw $gp,84($sp)
    sw $ra,88($sp)
    mfhi $t0
    sw $t0,92($sp)
    mflo $t0
    sw $t0,96($sp)
    lui $t9,%hi(EQ_POLL)
    addiu $t9,$t9,%lo(EQ_POLL)
    jalr $t9
    move $a0,$s0
    lw $t0,92($sp)
    mthi $t0
    lw $t0,96($sp)
    mtlo $t0
    lw $at,16($sp)
    lw $v0,20($sp)
    lw $v1,24($sp)
    lw $a0,28($sp)
    lw $a1,32($sp)
    lw $a2,36($sp)
    lw $a3,40($sp)
    lw $t0,44($sp)
    lw $t1,48($sp)
    lw $t2,52($sp)
    lw $t3,56($sp)
    lw $t4,60($sp)
    lw $t5,64($sp)
    lw $t6,68($sp)
    lw $t7,72($sp)
    lw $t8,76($sp)
    lw $t9,80($sp)
    lw $gp,84($sp)
    lw $ra,88($sp)
    addiu $sp,$sp,112
    j OLD_POWER_ENTRY
    nop
.set at

.section .rodata
.balign 4
.globl c10_eq_menu_table
c10_eq_menu_table:
    .incbin "build/menu-prefix.bin"
    .word c10_eq_main_draw_entry - 0x44c4d0
