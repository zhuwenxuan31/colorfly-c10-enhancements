#!/bin/sh
# One comparison during DAC_AB.wav. No persistent DAC preference is written.
root=${C10_DAC_ROOT:-}
bb="$root/bin/busybox"
media="$root/mnt/memory"
marker="$media/.c10-dac-ab"
sample="$media/000_DAC_AB/DAC_AB.wav"
module="$root/usr/local/modules/c10_dac_trial.ko"

playing_sample() {
    process=$1
    [ -r "$process/stat" ] || return 1
    IFS=' ' read -r pid command rest < "$process/stat" || return 1
    [ "$command" = '(mplayer)' ] || return 1
    "$bb" tr '\000' '\n' < "$process/cmdline" | "$bb" grep -Fxq "$sample" || return 1
    for fd in "$process"/fd/[0-9]*; do
        [ "$("$bb" readlink "$fd" 2>/dev/null)" = /dev/dsp ] && return 0
    done
    return 1
}

find_playback() {
    for stat_file in "$root"/proc/[0-9]*/stat; do
        track_process=${stat_file%/stat}
        playing_sample "$track_process" && return 0
    done
    return 1
}

wait_playing() {
    remaining=$1
    while [ "$remaining" -gt 0 ]; do
        "$bb" sleep 1
        playing_sample "$track_process" || return 1
        remaining=$((remaining - 1))
    done
}

compare_once() {
    attempts=0
    while ! find_playback; do
        attempts=$((attempts + 1))
        [ "$attempts" -ge 90 ] && break
        "$bb" sleep 1
    done
    [ -f "$marker" ] || return
    umask 077
    report=$("$bb" mktemp "$media/.c10-dac-ab.log.XXXXXX") || return
    if [ "$attempts" -ge 90 ]; then
        echo 'C10DAC_AB1 no-test-playback' >> "$report"
    elif ! wait_playing 20; then
        echo 'C10DAC_AB1 test-ended-before-switch' >> "$report"
    elif "$root/sbin/insmod" "$module" >> "$report" 2>&1; then
        trap '"$root/sbin/rmmod" c10_dac_trial >/dev/null 2>&1' EXIT
        trap 'exit 1' HUP INT TERM
        if ! wait_playing 20; then echo 'C10DAC_AB1 test-ended-during-switch' >> "$report"; fi
        if "$root/sbin/rmmod" c10_dac_trial >> "$report" 2>&1; then
            trap - EXIT HUP INT TERM
        else
            echo 'C10DAC_AB1 unload-failed' >> "$report"
        fi
        "$bb" dmesg | "$bb" grep 'C10DAC_AB1' >> "$report"
    else
        echo 'C10DAC_AB1 module-load-failed' >> "$report"
    fi
    if "$bb" mv "$report" "$media/C10_DAC_AB.log"; then
        "$bb" rm -f "$marker"
        "$bb" sync
    fi
}

if [ -f "$marker" ] && "$bb" mkdir "$root/tmp/c10-dac-ab-once" 2>/dev/null; then
    compare_once </dev/null >/dev/null 2>&1 &
fi
exec "$root/usr/local/aplayer/ap.factory" "$@"
