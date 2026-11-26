#include "recycle.h"

#include <stddef.h>

/* Match the stock file browser's audio format table. */
static const char *const audio_extensions[] = {
    ".flac", ".mp3", ".wav", ".ape", ".dsf", ".dff", ".aif", ".ogg",
    ".wma", ".aac", ".m4a"
};

static char ascii_lower(char character)
{
    if (character >= 'A' && character <= 'Z')
        return (char) (character + ('a' - 'A'));
    return character;
}

static int equal_ascii(const char *span, size_t length, const char *literal)
{
    size_t index;

    for (index = 0; index < length; ++index) {
        if (!literal[index] || ascii_lower(span[index]) != ascii_lower(literal[index]))
            return 0;
    }
    return literal[length] == '\0';
}

static size_t stock_root_length(const char *root)
{
    const char *const roots[] = { "/mnt/memory", "/mnt/mmc" };
    size_t index;

    if (!root)
        return 0;
    for (index = 0; index < sizeof(roots) / sizeof(roots[0]); ++index) {
        size_t length = 0;

        while (roots[index][length] && roots[index][length] == root[length])
            ++length;
        if (roots[index][length] == '\0' && root[length] == '\0')
            return length;
    }
    return 0;
}

static int ascii_hex(char character)
{
    character = ascii_lower(character);
    return (character >= '0' && character <= '9') ||
           (character >= 'a' && character <= 'f');
}

static int is_recycle_component(const char *name, size_t length)
{
    if (equal_ascii(name, length, C10_RECYCLE_FOLDER))
        return 1;

    /* VFAT may also expose the recycle tree through an 8.3 alias. */
    if (length != 8)
        return 0;
    if (equal_ascii(name, length, "c10-recy"))
        return 1;
    if (name[6] != '~' || name[7] < '1' || name[7] > '9')
        return 0;
    return equal_ascii(name, 6, "c10-re") ||
           (ascii_lower(name[0]) == 'c' && name[1] == '1' &&
            ascii_hex(name[2]) && ascii_hex(name[3]) &&
            ascii_hex(name[4]) && ascii_hex(name[5]));
}

static int is_audio_name(const char *name, size_t length)
{
    size_t stem = length;
    size_t index;

    while (stem > 0 && name[stem - 1] != '.')
        --stem;
    if (stem <= 1)
        return 0;
    for (index = 0; index < sizeof(audio_extensions) / sizeof(audio_extensions[0]); ++index) {
        if (equal_ascii(name + stem - 1, length - stem + 1, audio_extensions[index]))
            return 1;
    }
    return 0;
}

static int valid_relative_song(const char *relative)
{
    const char *component = relative;
    size_t index;

    for (index = 0; ; ++index) {
        unsigned char character = (unsigned char) relative[index];

        if (character == '/' || character == '\0') {
            size_t length = (size_t) (relative + index - component);

            if (!length || relative[index - 1] == '.' || relative[index - 1] == ' ')
                return 0;
            if (component == relative && is_recycle_component(component, length))
                return 0;
            if (!character)
                return is_audio_name(component, length);
            component = relative + index + 1;
        } else if (character < ' ' || character == '\\' || character == ':' ||
                   character == '"' || character == '*' || character == '?' ||
                   character == '<' || character == '>' || character == '|') {
            return 0;
        }
    }
}

static const char *relative_song(const char *root, size_t root_length, const char *source)
{
    const size_t extra = sizeof(C10_RECYCLE_FOLDER) + sizeof(C10_RECYCLE_SUFFIX) - 1;
    size_t length;

    if (!root_length || !source)
        return NULL;
    for (length = 0; length < root_length; ++length) {
        if (source[length] != root[length])
            return NULL;
    }
    if (source[length] != '/')
        return NULL;
    for (++length; length < C10_RECYCLE_PATH_CAPACITY - extra; ++length) {
        if (!source[length]) {
            const char *relative = source + root_length + 1;

            return valid_relative_song(relative) ? relative : NULL;
        }
    }
    return NULL;
}

