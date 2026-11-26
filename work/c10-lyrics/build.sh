#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$HERE"
mkdir -p build
cc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined test_lrc.c lrc.c -o build/test_lrc
build/test_lrc
../c10-rockbox/cross-bin/mipsel-c10-gcc -Os -g -G0 -fno-pic -fno-builtin -ffreestanding     -fno-stack-protector -fno-unwind-tables -fno-asynchronous-unwind-tables     -nostdlib -static -Wl,--build-id=none -Wl,--no-gc-sections -Wl,-e,lyrics_flip     -Wl,-T,module.ld lrc.c lyrics_ui.c original_abi.S -o module.elf
PYTHON=../c10-analysis/venv/bin/python
"$PYTHON" build_patch.py
"$PYTHON" test_mips.py
