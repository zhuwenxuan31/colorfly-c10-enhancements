#include "lrc.h"

static int begins(const char *text, const char *prefix) {
    while (*prefix) if (*text++ != *prefix++) return 0;
    return 1;
}

int lrc_path(char *out, unsigned size, const char *track) {
    if (!track || (!begins(track, "/mnt/mmc/") && !begins(track, "/mnt/memory/"))) return 0;
    unsigned dot = 0, base = 0, i = 0;
    while (i < size && track[i]) {
        if (track[i] == '/') {
            if ((i - base == 1 && track[base] == '.') ||
                (i - base == 2 && track[base] == '.' && track[base + 1] == '.')) return 0;
            base = i + 1;
            dot = 0;
        } else if (track[i] == '.') {
            dot = i;
        }
        i++;
    }
    if (i == size || dot <= base || dot + 1 == i || size - dot < 5) return 0;
    for (i = 0; i < dot; i++) out[i] = track[i];
    for (unsigned j = 0; j < 5; j++) out[i + j] = ".lrc"[j];
    return 1;
}

unsigned lrc_char_bytes(const char *p) {
    unsigned ch = (unsigned char)p[0];
    if (ch == 0) return 0;
    if (ch < 0x80) return 1;
    unsigned bytes = ch >= 0xc2 && ch <= 0xdf ? 2 :
                     ch >= 0xe0 && ch <= 0xef ? 3 :
                     ch >= 0xf0 && ch <= 0xf4 ? 4 : 0;
    if (!bytes) return 0;
    for (unsigned i = 1; i < bytes; i++) {
        unsigned c = (unsigned char)p[i];
        if ((c & 0xc0u) != 0x80u) return 0;
        if (i == 1 && ((ch == 0xe0 && c < 0xa0) || (ch == 0xed && c >= 0xa0) ||
                       (ch == 0xf0 && c < 0x90) || (ch == 0xf4 && c >= 0x90))) return 0;
    }
    return bytes;
}

static int number(const char **p, int maxdigits, int *value) {
    int n = 0, digits = 0;
    while (digits < maxdigits && **p >= '0' && **p <= '9') {
        n = n * 10 + (*(*p)++ - '0');
        digits++;
    }
    *value = n;
    return digits;
}

static int timestamp(const char **p, int *ms) {
    const char *s = *p;
    int min, sec, fraction = 0;
    if (*s++ != '[' || !number(&s, 4, &min) || *s++ != ':' ||
        !number(&s, 2, &sec) || sec >= 60) return 0;
    if (*s == '.' || *s == ':') {
        s++;
        int digits = number(&s, 3, &fraction);
        if (!digits) return 0;
        if (digits == 1) fraction *= 100;
        if (digits == 2) fraction *= 10;
    }
    if (*s++ != ']') return 0;
    *p = s;
    *ms = (min * 60 + sec) * 1000 + fraction;
    return 1;
}

static void set_offset(struct Lrc *lrc, const char *s) {
    int value, sign = 1;
    if (*s == '-' || *s == '+') {
        if (*s == '-') sign = -1;
        s++;
    }
    if (number(&s, 7, &value) && *s == ']' && value <= 3600000) lrc->offset = sign * value;
}

static void add_line(struct Lrc *lrc, const char *start, const char *end,
                     const int *stamps, unsigned count) {
    unsigned len = 0;
    for (const char *p = start; p < end;) {
        unsigned size = lrc_char_bytes(p);
        if (!size || size > (unsigned)(end - p) || ((unsigned char)*p < ' ' && *p != '\t')) return;
        p += size;
        if (len + size < LRC_LINE_BYTES && len == (unsigned)(p - start - size)) len += size;
    }
    if (!len || lrc->used + len + 1 > LRC_TEXT_BYTES) return;
    unsigned text = lrc->used;
    for (unsigned i = 0; i < len; i++) lrc->text[text + i] = start[i] == '\t' ? ' ' : start[i];
    lrc->text[text + len] = 0;
    lrc->used += len + 1;
    for (unsigned j = 0; j < count && lrc->count < LRC_MAX_LINES; j++) {
        unsigned i = lrc->count++;
        while (i && lrc->lines[i - 1].time > stamps[j]) {
            lrc->lines[i].time = lrc->lines[i - 1].time;
            lrc->lines[i].text = lrc->lines[i - 1].text;
            i--;
        }
        lrc->lines[i].time = stamps[j];
        lrc->lines[i].text = text;
    }
}

int lrc_parse(struct Lrc *lrc, const char *input) {
    lrc->count = lrc->used = 0;
    lrc->offset = 0;
    if (begins(input, "\xef\xbb\xbf")) input += 3;
    while (*input) {
        const char *start = input, *end = start;
        while (*end && *end != '\n') end++;
        input = *end ? end + 1 : end;
        while (end > start && (end[-1] == '\r' || end[-1] == ' ' || end[-1] == '\t')) end--;
        if (begins(start, "[offset:")) {
            set_offset(lrc, start + 8);
            continue;
        }
        int stamps[24], ms;
        unsigned count = 0;
        while (start < end && timestamp(&start, &ms)) {
            if (count < sizeof(stamps) / sizeof(stamps[0])) stamps[count++] = ms;
        }
        while (start < end && (*start == ' ' || *start == '\t')) start++;
        if (count) add_line(lrc, start, end, stamps, count);
    }
    return lrc->count != 0;
}

int lrc_at(const struct Lrc *lrc, int position) {
    unsigned min = 0, max = lrc->count;
    while (min < max) {
        unsigned mid = min + (max - min) / 2;
        if (lrc->lines[mid].time - lrc->offset <= position) min = mid + 1;
        else max = mid;
    }
    return (int)min - 1;
}

const char *lrc_text(const struct Lrc *lrc, int index) {
    if (index < 0 || (unsigned)index >= lrc->count) return "";
    return lrc->text + lrc->lines[index].text;
}
