#ifndef C10_DELETE_GESTURE_H
#define C10_DELETE_GESTURE_H

#include <stdint.h>

/* In the stock directory browser, right starts the selected song. */
enum { C10_DIRECTORY_PLAY_KEY = 106 };

enum c10_delete_screen { C10_DELETE_CLOSED, C10_DELETE_MENU };
enum c10_delete_action { C10_DELETE_STOCK, C10_DELETE_HANDLED, C10_DELETE_SHORT_PLAY, C10_DELETE_MOVE };

struct c10_delete_gesture {
    uint32_t started;
    unsigned holding;
    enum c10_delete_screen screen;
    unsigned selected;
};

enum c10_delete_action c10_delete_press(struct c10_delete_gesture *state, int key,
                                        int repeated, int eligible, uint32_t now);
enum c10_delete_action c10_delete_release(struct c10_delete_gesture *state, int key, uint32_t now);
void c10_delete_tick(struct c10_delete_gesture *state, uint32_t now);

#endif
