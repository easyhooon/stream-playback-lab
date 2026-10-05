#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"
export GRADLE_USER_HOME="$repo_dir/.local/gradle"
export ANDROID_USER_HOME="$repo_dir/.local/android-user"
mkdir -p "$GRADLE_USER_HOME" "$ANDROID_USER_HOME"
if [[ -z "${ANDROID_HOME:-}" ]]; then
    if [[ -n "${ANDROID_SDK_ROOT:-}" ]]; then
        export ANDROID_HOME="$ANDROID_SDK_ROOT"
    elif [[ -d "$HOME/Library/Android/sdk" ]]; then
        export ANDROID_HOME="$HOME/Library/Android/sdk"
    else
        export ANDROID_HOME="$HOME/Android/Sdk"
    fi
fi
if (( $# == 0 )); then
    set -- :app:assembleDebug :app:testDebugUnitTest :app:lintDebug :app:assembleDebugAndroidTest
fi
exec ./gradlew --no-daemon "$@"
