#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p build
for test in gesture recycle; do
    cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        "test_$test.c" "$test.c" -o "build/test_$test"
    "build/test_$test"
done
../c10-rockbox/cross-bin/mipsel-c10-gcc -Os -g -G0 -fno-pic -fno-builtin -ffreestanding \
    -Wall -Wextra -Werror -fno-stack-protector -fno-unwind-tables -fno-asynchronous-unwind-tables \
    -nostdlib -static -Wl,--build-id=none -Wl,--no-gc-sections -Wl,-e,c10_delete_down -Wl,-T,module.ld \
    native_abi.S gesture.c delete_ui.c recycle.c -o build/module.elf
../c10-analysis/venv/bin/python build_patch.py
../c10-analysis/venv/bin/python test_native.py
