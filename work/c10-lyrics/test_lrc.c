#include "lrc.h"
#include <assert.h>
#include <string.h>

static struct Lrc lyrics;

int main(void) {
    const char *sample = "\xef\xbb\xbf[ar:测试]\r\n[00:08.00][00:02.50]第二句\r\n"
                         "[00:00.00]开场\n[00:05.100]第三句\n[offset:+100]\n"
                         "[00:69]坏时间\n[xx:02]坏行\n";
    assert(lrc_parse(&lyrics, sample));
    assert(lyrics.count == 4);
    assert(lrc_at(&lyrics, 2399) == 0);
    assert(lrc_at(&lyrics, 2400) == 1);
    assert(!strcmp(lrc_text(&lyrics, 1), "第二句"));
    assert(lrc_at(&lyrics, 5000) == 2);
    assert(lrc_at(&lyrics, 8000) == 3);
    assert(lrc_at(&lyrics, 0) == 0);
    assert(lrc_parse(&lyrics, "[00:01]一\n[00:02]二"));
    assert(lrc_at(&lyrics, 999) == -1);
    assert(lrc_at(&lyrics, 1000) == 0);
    assert(lrc_parse(&lyrics, "[offset:-250]\n[00:01.1]中文"));
    assert(lrc_at(&lyrics, 1349) == -1);
    assert(lrc_at(&lyrics, 1350) == 0);
    assert(!lrc_parse(&lyrics, "[00:01]\xf5\x80\x80\x80"));
    assert(!lrc_parse(&lyrics, "[00:01]\xe4\xb8"));
    assert(!lrc_parse(&lyrics, "[ti:无歌词]"));
    char path[408];
    assert(lrc_path(path, sizeof path, "/mnt/memory/中文/音乐.FLAC"));
    assert(!strcmp(path, "/mnt/memory/中文/音乐.lrc"));
    assert(lrc_path(path, sizeof path, "/mnt/mmc/音乐.mp3"));
    assert(!lrc_path(path, 10, "/mnt/mmc/音乐.mp3"));
    assert(!lrc_path(path, sizeof path, "/mnt/mmc/目录.mp3/没有扩展名"));
    assert(!lrc_path(path, sizeof path, "/mnt/mmc/../other/song.mp3"));
    assert(!lrc_path(path, sizeof path, "/mnt/mmc/.hidden"));
    assert(!lrc_path(path, sizeof path, "/etc/passwd"));
    return 0;
}
