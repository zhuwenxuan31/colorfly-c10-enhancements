#ifndef C10_LRC_H
#define C10_LRC_H

#define LRC_MAX_FILE 32768
#define LRC_MAX_LINES 384
#define LRC_TEXT_BYTES 24576
#define LRC_PATH_BYTES 512
#define LRC_LINE_BYTES 192

struct LrcLine {
    int time;
    unsigned text;
};

struct Lrc {
    unsigned count;
    unsigned used;
    int offset;
    struct LrcLine lines[LRC_MAX_LINES];
    char text[LRC_TEXT_BYTES];
};

int lrc_path(char *out, unsigned size, const char *track);
int lrc_parse(struct Lrc *lrc, const char *input);
int lrc_at(const struct Lrc *lrc, int position);
const char *lrc_text(const struct Lrc *lrc, int index);
unsigned lrc_char_bytes(const char *p);
#endif
