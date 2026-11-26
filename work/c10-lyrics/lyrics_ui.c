#include "lrc.h"
#include "../c10-eq-live/c10_io_flags.h"
#include <stdint.h>

#define STOCK32(address) (*(volatile uint32_t *)(address))
#define STATE_SLOT (*(struct LyricsState **)0x446ff0u)

struct Rect { int16_t x, y; uint16_t w, h; };
struct Surface {
    uint32_t flags;
    void *format;
    int width, height;
};

struct LyricsState {
    char path[LRC_PATH_BYTES];
    struct Lrc lrc;
    int rendered_line;
    void *rendered_font;
    struct Surface *rows[3];
};

extern void *orig_malloc(unsigned size);
extern void orig_free(void *ptr);
extern int orig_open(const char *path, int flags, int mode);
extern int orig_close(int fd);
extern int orig_read(int fd, void *buffer, unsigned size);
extern int orig_fstat64(int fd, void *buffer);
extern uint32_t orig_maprgb(void *format, unsigned red, unsigned green, unsigned blue);
extern int orig_fill_rect(void *screen, struct Rect *rect, unsigned color);
extern int orig_measure(void *font, const char *text, int *w, int *h);
extern struct Surface *orig_render(void *font, const char *text, uint32_t color);
extern int orig_upper_blit(void *src, void *src_rect, void *dst, struct Rect *dst_rect);
extern void orig_free_surface(void *surface);
extern int orig_flip(void *screen);

static int same(const char *a, const char *b) {
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}

static void reset_rows(struct LyricsState *state) {
    for (unsigned i = 0; i < 3; i++) {
        if (state->rows[i]) orig_free_surface(state->rows[i]);
        state->rows[i] = 0;
    }
    state->rendered_line = -2;
}

static void load(struct LyricsState *state, const char *path) {
    unsigned i = 0;
    do { state->path[i] = path[i]; } while (path[i++]);
    reset_rows(state);
    state->lrc.count = 0;
    int fd = orig_open(path, O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC, 0);
    if (fd < 0) return;
    /* Linux MIPS O32 struct stat64 st_mode is word 6, as in the EQ FIFO check. */
    uint32_t st[32];
    if (orig_fstat64(fd, st) < 0 || (st[6] & 0170000u) != 0100000u) {
        orig_close(fd);
        return;
    }
    char *buffer = orig_malloc(LRC_MAX_FILE + 1);
    if (buffer) {
        unsigned used = 0;
        int read_failed = 0;
        while (used <= LRC_MAX_FILE) {
            int n = orig_read(fd, buffer + used, LRC_MAX_FILE + 1 - used);
            if (n < 0) { read_failed = 1; break; }
            if (!n) break;
            used += (unsigned)n;
        }
        if (!read_failed && used && used <= LRC_MAX_FILE) {
            buffer[used] = 0;
            lrc_parse(&state->lrc, buffer);
        }
        orig_free(buffer);
    }
    orig_close(fd);
}

static struct Surface *render_line(void *font, const char *text, uint32_t color) {
    if (!*text) return 0;
    char fit[LRC_LINE_BYTES];
    unsigned len = 0;
    while (text[len]) {
        fit[len] = text[len];
        len++;
    }
    fit[len] = 0;
    int w, h;
    if (orig_measure(font, fit, &w, &h) < 0) return 0;
    while (w > 362 && len) {
        len--;
        while (len && ((unsigned char)fit[len] & 0xc0u) == 0x80u) len--;
        fit[len] = 0;
        if (orig_measure(font, fit, &w, &h) < 0) return 0;
    }
    if (!len || h > 31) return 0;
    return orig_render(font, fit, color);
}

static void draw_lyrics(struct Surface *screen) {
    const char *track = (const char *)(uintptr_t)STOCK32(0x444a80u);
    unsigned seconds = STOCK32(0x444cb8u);
    void *font = (void *)(uintptr_t)STOCK32(0x444b04u);
    if (!screen || !screen->format || screen->width < 400 || screen->height < 360 ||
        !font || !track || !STOCK32(0x444cbcu) || seconds > 600000u ||
        *(const unsigned *)(track + 0x338)) return; /* CUE subtracks have different timing. */
    char path[LRC_PATH_BYTES];
    if (!lrc_path(path, sizeof path, track)) return;

    struct LyricsState *state = STATE_SLOT;
    if (!state) {
        state = orig_malloc(sizeof *state);
        if (!state) return;
        state->path[0] = 0;
        for (unsigned i = 0; i < 3; i++) state->rows[i] = 0;
        STATE_SLOT = state;
    }
    if (!same(state->path, path)) load(state, path);
    if (!state->lrc.count) return;
    int current = lrc_at(&state->lrc, (int)seconds * 1000);
    if (current != state->rendered_line || font != state->rendered_font) {
        reset_rows(state);
        state->rendered_line = current;
        state->rendered_font = font;
        state->rows[0] = render_line(font, lrc_text(&state->lrc, current - 1), 0x00bec4c2);
        state->rows[1] = render_line(font, lrc_text(&state->lrc, current), 0x00bdecff);
        state->rows[2] = render_line(font, lrc_text(&state->lrc, current + 1), 0x00bec4c2);
    }
    if (!state->rows[0] && !state->rows[1] && !state->rows[2]) return;
    struct Rect panel = {12, 119, 376, 124};
    orig_fill_rect(screen, &panel, orig_maprgb(screen->format, 23, 29, 34));
    for (unsigned i = 0; i < 3; i++) {
        struct Surface *surface = state->rows[i];
        if (surface) {
            struct Rect dst = {(int16_t)((400 - surface->width) / 2),
                               (int16_t)(126 + i * 36 + (32 - surface->height) / 2), 0, 0};
            orig_upper_blit(surface, 0, screen, &dst);
        }
    }
}

int lyrics_flip_c(struct Surface *screen) {
    draw_lyrics(screen);
    return orig_flip(screen);
}
