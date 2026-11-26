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
import orig_open, 0x499c
import orig_read, 0x4840
import orig_write, 0x478c
import orig_close, 0x476c
import orig_fsync, 0x45d8
import orig_unlink, 0x46f4
import orig_popen, 0x45b0
import orig_fgets, 0x4754
import orig_flip, 0x4630

.macro fixed name, address
.globl \name
.ent \name
\name:
    lui $t9,%hi(\address)
    addiu $t9,$t9,%lo(\address)
    lui $gp,0x45
    addiu $gp,$gp,-0x3b30
    jr $t9
    nop
.end \name
.endm
fixed orig_blit, 0x41fd68
fixed orig_pic, 0x41fd98
fixed orig_label, 0x426fa0
fixed orig_text, 0x420118
fixed orig_battery, 0x420890

.globl orig_rename
.ent orig_rename
orig_rename:
    addiu $v0,$zero,4038
    syscall
    beqz $a3,.Lrename_done
    nop
    addiu $v0,$zero,-1
.Lrename_done:
    jr $ra
    nop
.end orig_rename

.globl orig_fstat64
.ent orig_fstat64
orig_fstat64:
    addiu $v0,$zero,4215
    syscall
    beqz $a3,.Lfstat_done
    nop
    addiu $v0,$zero,-1
.Lfstat_done:
    jr $ra
    nop
.end orig_fstat64
