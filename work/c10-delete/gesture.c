#include "gesture.h"

enum { BACK = 1, PLAY = C10_DIRECTORY_PLAY_KEY, UP = 103, LEFT = 105, DOWN = 108 };
enum { HOLD_MS = 700 };

static int menu_key(int key) {
    return key == BACK || key == PLAY || key == UP || key == LEFT || key == DOWN;
}

void c10_delete_tick(struct c10_delete_gesture *state, uint32_t now) {
    if (state->holding && state->screen == C10_DELETE_CLOSED && now - state->started >= HOLD_MS) {
        state->screen = C10_DELETE_MENU;
        state->selected = 0;
    }
}

enum c10_delete_action c10_delete_press(struct c10_delete_gesture *state, int key,
                                        int repeated, int eligible, uint32_t now) {
    if (state->screen != C10_DELETE_CLOSED)
        return menu_key(key) ? C10_DELETE_HANDLED : C10_DELETE_STOCK;
    if (key != PLAY) return C10_DELETE_STOCK;
    if (state->holding) {
        c10_delete_tick(state, now);
        return C10_DELETE_HANDLED;
    }
    if (repeated || !eligible) return C10_DELETE_STOCK;
    state->holding = 1;
    state->started = now;
    return C10_DELETE_HANDLED;
}

enum c10_delete_action c10_delete_release(struct c10_delete_gesture *state, int key, uint32_t now) {
    if (key == PLAY && state->holding) {
        c10_delete_tick(state, now);
        state->holding = 0;
        return state->screen == C10_DELETE_CLOSED ? C10_DELETE_SHORT_PLAY : C10_DELETE_HANDLED;
    }
    if (state->screen == C10_DELETE_CLOSED || !menu_key(key)) return C10_DELETE_STOCK;
    if (key == UP || key == DOWN) {
        state->selected ^= 1u;
        return C10_DELETE_HANDLED;
    }
    int move = key == PLAY && state->selected;
    state->screen = C10_DELETE_CLOSED;
    state->selected = 0;
    return move ? C10_DELETE_MOVE : C10_DELETE_HANDLED;
}
