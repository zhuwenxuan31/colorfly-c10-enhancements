#define _DARWIN_C_SOURCE
#define _XOPEN_SOURCE 700

#include "recycle.h"

#include <assert.h>
#include <errno.h>
#include <ftw.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

struct fixture {
    char root[80];
    int fail_rename;
    int fail_mkdir;
    int race_destination;
    unsigned renames;
};

static void fixture_path(const struct fixture *fixture, const char *path,
                         char output[C10_RECYCLE_PATH_CAPACITY + 80])
{
    int length = snprintf(output, C10_RECYCLE_PATH_CAPACITY + 80, "%s%s",
                          fixture->root, path);
    assert(length > 0 && length < C10_RECYCLE_PATH_CAPACITY + 80);
}

static void put_file(const struct fixture *fixture, const char *path,
                     const char *content)
{
    char full[C10_RECYCLE_PATH_CAPACITY + 80];
    FILE *file;

    fixture_path(fixture, path, full);
    file = fopen(full, "w");
    assert(file);
    assert(fputs(content, file) >= 0);
    assert(fclose(file) == 0);
}

static void check_content(const struct fixture *fixture, const char *path,
                          const char *expected)
{
    char full[C10_RECYCLE_PATH_CAPACITY + 80];
    char content[64];
    FILE *file;

    fixture_path(fixture, path, full);
    file = fopen(full, "r");
    assert(file);
    assert(fgets(content, sizeof(content), file));
    assert(strcmp(content, expected) == 0);
    assert(fclose(file) == 0);
}

static enum c10_recycle_kind kind(void *context, const char *path)
{
    const struct fixture *fixture = context;
    char full[C10_RECYCLE_PATH_CAPACITY + 80];
    struct stat status;

    fixture_path(fixture, path, full);
    if (lstat(full, &status) != 0)
        return errno == ENOENT ? C10_RECYCLE_MISSING : C10_RECYCLE_ERROR;
    if (S_ISREG(status.st_mode))
        return C10_RECYCLE_FILE;
    if (S_ISDIR(status.st_mode))
        return C10_RECYCLE_DIRECTORY;
    return C10_RECYCLE_OTHER;
}

static int make_directory(void *context, const char *path)
{
    const struct fixture *fixture = context;
    char full[C10_RECYCLE_PATH_CAPACITY + 80];

    fixture_path(fixture, path, full);
    return fixture->fail_mkdir ? -1 : mkdir(full, 0700);
}

static int rename_file(void *context, const char *source, const char *destination)
{
    struct fixture *fixture = context;
    char from[C10_RECYCLE_PATH_CAPACITY + 80];
    char to[C10_RECYCLE_PATH_CAPACITY + 80];

    ++fixture->renames;
    if (fixture->fail_rename)
        return -1;
    if (fixture->race_destination)
        put_file(fixture, destination, "arrived");
    if (kind(context, destination) != C10_RECYCLE_MISSING)
        return -1;
    fixture_path(fixture, source, from);
    fixture_path(fixture, destination, to);
    return rename(from, to);
}

static const struct c10_recycle_io io = { kind, make_directory, rename_file };

static void setup(struct fixture *fixture)
{
    memset(fixture, 0, sizeof(*fixture));
    strcpy(fixture->root, "/tmp/c10-recycle-test-XXXXXX");
    assert(mkdtemp(fixture->root));
    assert(make_directory(fixture, "/mnt") == 0);
    assert(make_directory(fixture, "/mnt/memory") == 0);
    assert(make_directory(fixture, "/mnt/mmc") == 0);
    assert(make_directory(fixture, "/mnt/memory/Music") == 0);
    assert(make_directory(fixture, "/mnt/memory/Music/合辑") == 0);
    put_file(fixture, "/mnt/memory/Music/合辑/A.FLAC", "track data");
}

static int remove_entry(const char *path, const struct stat *status, int type,
                        struct FTW *walk)
{
    (void) status;
    (void) type;
    (void) walk;
    return remove(path);
}

static void cleanup(struct fixture *fixture)
{
    assert(nftw(fixture->root, remove_entry, 12, FTW_PHYS | FTW_DEPTH) == 0);
}

