#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
check() {
  unit=$1
  test=$2
  shift 2
  (
    cd "$root/work/$unit"
    "${CC:-cc}" -std=c11 -Wall -Wextra -Werror "$test.c" "$@" -o "$tmp/$test"
  )
  (cd "$tmp" && "./$test")
}
check c10-dual-timer test_sleep_timer sleep_timer.c
check c10-usb-dac test_feedback feedback.c -lm
mkdir -p "$tmp/build"
check c10-usb-dac test_descriptors descriptors.c
cp "$root/work/c10-usb-dac/test_descriptors.py" "$tmp/"
python3 "$tmp/test_descriptors.py"
check c10-lyrics test_lrc lrc.c
check c10-eq-live test_model eq_model.c
check c10-eq-live test_live_model eq_model.c live_model.c
check c10-delete test_gesture gesture.c
check c10-delete test_recycle recycle.c
check c10-dac-filter test_probe probe.c
check c10-dac-filter test_filter_compare filter_compare.c
python3 "$root/work/c10-dac-filter/test_launcher.py"
python3 "$root/work/c10-dac-filter/test_trial_launcher.py"
