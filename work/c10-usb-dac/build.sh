#!/bin/sh
set -eu
TASK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON="$TASK_DIR/../c10-analysis/venv/bin/python"
ZIG="$TASK_DIR/../c10-prototype/toolchain/zig-macos-aarch64-0.13.0/zig"
mkdir -p "$TASK_DIR/build"
cc -std=c11 -O2 -Wall -Wextra -Werror "$TASK_DIR/feedback.c" "$TASK_DIR/test_feedback.c" -lm -o "$TASK_DIR/build/test_feedback"
"$TASK_DIR/build/test_feedback"
cc -std=c11 -O2 -Wall -Wextra -Werror "$TASK_DIR/descriptors.c" "$TASK_DIR/test_descriptors.c" -o "$TASK_DIR/build/test_descriptors"
cd "$TASK_DIR"
./build/test_descriptors
"$PYTHON" test_descriptors.py
"$PYTHON" module_elf.py
for unit in feedback descriptors usb_engine; do
 "$ZIG" cc -target mipsel-linux-musl -mcpu=mips32+soft_float+noabicalls+long_calls -mabi=32 -fno-lto -Os -G0 -fno-pic -fno-pie -mno-abicalls -static -ffreestanding -fno-builtin -fno-stack-protector -fno-unwind-tables -fno-asynchronous-unwind-tables -Wall -Wextra -Werror -c "$unit.c" -o "build/$unit.o"
done
"$ZIG" ld.lld -r --build-id=none build/stock-prepared.o build/feedback.o build/descriptors.o build/usb_engine.o -o build/g_audio.candidate.ko

"$PYTHON" audit_module.py
"$PYTHON" test_module.py
