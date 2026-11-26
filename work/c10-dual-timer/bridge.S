.set noreorder
.option pic0
.text

/* State: 446bf0 initialized, bf4 previous selection, bf8 armed ticks,
 * bfc active sleep, 446c00 pending menu selection, c04 menu-was-open.
 * Original idle setting remains exclusively at 4463c0.
 */
.globl c10_sleep_tick
.ent c10_sleep_tick
c10_sleep_tick:
    move $a2, $a0
    lui $t0, 0x44
    lw $t1, 0x4b34($t0)
    addiu $t2, $zero, 3
    beq $t1, $t2, .Lmenu_open
    nop
    sw $zero, 0x6c04($t0)
    b .Ltimer_step
    nop
.Lmenu_open:
    lw $t1, 0x6c04($t0)
    nop
    bnez $t1, .Ltimer_step
    nop
    lw $t1, 0x6bfc($t0)
    addiu $t2, $zero, 1
    sw $t1, 0x6c00($t0)
    sw $t2, 0x6c04($t0)
.Ltimer_step:
    ori $a0, $t0, 0x6bf0
    ori $a1, $t0, 0x6bfc
    j c10_sleep_step
    nop
.end c10_sleep_tick

.globl c10_power_checks_entry
.ent c10_power_checks_entry
c10_power_checks_entry:
    addiu $sp, $sp, -32
    sw $ra, 28($sp)
    sw $gp, 16($sp)
    jal c10_sleep_tick
    move $a0, $s0
    lw $gp, 16($sp)
    lw $ra, 28($sp)
    addiu $sp, $sp, 32
    bnez $v0, .Lsleep_expired
    lw $t9, -0x7c2c($gp)
    j 0x41b920
    nop
.Lsleep_expired:
    j 0x41ba48
    nop
.end c10_power_checks_entry

.globl c10_sleep_usb_entry
.ent c10_sleep_usb_entry
c10_sleep_usb_entry:
    lui $t0, 0x44
    sw $zero, 0x6bfc($t0)
    sw $zero, 0x6c00($t0)
    sw $zero, 0x6bf4($t0)
    sw $zero, 0x6c04($t0)
    lw $s0, -0x7ecc($gp)
    lw $t9, -0x7f58($gp)
    jr $ra
    nop
.end c10_sleep_usb_entry

.globl c10_menu_option_entry
.ent c10_menu_option_entry
c10_menu_option_entry:
    addiu $t8, $zero, 10
    beq $a0, $t8, .Lsleep_option
    nop
    /* Replay the two original instructions for all ten stock items. */
    lui $gp, 0x45
    lui $a2, 0x44
    j 0x425760
    nop
.Lsleep_option:
    lui $a2, 0x44
    addiu $v0, $zero, 1
    sw $v0, 0x5104($a2)
    lw $v1, 0x6c00($a2)
    addiu $t8, $zero, 106
    beq $a1, $t8, .Lsleep_right
    nop
    addiu $v1, $v1, -1
    b .Lsleep_store
    andi $v1, $v1, 3
.Lsleep_right:
    addiu $v1, $v1, 1
    andi $v1, $v1, 3
.Lsleep_store:
    jr $ra
    sw $v1, 0x6c00($a2)
.end c10_menu_option_entry

.globl c10_menu_commit_entry
.ent c10_menu_commit_entry
c10_menu_commit_entry:
    lui $t0, 0x44
    lw $t1, 0x6c00($t0)
    nop
    sw $t1, 0x6bfc($t0)
    /* Continue the untouched original idle-setting commit logic. */
    lw $v1, 0x14($s2)
    lw $t3, 0x14($s1)
    j 0x42602c
    nop
.end c10_menu_commit_entry

.globl c10_menu_discard_entry
.ent c10_menu_discard_entry
c10_menu_discard_entry:
    /* Match the stock dirty-navigation path: discard edits, keep active timer. */
    lui $t0, 0x44
    lw $t1, 0x6bfc($t0)
    nop
    sw $t1, 0x6c00($t0)
    lw $t8, -0x7ecc($gp)
    lw $t7, -0x7bc8($gp)
    j 0x4256f4
    nop
.end c10_menu_discard_entry

/* New switch case in c10displaysysconfig. s0=row, s3=screen; original
 * renderer has already painted selected-row background and scrollbar.
 * All nested calls use the original functions; no new SDL/audio ABI.
 */
.globl c10_sleep_draw_entry
.ent c10_sleep_draw_entry
c10_sleep_draw_entry:
    addiu $sp, $sp, -48
    sw $gp, 32($sp)
    lui $t0, 0x44
    lw $t1, 0x4b5c($t0)
    addiu $t2, $zero, 10
    xor $t1, $t1, $t2
    sltiu $a1, $t1, 1
    sw $a1, 36($sp)
    lw $t1, 0x63b8($t0)
    nop
    sltiu $t2, $t1, 3
    bnez $t2, .Lknown_language
    nop
    addiu $t1, $zero, 2
.Lknown_language:
    sll $t1, $t1, 2
    lui $t2, %hi(c10_sleep_titles)
    addiu $t2, $t2, %lo(c10_sleep_titles)
    addu $t2, $t2, $t1
    lw $a2, 0($t2)
    move $a0, $s0
    jal 0x426fa0
    move $a3, $s3
    lw $gp, 32($sp)
    lui $t0, 0x44
    lw $t1, 0x4adc($t0)
    lw $t2, 36($sp)
    nop
    beqz $t2, .Lunselected_icon
    nop
    b .Ldraw_icon
    lw $a1, 40($t1)
.Lunselected_icon:
    lw $a1, 44($t1)
.Ldraw_icon:
    move $a0, $s0
    jal 0x426f40
    move $a2, $s3
    lw $gp, 32($sp)
    lui $t0, 0x44
    lw $t1, 0x6c00($t0)
    nop
    andi $t1, $t1, 3
    sll $t1, $t1, 2
    lui $t2, %hi(c10_sleep_values)
    addiu $t2, $t2, %lo(c10_sleep_values)
    addu $t2, $t2, $t1
    lw $t2, 0($t2)
    sw $s3, 20($sp)
    sw $t2, 16($sp)
    lw $a2, -0x7e44($gp)
    lw $a3, -0x7d74($gp)
    lw $a2, 0($a2)
    lw $a3, 0($a3)
    sll $t0, $s0, 5
    sll $t1, $s0, 3
    addu $a1, $t0, $t1
    addiu $a1, $a1, 53
    jal 0x420118
    addiu $a0, $zero, 318
    lw $gp, 32($sp)
    addiu $sp, $sp, 48
    j 0x42790c
    nop
.end c10_sleep_draw_entry

.section .rodata
.balign 4
.globl c10_menu_dispatch_table
c10_menu_dispatch_table:
    .word 0xfffdb93c, 0xfffdb9ec, 0xfffdb858, 0xfffdbba8, 0xfffdb778
    .word 0xfffdbac0, 0xfffdb688, 0xfffdb5ac, 0xfffdb4ac, 0xfffdb3f4
    .word c10_sleep_draw_entry - 0x44c4d0
c10_sleep_titles:
    .word .Ltitle_zh, .Ltitle_tw, .Ltitle_en
c10_sleep_values:
    .word .Loff, .L30, .L60, .L90
.Ltitle_zh: .asciz "睡眠定时关机"
.Ltitle_tw: .asciz "睡眠定時關機"
.Ltitle_en: .asciz "Sleep timer"
.Loff: .asciz "OFF"
.L30: .asciz "30min"
.L60: .asciz "60min"
.L90: .asciz "90min"
