#!/usr/bin/env python3
"""Exercise an explicitly selected device against the running loopback HLS lab."""
import argparse
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

PACKAGE = "dev.easyhooon.streamplaybacklab"
ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True, help="Dedicated device serial; never auto-select")
    parser.add_argument("--adb", default=None)
    args = parser.parse_args()
    sdk = os.environ.get("ANDROID_HOME", os.environ.get("ANDROID_SDK_ROOT", ""))
    adb_path = args.adb or (str(Path(sdk) / "platform-tools/adb") if sdk else shutil.which("adb"))
    if not adb_path:
        parser.error("Set ANDROID_HOME or pass --adb")
    adb = [adb_path, "-s", args.serial]
    evidence = ROOT / ".local/evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    log = evidence / "playback.log"

    def run(*arguments, **kwargs):
        return subprocess.run(adb + list(arguments), check=True, timeout=30, **kwargs)

    def control(**values):
        request = urllib.request.Request("http://127.0.0.1:8090/control", json.dumps(values).encode(),
                                         {"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)

    def logs():
        return log.read_text(errors="replace") if log.exists() else ""

    def wait_for(pattern, offset=0, timeout=60):
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            match = re.search(pattern, logs()[offset:])
            if match:
                print("Observed: " + match.group(0), flush=True)
                return match.group(0)
            time.sleep(1)
        raise AssertionError(f"Not observed in {timeout}s: {pattern}; see .local/evidence/playback.log")

    def ui():
        for attempt in range(3):
            result = run("shell", "uiautomator", "dump", "/sdcard/playback-lab-ui.xml", capture_output=True)
            raw = run("shell", "cat", "/sdcard/playback-lab-ui.xml", capture_output=True).stdout
            try:
                return ET.fromstring(raw)
            except ET.ParseError:
                if attempt == 2:
                    raise AssertionError(result.stdout.decode(errors="replace"))
                time.sleep(1)

    def click(text):
        nodes = [node for node in ui().iter("node") if node.get("text") == text]
        if not nodes:
            raise AssertionError(f"UI control missing: {text}")
        bounds = [int(value) for value in re.findall(r"\d+", nodes[0].get("bounds", ""))]
        if len(bounds) != 4:
            raise AssertionError(f"Invalid bounds for {text}")
        x1, y1, x2, y2 = bounds
        run("shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))

    def position():
        for node in ui().iter("node"):
            match = re.fullmatch(r"(\d+):(\d+) / (\d+):(\d+)", node.get("text", ""))
            if match:
                minutes, seconds, _, _ = map(int, match.groups())
                return minutes * 60 + seconds
        raise AssertionError("Playback timeline not visible")

    def capture(name):
        with (evidence / f"{name}.png").open("wb") as output:
            run("exec-out", "screencap", "-p", stdout=output)

    def check(condition, message):
        if not condition:
            raise AssertionError(message)

    report = {"device": args.serial, "checks": {}, "events": {}}
    run("get-state", capture_output=True)
    control(kbps=6000, fail=False)
    run("reverse", "tcp:8090", "tcp:8090")
    run("install", "-r", str(ROOT / "app/build/outputs/apk/debug/app-debug.apk"))
    run("shell", "am", "force-stop", PACKAGE)
    run("logcat", "-c")
    logger = None
    try:
        with log.open("wb") as output:
            logger = subprocess.Popen(adb + ["logcat", "-v", "brief", "-s", "PlaybackLab:I", "*:S"], stdout=output)
            run("shell", "am", "start", "-n", f"{PACKAGE}/.MainActivity")
            report["events"]["initial_high"] = wait_for(r"event=decoder_format height=720[^\n]*")
            wait_for(r"event=playing=true[^\n]*")
            report["checks"]["loading"] = "event=state=BUFFERING" in logs()
            capture("01-playing-720p")

            mark = len(logs())
            click("Pause")
            wait_for(r"event=playing=false[^\n]*", mark)
            paused = position()
            time.sleep(3)
            check(position() == paused, "Position moved while paused")
            report["checks"]["pause_freezes_position"] = True
            mark = len(logs())
            click("Play")
            wait_for(r"event=playing=true[^\n]*", mark)
            before_seek = position()
            mark = len(logs())
            click("+10s")
            wait_for(r"event=seek target_ms=\d+", mark)
            check(position() >= before_seek + 8, "Seek did not advance the playback timeline")
            report["checks"]["resume_and_seek"] = True

            mark = len(logs())
            control(kbps=600)
            report["events"]["adaptive_low"] = wait_for(
                r"event=request_format height=360[^\n]*reason=ADAPTIVE[^\n]*", mark, 75)
            report["events"]["decoded_low"] = wait_for(r"event=decoder_format height=360[^\n]*", mark, 75)
            capture("02-adaptive-360p")
            mark = len(logs())
            control(kbps=6000)
            report["events"]["adaptive_high"] = wait_for(
                r"event=request_format height=720[^\n]*reason=ADAPTIVE[^\n]*", mark, 75)
            report["events"]["decoded_high"] = wait_for(r"event=decoder_format height=720[^\n]*", mark, 75)
            capture("03-adaptive-720p")
            report["checks"]["abr_down_and_up"] = True
            check("quality_mode=" not in logs(), "ABR test changed the quality override")

            mark = len(logs())
            control(fail=True)
            report["events"]["error"] = wait_for(r"event=player_error code=\S+[^\n]*", mark, 60)
            capture("04-error")
            control(fail=False, kbps=6000)
            mark = len(logs())
            click("Retry")
            report["events"]["retry"] = wait_for(r"event=retry position_ms=\d+", mark)
            report["events"]["recovered"] = wait_for(r"event=playing=true[^\n]*", mark)
            capture("05-recovered")
            report["checks"]["error_and_retry"] = True
            check(report["checks"]["loading"], "Loading state was not observed")
            report["status"] = "PASS"
    except Exception as error:
        report["status"] = "FAIL"
        report["error"] = str(error)
        raise
    finally:
        if logger is not None:
            logger.terminate()
            logger.wait(timeout=5)
        control(fail=False, kbps=0)
        (evidence / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