static void create_symlink(struct fixture *fixture, const char *target,
                           const char *path)
{
    char real_target[C10_RECYCLE_PATH_CAPACITY + 80];
    char real_path[C10_RECYCLE_PATH_CAPACITY + 80];

    fixture_path(fixture, target, real_target);
    fixture_path(fixture, path, real_path);
    assert(symlink(real_target, real_path) == 0);
}

static const char source[] = "/mnt/memory/Music/合辑/A.FLAC";
static const char destination[] = "/mnt/memory/" C10_RECYCLE_FOLDER
                                  "/Music/合辑/A.FLAC" C10_RECYCLE_SUFFIX;

static void preserves_contents_and_original_path(struct fixture *fixture)
{
    assert(c10_recycle_move(&io, fixture, "/mnt/memory", source) == C10_RECYCLE_OK);
    assert(c10_recycle_is_song("/mnt/memory", source));
    assert(!c10_recycle_is_song("/mnt/memory", destination));
    assert(c10_recycle_is_song("/mnt/memory", "/mnt/memory/Track.DSF"));
    assert(c10_recycle_is_song("/mnt/memory", "/mnt/memory/Track.DFF"));
    assert(c10_recycle_is_song("/mnt/memory", "/mnt/memory/Track.AIF"));
    assert(kind(fixture, source) == C10_RECYCLE_MISSING);
    check_content(fixture, destination, "track data");
    assert(kind(fixture, "/mnt/mmc/" C10_RECYCLE_FOLDER) == C10_RECYCLE_MISSING);

    put_file(fixture, "/mnt/mmc/B.ape", "card track");
    assert(c10_recycle_move(&io, fixture, "/mnt/mmc", "/mnt/mmc/B.ape") == C10_RECYCLE_OK);
    check_content(fixture, "/mnt/mmc/" C10_RECYCLE_FOLDER "/B.ape" C10_RECYCLE_SUFFIX,
                  "card track");
}

static void rejects_collision_and_keeps_both_files(struct fixture *fixture)
{
    assert(make_directory(fixture, "/mnt/memory/" C10_RECYCLE_FOLDER) == 0);
    assert(make_directory(fixture, "/mnt/memory/" C10_RECYCLE_FOLDER "/Music") == 0);
    assert(make_directory(fixture, "/mnt/memory/" C10_RECYCLE_FOLDER "/Music/合辑") == 0);
    put_file(fixture, destination, "older track");
    assert(c10_recycle_move(&io, fixture, "/mnt/memory", source) == C10_RECYCLE_CONFLICT);
    check_content(fixture, source, "track data");
    check_content(fixture, destination, "older track");
    assert(fixture->renames == 0);
}

static void rejects_paths_outside_the_original_song_tree(struct fixture *fixture)
{
    const char *invalid[] = {
        "/mnt/memory/../mmc/B.flac",
        "/mnt/memory2/Music/合辑/A.FLAC",
        "/mnt/memory/Music/./合辑/A.FLAC",
        "/mnt/memory//Music/合辑/A.FLAC",
        "/mnt/memory/Music/合辑/A.FLAC/",
        "/mnt/memory/Music /合辑/A.FLAC",
        "/mnt/memory/Music\\合辑/A.FLAC",
        "/mnt/memory/Music:A.FLAC",
        "/mnt/memory/" C10_RECYCLE_FOLDER "/A.FLAC",
        "/mnt/memory/.C10-Recycle/A.FLAC",
        "/mnt/memory/C10-RE~1/A.FLAC",
        "/mnt/memory/C10-RECY/A.FLAC",
        "/mnt/memory/C12AF0~3/A.FLAC",
        "/mnt/mmc/B.flac",
        "/mnt/memory/Cover.JPG",
        "/mnt/memory/Album.cue",
        "Music/合辑/A.FLAC"
    };
    size_t index;

    put_file(fixture, "/mnt/mmc/B.flac", "card track");
    put_file(fixture, "/mnt/memory/Cover.JPG", "cover");
    for (index = 0; index < sizeof(invalid) / sizeof(invalid[0]); ++index) {
        assert(!c10_recycle_is_song("/mnt/memory", invalid[index]));
        assert(c10_recycle_move(&io, fixture, "/mnt/memory", invalid[index])
               == C10_RECYCLE_INVALID);
    }
    assert(c10_recycle_move(&io, fixture, "/mnt", source) == C10_RECYCLE_INVALID);
    assert(kind(fixture, "/mnt/memory/" C10_RECYCLE_FOLDER) == C10_RECYCLE_MISSING);
    assert(fixture->renames == 0);
    check_content(fixture, source, "track data");
}

