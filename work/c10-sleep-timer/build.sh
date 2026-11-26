#!/bin/sh
set -eu
TASK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON="$TASK_DIR/../c10-analysis/venv/bin/python"
CROSS="$TASK_DIR/../c10-rockbox/cross-bin/mipsel-c10-gcc"
cc -std=c11 -Wall -Wextra -Werror "$TASK_DIR/test_sleep_timer.c" \
  "$TASK_DIR/sleep_timer.c" -o "$TASK_DIR/test_sleep_timer"
"$TASK_DIR/test_sleep_timer"
"$CROSS" -Os -g -G0 -fno-pic -ffreestanding -fno-stack-protector \
  -fno-unwind-tables -fno-asynchronous-unwind-tables -nostdlib -static \
  -Wl,--build-id=none -Wl,--no-gc-sections -Wl,-e,c10_sleep_tick \
  -Wl,-u,c10_sleep_usb_entry -Wl,-T,"$TASK_DIR/payload.ld" \
  "$TASK_DIR/sleep_timer.c" "$TASK_DIR/usb_cancel.S" -o "$TASK_DIR/payload.elf"
"$PYTHON" "$TASK_DIR/build_patch.py"
"$PYTHON" "$TASK_DIR/test_mips_patch.py"
"$PYTHON" "$TASK_DIR/test_main_menu.py"
"$PYTHON" "$TASK_DIR/prepare_package.py"
