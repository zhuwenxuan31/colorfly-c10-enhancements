#!/bin/sh
set -eu
TASK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON="$TASK_DIR/../c10-analysis/venv/bin/python"
CROSS="$TASK_DIR/../c10-rockbox/cross-bin/mipsel-c10-gcc"
mkdir -p "$TASK_DIR/build"
cc -std=c11 -Wall -Wextra -Werror "$TASK_DIR/eq_model.c" "$TASK_DIR/test_model.c" -o "$TASK_DIR/build/test_model"
"$TASK_DIR/build/test_model"
"$CROSS" -Os -g -G0 -fno-pic -fno-builtin -ffreestanding -fno-stack-protector \
  -fno-unwind-tables -fno-asynchronous-unwind-tables -nostdlib -static \
  -Wl,--build-id=none -Wl,--no-gc-sections -Wl,-e,eq_popen -Wl,-T,"$TASK_DIR/module.ld" \
  "$TASK_DIR/eq_model.c" "$TASK_DIR/eq_module.c" "$TASK_DIR/original_abi.S" -o "$TASK_DIR/module.elf"
"$PYTHON" "$TASK_DIR/build_eq.py" prepare
cd "$TASK_DIR"
"$CROSS" -g -nostdlib -static -Wl,--build-id=none -Wl,--no-gc-sections \
  -Wl,-e,c10_eq_startup_entry -Wl,-T,bridges.ld bridges.S -o bridges.elf
"$PYTHON" "$TASK_DIR/build_eq.py"
"$PYTHON" "$TASK_DIR/test_eq_ui.py"
