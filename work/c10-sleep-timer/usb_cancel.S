/* Replacement for the two original loads at 0x41b788/0x41b78c.
 * Called only on original PMU USB-connected detection, before stock USB setup.
 * Restore both original loads, preserving a0-a3 and gp for the original call.
 */
.set noreorder
.text
.globl c10_sleep_tick
.ent c10_sleep_tick
c10_sleep_tick:
    move $a2, $a0
    lui $t0, 0x44
    ori $a0, $t0, 0x6bf0
    ori $a1, $t0, 0x63c0
    j c10_sleep_step
    nop
.end c10_sleep_tick

.globl c10_sleep_usb_entry
.ent c10_sleep_usb_entry
c10_sleep_usb_entry:
    lui $t0, 0x44
    sw $zero, 0x63c0($t0)
    sw $zero, 0x6bf4($t0)
    lw $s0, -0x7ecc($gp)
    lw $t9, -0x7f58($gp)
    jr $ra
    nop
.end c10_sleep_usb_entry
