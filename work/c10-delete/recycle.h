#ifndef C10_RECYCLE_H
#define C10_RECYCLE_H

#define C10_RECYCLE_FOLDER ".c10-recycle"
#define C10_RECYCLE_SUFFIX ".deleted"
#define C10_RECYCLE_PATH_CAPACITY 4096

enum c10_recycle_kind {
    C10_RECYCLE_MISSING,
    C10_RECYCLE_FILE,
    C10_RECYCLE_DIRECTORY,
    C10_RECYCLE_OTHER,
    C10_RECYCLE_ERROR
};

enum c10_recycle_result {
    C10_RECYCLE_OK,
    C10_RECYCLE_INVALID,
    C10_RECYCLE_UNAVAILABLE,
    C10_RECYCLE_CONFLICT,
    C10_RECYCLE_IO_ERROR
};

struct c10_recycle_io {
    /* Use lstat semantics. Report symbolic links as C10_RECYCLE_OTHER. */
    enum c10_recycle_kind (*kind)(void *context, const char *path);
    int (*make_directory)(void *context, const char *path);
    /* Return 0 after a same-filesystem rename. Preserve both files on conflict. */
    int (*rename_file)(void *context, const char *source, const char *destination);
};

/* Check the stock mount, absolute path syntax, and audio filename extension. */
int c10_recycle_is_song(const char *storage_root, const char *source_path);

/* Move one existing song from /mnt/memory or /mnt/mmc to the hidden recycle tree.
   The source path is absolute. Serialize operations that change either path. */
enum c10_recycle_result c10_recycle_move(const struct c10_recycle_io *io,
                                        void *context,
                                        const char *storage_root,
                                        const char *source_path);

#endif
