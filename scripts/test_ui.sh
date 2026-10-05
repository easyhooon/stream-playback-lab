#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
serial="${1:?Usage: scripts/test_ui.sh dedicated-device-serial}"
sdk_dir="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [[ -z "$sdk_dir" ]]; then
    echo 'Set ANDROID_HOME to an installed Android SDK.' >&2
    exit 2
fi
adb="$sdk_dir/platform-tools/adb"
"$adb" -s "$serial" install -r "$repo_dir/app/build/outputs/apk/debug/app-debug.apk"
"$adb" -s "$serial" install -r "$repo_dir/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
result="$("$adb" -s "$serial" shell am instrument -w \
    -e class dev.easyhooon.streamplaybacklab.PlaybackScreenTest \
    dev.easyhooon.streamplaybacklab.test/androidx.test.runner.AndroidJUnitRunner)"
printf '%s\n' "$result"
if ! [[ "$result" =~ OK\ \([1-9][0-9]*\ tests?\) ]]; then
    exit 1
fi