static void rejects_symlinks_and_non_files(struct fixture *fixture)
{
    create_symlink(fixture, "/mnt/memory/Music", "/mnt/mmc/Music");
    create_symlink(fixture, source, "/mnt/memory/Link.ape");
    assert(make_directory(fixture, "/mnt/memory/Folder.FLAC") == 0);
    assert(c10_recycle_move(&io, fixture, "/mnt/mmc", "/mnt/mmc/Music/合辑/A.FLAC")
           == C10_RECYCLE_INVALID);
    assert(c10_recycle_move(&io, fixture, "/mnt/memory", "/mnt/memory/Link.ape")
           == C10_RECYCLE_INVALID);
    assert(c10_recycle_move(&io, fixture, "/mnt/memory", "/mnt/memory/Folder.FLAC")
           == C10_RECYCLE_INVALID);
    create_symlink(fixture, "/mnt/mmc", "/mnt/memory/" C10_RECYCLE_FOLDER);
    assert(c10_recycle_move(&io, fixture, "/mnt/memory", source) == C10_RECYCLE_CONFLICT);
    assert(fixture->renames == 0);
    check_content(fixture, source, "track data");
}

static void failed_rename_can_be_retried(struct fixture *fixture)
{
    fixture->fail_rename = 1;
    assert(c10_recycle_move(&io, fixture, "/mnt/memory", source) == C10_RECYCLE_IO_ERROR);
    check_content(fixture, source, "track data");
    assert(kind(fixture, destination) == C10_RECYCLE_MISSING);
    fixture->fail_rename = 0;
    assert(c10_recycle_move(&io, fixture, "/mnt/memory", source) == C10_RECYCLE_OK);
    check_content(fixture, destination, "track data");
}

static void fails_safely_when_storage_is_unavailable(struct fixture *fixture)
{
    fixture->fail_mkdir = 1;
    assert(c10_recycle_move(&io, fixture, "/mnt/memory", source) == C10_RECYCLE_IO_ERROR);
    assert(c10_recycle_move(&io, fixture, "/mnt/memory", "/mnt/memory/Missing.FLAC")
           == C10_RECYCLE_UNAVAILABLE);
    assert(kind(fixture, "/mnt/memory/" C10_RECYCLE_FOLDER) == C10_RECYCLE_MISSING);
    assert(fixture->renames == 0);
    check_content(fixture, source, "track data");
}

static void retains_new_destination_and_reports_collision(struct fixture *fixture)
{
    fixture->race_destination = 1;
    assert(c10_recycle_move(&io, fixture, "/mnt/memory", source) == C10_RECYCLE_CONFLICT);
    check_content(fixture, source, "track data");
    check_content(fixture, destination, "arrived");
}

static void refuses_to_truncate_a_filename(struct fixture *fixture)
{
    char name[256];
    char path[sizeof("/mnt/memory/") + sizeof(name)];

    memset(name, 'a', sizeof(name));
    strcpy(name + sizeof(name) - sizeof(".mp3"), ".mp3");
    assert(snprintf(path, sizeof(path), "/mnt/memory/%s", name) > 0);
    put_file(fixture, path, "long name");
    assert(c10_recycle_move(&io, fixture, "/mnt/memory", path) == C10_RECYCLE_IO_ERROR);
    check_content(fixture, path, "long name");
    assert(fixture->renames == 0);
}

int main(void)
{
    void (*tests[])(struct fixture *) = {
        preserves_contents_and_original_path,
        rejects_collision_and_keeps_both_files,
        rejects_paths_outside_the_original_song_tree,
        rejects_symlinks_and_non_files,
        failed_rename_can_be_retried,
        fails_safely_when_storage_is_unavailable,
        retains_new_destination_and_reports_collision,
        refuses_to_truncate_a_filename
    };
    struct fixture fixture;
    size_t index;

    for (index = 0; index < sizeof(tests) / sizeof(tests[0]); ++index) {
        setup(&fixture);
        tests[index](&fixture);
        cleanup(&fixture);
    }
    puts("8 recycle fixture tests passed");
    return 0;
}
