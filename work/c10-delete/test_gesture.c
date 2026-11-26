#include "gesture.h"
#include <assert.h>

int main(void) {
    struct c10_delete_gesture gesture = {0};
    assert(c10_delete_press(&gesture, 28, 0, 1, 1) == C10_DELETE_STOCK);
    assert(c10_delete_press(&gesture, 106, 0, 0, 10) == C10_DELETE_STOCK);
    assert(c10_delete_press(&gesture, 106, 0, 1, 20) == C10_DELETE_HANDLED);
    assert(c10_delete_release(&gesture, 106, 200) == C10_DELETE_SHORT_PLAY);
    assert(gesture.screen == C10_DELETE_CLOSED);

    assert(c10_delete_press(&gesture, 106, 0, 1, 400) == C10_DELETE_HANDLED);
    assert(c10_delete_release(&gesture, 106, 1099) == C10_DELETE_SHORT_PLAY);
    assert(c10_delete_press(&gesture, 106, 0, 1, 2000) == C10_DELETE_HANDLED);
    c10_delete_tick(&gesture, 2700);
    assert(gesture.screen == C10_DELETE_MENU);
    assert(c10_delete_release(&gesture, 106, 2705) == C10_DELETE_HANDLED);
    assert(gesture.screen == C10_DELETE_MENU);
    assert(c10_delete_release(&gesture, 106, 2710) == C10_DELETE_HANDLED);
    assert(gesture.screen == C10_DELETE_CLOSED); /* Cancel starts selected. */

    assert(c10_delete_press(&gesture, 106, 0, 1, 3000) == C10_DELETE_HANDLED);
    assert(c10_delete_release(&gesture, 106, 3700) == C10_DELETE_HANDLED);
    assert(c10_delete_release(&gesture, 108, 3800) == C10_DELETE_HANDLED);
    assert(c10_delete_release(&gesture, 106, 3900) == C10_DELETE_MOVE);
    assert(gesture.screen == C10_DELETE_CLOSED);
    assert(c10_delete_release(&gesture, 1, 4500) == C10_DELETE_STOCK);

    assert(c10_delete_press(&gesture, 106, 0, 1, UINT32_MAX - 200) == C10_DELETE_HANDLED);
    assert(c10_delete_release(&gesture, 106, 550) == C10_DELETE_HANDLED);
    assert(gesture.screen == C10_DELETE_MENU);
    assert(c10_delete_release(&gesture, 1, 600) == C10_DELETE_HANDLED);
    assert(gesture.screen == C10_DELETE_CLOSED);
    return 0;
}
