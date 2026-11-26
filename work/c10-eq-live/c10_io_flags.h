#ifndef C10_IO_FLAGS_H
#define C10_IO_FLAGS_H
/* Linux MIPS O32 flags, checked against bundled mips-linux-musl/bits/fcntl.h.
 * Deliberately not the host macOS flag values; this module is freestanding.
 */
#define O_RDONLY 0
#define O_WRONLY 1
#define O_APPEND 010
#define O_CREAT 0400
#define O_TRUNC 01000
#define O_NONBLOCK 0200
#define O_NOFOLLOW 0400000
#define O_CLOEXEC 02000000
#endif