int c10_recycle_is_song(const char *storage_root, const char *source_path)
{
    return relative_song(storage_root, stock_root_length(storage_root), source_path) != NULL;
}

static char *append_string(char *end, const char *suffix)
{
    while (*suffix)
        *end++ = *suffix++;
    *end = '\0';
    return end;
}

static enum c10_recycle_result directory(const struct c10_recycle_io *io,
                                          void *context, const char *path, int create)
{
    enum c10_recycle_kind kind = io->kind(context, path);

    if (kind == C10_RECYCLE_MISSING && create) {
        io->make_directory(context, path);
        kind = io->kind(context, path);
    }
    if (kind == C10_RECYCLE_DIRECTORY)
        return C10_RECYCLE_OK;
    if (kind == C10_RECYCLE_ERROR)
        return C10_RECYCLE_IO_ERROR;
    if (kind == C10_RECYCLE_MISSING)
        return create ? C10_RECYCLE_IO_ERROR : C10_RECYCLE_UNAVAILABLE;
    return create ? C10_RECYCLE_CONFLICT : C10_RECYCLE_INVALID;
}

static enum c10_recycle_result append_tree(const struct c10_recycle_io *io,
                                            void *context, char *path, char **end,
                                            const char *relative, int create)
{
    while (*relative) {
        if (*relative == '/') {
            enum c10_recycle_result result;

            **end = '\0';
            result = directory(io, context, path, create);
            if (result != C10_RECYCLE_OK)
                return result;
        }
        **end = *relative++;
        ++*end;
    }
    **end = '\0';
    return C10_RECYCLE_OK;
}

enum c10_recycle_result c10_recycle_move(const struct c10_recycle_io *io,
                                        void *context, const char *storage_root,
                                        const char *source_path)
{
    char path[C10_RECYCLE_PATH_CAPACITY];
    size_t root_length = stock_root_length(storage_root);
    const char *relative = relative_song(storage_root, root_length, source_path);
    enum c10_recycle_result result;
    enum c10_recycle_kind kind;
    char *end;

    if (!relative || !io || !io->kind || !io->make_directory || !io->rename_file)
        return C10_RECYCLE_INVALID;
    result = directory(io, context, "/mnt", 0);
    if (result != C10_RECYCLE_OK)
        return result;
    result = directory(io, context, storage_root, 0);
    if (result != C10_RECYCLE_OK)
        return result;

    end = append_string(append_string(path, storage_root), "/");
    result = append_tree(io, context, path, &end, relative, 0);
    if (result != C10_RECYCLE_OK)
        return result;
    kind = io->kind(context, source_path);
    if (kind == C10_RECYCLE_MISSING)
        return C10_RECYCLE_UNAVAILABLE;
    if (kind == C10_RECYCLE_ERROR)
        return C10_RECYCLE_IO_ERROR;
    if (kind != C10_RECYCLE_FILE)
        return C10_RECYCLE_INVALID;

    end = append_string(path + root_length + 1, C10_RECYCLE_FOLDER);
    result = directory(io, context, path, 1);
    if (result != C10_RECYCLE_OK)
        return result;
    end = append_string(end, "/");
    result = append_tree(io, context, path, &end, relative, 1);
    if (result != C10_RECYCLE_OK)
        return result;
    append_string(end, C10_RECYCLE_SUFFIX);

    kind = io->kind(context, path);
    if (kind == C10_RECYCLE_ERROR)
        return C10_RECYCLE_IO_ERROR;
    if (kind != C10_RECYCLE_MISSING)
        return C10_RECYCLE_CONFLICT;
    if (io->rename_file(context, source_path, path) == 0)
        return C10_RECYCLE_OK;
    kind = io->kind(context, path);
    return kind == C10_RECYCLE_MISSING || kind == C10_RECYCLE_ERROR
           ? C10_RECYCLE_IO_ERROR : C10_RECYCLE_CONFLICT;
}
