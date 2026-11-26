#!/bin/sh
set -eu
TASK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON="$TASK_DIR/../c10-analysis/venv/bin/python"
CROSS="$TASK_DIR/../c10-rockbox/cross-bin/mipsel-c10-gcc"
mkdir -p "$TASK_DIR/build"
cc -std=c11 -Wall -Wextra -Werror "$TASK_DIR/eq_model.c" "$TASK_DIR/test_model.c" -o "$TASK_DIR/build/test_model"
"$TASK_DIR/build/test_model"
cc -std=c11 -Wall -Wextra -Werror "$TASK_DIR/eq_model.c" "$TASK_DIR/live_model.c" "$TASK_DIR/test_live_model.c" -o "$TASK_DIR/build/test_live_model"
"$TASK_DIR/build/test_live_model"
"$CROSS" -Os -g -G0 -fno-pic -fno-builtin -ffreestanding -fno-stack-protector \
  -fno-unwind-tables -fno-asynchronous-unwind-tables -nostdlib -static \
  -Wl,--build-id=none -Wl,--no-gc-sections -Wl,-e,eq_popen -Wl,-T,"$TASK_DIR/module.ld" \
  "$TASK_DIR/eq_model.c" "$TASK_DIR/live_model.c" "$TASK_DIR/eq_module.c" "$TASK_DIR/original_abi.S" -o "$TASK_DIR/module.elf"
"$PYTHON" "$TASK_DIR/build_eq.py" prepare
cd "$TASK_DIR"
# Zig's assembler cache does not track .include/.incbin dependencies reliably.
# Put the exact generated addresses and menu bytes in the compiler input.
"$PYTHON" -c 'from pathlib import Path; s=Path("bridges.S").read_text(); s=s.replace(".include \"build/module-addrs.inc\"",Path("build/module-addrs.inc").read_text()); s=s.replace(".incbin \"build/menu-prefix.bin\"",".byte "+",".join(str(x) for x in Path("build/menu-prefix.bin").read_bytes())); Path("build/bridges.expanded.S").write_text(s)'
"$CROSS" -g -nostdlib -static -Wl,--build-id=none -Wl,--no-gc-sections \
  -Wl,-e,c10_eq_startup_entry -Wl,-T,bridges.ld build/bridges.expanded.S -o bridges.elf
"$PYTHON" "$TASK_DIR/build_eq.py"
"$PYTHON" "$TASK_DIR/test_eq_ui.py"

"$PYTHON" "$TASK_DIR/test_live_ui.py"
"$PYTHON" "$TASK_DIR/test_eq_trace.py"
"$PYTHON" "$TASK_DIR/test_timer_regression.py"
