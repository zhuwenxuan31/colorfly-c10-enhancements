#!/bin/sh
# Run the read-only DAC filter probe once, during ordinary local playback.
root=${C10_DAC_ROOT:-}
busybox="$root/bin/busybox"
media="$root/mnt/memory"
module="$root/usr/local/modules/c10_dac_probe.ko"
marker="$media/.c10-dac-probe"

has_local_playback() {
    for stat_file in "$root"/proc/[0-9]*/stat; do
        [ -r "$stat_file" ] || continue
        IFS=' ' read -r pid command rest < "$stat_file" || continue
        [ "$command" = '(mplayer)' ] || continue
        for fd in "${stat_file%/stat}"/fd/[0-9]*; do
            [ "$("$busybox" readlink "$fd" 2>/dev/null)" = /dev/dsp ] && return 0
        done
    done
    return 1
}

probe_once() {
    count=0
    while [ "$count" -lt 45 ] && ! has_local_playback; do
        count=$((count + 1))
        "$busybox" sleep 2
    done
    # USB storage operation unmounts this filesystem. Recheck the trigger.
    [ -f "$marker" ] || return
    umask 077
    report=$("$busybox" mktemp "$media/.c10-dac-probe.log.XXXXXX") || return
    if [ "$count" -eq 45 ]; then
        printf '%s\n' 'C10DAC_PROBE1 status=no-local-playback' > "$report"
    elif "$root/sbin/insmod" "$module" > "$report" 2>&1; then
        if ! "$busybox" dmesg | "$busybox" grep 'C10DAC_PROBE1' >> "$report"; then
            printf '%s\n' 'C10DAC_PROBE1 status=no-kernel-result' >> "$report"
        fi
        "$root/sbin/rmmod" c10_dac_probe >> "$report" 2>&1
    else
        printf '%s\n' 'C10DAC_PROBE1 status=module-load-failed' >> "$report"
    fi
    if "$busybox" mv "$report" "$media/C10_DAC_PROBE.log"; then
        "$busybox" rm -f "$marker"
        "$busybox" sync
    fi
}

if [ -f "$marker" ] && "$busybox" mkdir "$root/tmp/c10-dac-probe-once" 2>/dev/null; then
    probe_once </dev/null >/dev/null 2>&1 &
fi
exec "$root/usr/local/aplayer/ap.factory" "$@"
