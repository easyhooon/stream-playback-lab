#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
sdk_dir="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [[ -z "$sdk_dir" || ! -x "$sdk_dir/emulator/emulator" ]]; then
    echo 'Set ANDROID_HOME to an installed Android SDK.' >&2
    exit 2
fi
case "$(uname -m)" in
    arm64|aarch64) abi=arm64-v8a ;;
    *) abi=x86_64 ;;
esac
system_image="${LAB_SYSTEM_IMAGE:-system-images;android-34;google_apis_playstore;$abi}"
avd_name=Stream_Playback_Lab
export ANDROID_USER_HOME="$repo_dir/.local/android-user"
export ANDROID_AVD_HOME="$repo_dir/.local/avd"
export ANDROID_EMULATOR_HOME="$ANDROID_USER_HOME"
export PATH="$sdk_dir/platform-tools:$PATH"
mkdir -p "$ANDROID_USER_HOME" "$ANDROID_AVD_HOME"
if [[ ! -f "$ANDROID_AVD_HOME/$avd_name.ini" ]]; then
    avdmanager="$sdk_dir/cmdline-tools/latest/bin/avdmanager"
    if [[ ! -x "$avdmanager" ]]; then
        echo 'Android SDK Command-line Tools (latest) are required.' >&2
        exit 2
    fi
    printf 'no\n' | "$avdmanager" create avd -n "$avd_name" \
        -p "$ANDROID_AVD_HOME/$avd_name.avd" -k "$system_image" -d pixel_5
fi
exec "$sdk_dir/emulator/emulator" -avd "$avd_name" -port 5558 \
    -adb-path "$sdk_dir/platform-tools/adb" \
    -no-window -no-snapshot -no-audio -gpu auto -memory 2048 -cores 2
