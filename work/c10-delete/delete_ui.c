#include "gesture.h"
#include "recycle.h"
#include <stdint.h>

#define STOCK32(address) (*(volatile uint32_t *)(uintptr_t)(address))
#define STATE (*(struct DeleteState **)(uintptr_t)0x446ff4u)

enum { PLAY = C10_DIRECTORY_PLAY_KEY, PATH_BYTES = 512, FILE_LIST = 0, STOPPED = 2 };

struct DeleteState {
    struct c10_delete_gesture gesture;
    char path[PATH_BYTES];
    const char *message;
    uint32_t shown_at;
};

struct Rect { int16_t x, y; uint16_t w, h; };
struct Surface { uint32_t flags; void *format; int width, height; };

extern void *delete_malloc(unsigned size);
extern unsigned delete_ticks(void);
extern void delete_original_down(int key, int repeated);
extern int delete_lstat64(const char *path, void *record);
extern int delete_mkdir(const char *path, unsigned mode);
extern int delete_rename(const char *source, const char *destination);
extern uint32_t delete_maprgb(void *format, unsigned red, unsigned green, unsigned blue);
extern int delete_fill(void *screen, struct Rect *rect, uint32_t color);
extern struct Surface *delete_text(void *font, const char *text, uint32_t color);
extern int delete_blit(void *src, void *src_rect, void *dst, struct Rect *dst_rect);
extern void delete_free_surface(void *surface);
extern int delete_flip(void *screen);

static enum c10_recycle_kind classify(void *context, const char *path) {
    (void)context;
    uint32_t stat[40] __attribute__((aligned(8)));
    int status = delete_lstat64(path, stat);
    if (status == -2) return C10_RECYCLE_MISSING;
    if (status) return C10_RECYCLE_ERROR;
    unsigned mode = stat[6] & 0170000u;
    if (mode == 0100000u) return C10_RECYCLE_FILE;
    if (mode == 0040000u) return C10_RECYCLE_DIRECTORY;
    return C10_RECYCLE_OTHER;
}

static int mkdir_callback(void *context, const char *path) {
    (void)context;
    return delete_mkdir(path, 0700);
}

static int rename_callback(void *context, const char *source, const char *destination) {
    (void)context;
    return delete_rename(source, destination);
}

static const struct c10_recycle_io io = { classify, mkdir_callback, rename_callback };

static const char *song_root(const char *path) {
    if (c10_recycle_is_song("/mnt/memory", path)) return "/mnt/memory";
    if (c10_recycle_is_song("/mnt/mmc", path)) return "/mnt/mmc";
    return 0;
}

static void copy_path(char dst[PATH_BYTES], const char *src) {
    unsigned i = 0;
    do { dst[i] = src[i]; } while (src[i] && ++i < PATH_BYTES - 1u);
    dst[i] = 0;
}

static int same_path(const char *a, const char *b) {
    unsigned i = 0;
    while (i < PATH_BYTES - 1u && a[i] && a[i] == b[i]) i++;
    return a[i] == b[i];
}

static const char *selected_file(void) {
    if (STOCK32(0x444b34u) != FILE_LIST) return 0;
    uintptr_t node = STOCK32(0x444aa0u); /* g_browse_node_list */
    unsigned depth = 0;
    while (node && STOCK32(node + 0x50u)) {
        if (++depth == 128u) return 0;
        node = STOCK32(node + 0x50u);
    }
    if (!node) return 0;
    unsigned row = STOCK32(node + 8u);
    if (row >= 8u || !STOCK32(node + 4u * (row + 4u))) return 0;
    uintptr_t song = STOCK32(node + 4u * (row + 12u));
    if (!song || STOCK32(song + 0x334u) || STOCK32(song + 0x338u)) return 0;
    const char *path = (const char *)song;
    for (unsigned i = 0; i < PATH_BYTES; i++) {
        if (path[i] == 0) return song_root(path) ? path : 0;
    }
    return 0;
}

static struct DeleteState *allocate_state(void) {
    struct DeleteState *state = STATE;
    if (state) return state;
    state = delete_malloc(sizeof(*state));
    if (!state) return 0;
    state->gesture.started = 0;
    state->gesture.holding = 0;
    state->gesture.screen = C10_DELETE_CLOSED;
    state->gesture.selected = 0;
    state->path[0] = 0;
    state->message = 0;
    state->shown_at = 0;
    STATE = state;
    return state;
}

int c10_delete_down_c(int key, int repeated) {
    if (STOCK32(0x444b34u) != FILE_LIST) return 0;
    struct DeleteState *state = STATE;
    if (state && (state->gesture.holding || state->gesture.screen != C10_DELETE_CLOSED))
        return c10_delete_press(&state->gesture, key, repeated, 0, delete_ticks()) != C10_DELETE_STOCK;
    if (key != PLAY || repeated) return 0;
    const char *path = selected_file();
    if (!path || classify(0, path) != C10_RECYCLE_FILE) return 0;
    state = allocate_state();
    if (!state) return 0;
    copy_path(state->path, path);
    state->message = 0;
    return c10_delete_press(&state->gesture, key, repeated, 1, delete_ticks()) != C10_DELETE_STOCK;
}

static const char *try_move(const char *path) {
    const char *selected = selected_file();
    if (!selected || !same_path(path, selected)) return "选中的歌曲已变更";
    const char *playing = (const char *)(uintptr_t)STOCK32(0x444a80u);
    if (playing && STOCK32(0x444440u) != STOPPED && same_path(path, playing))
        return "请停止这首歌后重试";
    const char *root = song_root(path);
    if (!root) return "歌曲文件不可用";
    switch (c10_recycle_move(&io, 0, root, path)) {
        case C10_RECYCLE_OK: return "已移到回收站，重开机刷新目录";
        case C10_RECYCLE_CONFLICT: return "回收站有同名文件";
        case C10_RECYCLE_UNAVAILABLE: return "歌曲文件不可用";
        default: return "移动失败，歌曲保留";
    }
}

int c10_delete_up_c(int key, int repeated) {
    (void)repeated;
    struct DeleteState *state = STATE;
    if (!state || (!state->gesture.holding && state->gesture.screen == C10_DELETE_CLOSED)) return 0;
    if (STOCK32(0x444b34u) != FILE_LIST) {
        unsigned held = state->gesture.holding;
        state->gesture.holding = 0;
        state->gesture.screen = C10_DELETE_CLOSED;
        return held && key == PLAY;
    }
    unsigned now = delete_ticks();
    enum c10_delete_action action = c10_delete_release(&state->gesture, key, now);
    if (action == C10_DELETE_SHORT_PLAY) {
        const char *path = selected_file();
        if (!path || !same_path(state->path, path)) return 1;
        delete_original_down(key, 0);
        return 0;
    }
    if (action == C10_DELETE_MOVE) {
        state->message = try_move(state->path);
        state->shown_at = now;
    }
    return action != C10_DELETE_STOCK;
}

static void box(struct Surface *screen, int x, int y, unsigned w, unsigned h, unsigned color) {
    struct Rect area = { (int16_t)x, (int16_t)y, (uint16_t)w, (uint16_t)h };
    delete_fill(screen, &area, color);
}

static void label(struct Surface *screen, int x, int y, const char *value, unsigned color) {
    void *font = (void *)(uintptr_t)STOCK32(0x444b04u);
    if (!font) return;
    struct Surface *text = delete_text(font, value, color);
    if (!text) return;
    struct Rect holder = { (int16_t)x, (int16_t)y, 0, 0 };
    delete_blit(text, 0, screen, &holder);
    delete_free_surface(text);
}

static void song_name(char title[64], const char *path) {
    const char *base = path;
    for (const char *next = path; *next; next++) if (*next == '/') base = next + 1;
    unsigned size = 0;
    while (base[size] && size < 48) size++;
    if (base[size]) {
        while (size && ((unsigned char)base[size] & 0xc0u) == 0x80u) size--;
        for (unsigned i = 0; i < size; i++) title[i] = base[i];
        title[size++] = '.';
        title[size++] = '.';
        title[size++] = '.';
    } else {
        for (unsigned i = 0; i < size; i++) title[i] = base[i];
    }
    title[size] = 0;
}

int c10_delete_flip_c(struct Surface *screen) {
    struct DeleteState *state = STATE;
    if (!state || STOCK32(0x444b34u) != FILE_LIST || !screen || !screen->format ||
        screen->width < 400 || screen->height < 360) return delete_flip(screen);
    if (!state->gesture.holding && state->gesture.screen == C10_DELETE_CLOSED && !state->message)
        return delete_flip(screen);
    unsigned now = delete_ticks();
    c10_delete_tick(&state->gesture, now);
    unsigned bg = delete_maprgb(screen->format, 30, 30, 30);
    if (state->gesture.screen != C10_DELETE_CLOSED) {
        char title[64];
        song_name(title, state->path);
        box(screen, 22, 87, 356, 184, bg);
        box(screen, 29, 175 + 37 * (int)state->gesture.selected, 342, 35,
            delete_maprgb(screen->format, 87, 68, 35));
        label(screen, 40, 100, "歌曲操作", 0x00bdecffu);
        label(screen, 40, 135, title, 0x00ffffffu);
        label(screen, 40, 181, "取消", 0x00ffffffu);
        label(screen, 40, 218, "删除", 0x00ffffffu);
        label(screen, 124, 218, "移到回收站", 0x00d6d6d6u);
    } else if (state->message) {
        if (now - state->shown_at < 4500) {
            box(screen, 14, 300, 372, 45, bg);
            label(screen, 28, 311, state->message, 0x00ffffffu);
        } else {
            state->message = 0;
        }
    }
    return delete_flip(screen);
}
