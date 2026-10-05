"""Small adb probe for explicitly selected lab devices and local evidence."""
import os
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "dev.easyhooon.streamplaybacklab"


class DeviceProbe:
    def __init__(self, serial, scenario, adb_path=None):
        sdk = os.environ.get("ANDROID_HOME", os.environ.get("ANDROID_SDK_ROOT", ""))
        executable = adb_path or (str(Path(sdk) / "platform-tools/adb") if sdk else shutil.which("adb"))
        if not executable:
            raise ValueError("Set ANDROID_HOME or pass --adb")
        self.adb = [executable, "-s", serial]
        self.evidence = ROOT / ".local/evidence" / scenario
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.log = self.evidence / "playback.log"
        self.logger = None
        self.output = None

    def run(self, *arguments, **kwargs):
        return subprocess.run(self.adb + list(arguments), check=True, timeout=30, **kwargs)

    def start(self):
        self.run("get-state", capture_output=True)
        self.run("reverse", "tcp:8090", "tcp:8090")
        self.run("install", "-r", str(ROOT / "app/build/outputs/apk/debug/app-debug.apk"))
        self.run("shell", "am", "force-stop", PACKAGE)
        self.run("logcat", "-c")
        self.output = self.log.open("wb")
        self.logger = subprocess.Popen(self.adb + ["logcat", "-v", "brief", "-s", "PlaybackLab:I", "*:S"], stdout=self.output)
        self.run("shell", "am", "start", "-n", f"{PACKAGE}/.MainActivity")

    def logs(self):
        return self.log.read_text(errors="replace")

    def wait(self, pattern, offset=0, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            match = re.search(pattern, self.logs()[offset:])
            if match:
                print("Observed: " + match.group(0), flush=True)
                return match.group(0)
            time.sleep(0.5)
        raise AssertionError(f"Not observed: {pattern}; see {self.log.relative_to(ROOT)}")

    def ui(self):
        for _ in range(3):
            result = self.run("shell", "uiautomator", "dump", "/sdcard/playback-lab-probe.xml", capture_output=True)
            if b"dumped to" in result.stdout:
                raw = self.run("shell", "cat", "/sdcard/playback-lab-probe.xml", capture_output=True).stdout
                return ET.fromstring(raw)
            time.sleep(1)
        raise AssertionError("Cannot obtain current device UI")

    def click(self, text):
        for direction in (1, -1):
            for _ in range(5):
                tree = self.ui()
                for node in tree.iter("node"):
                    bounds = [int(x) for x in re.findall(r"\d+", node.get("bounds", ""))]
                    if node.get("text") == text and len(bounds) == 4:
                        x1, y1, x2, y2 = bounds
                        if x2 > x1 and y2 > y1:
                            self.run("shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))
                            return
                size = self.run("shell", "wm", "size", capture_output=True).stdout.decode()
                width, height = map(int, re.findall(r"(\d+)x(\d+)", size)[-1])
                y1, y2 = (height * 4 // 5, height * 2 // 5) if direction == 1 else (height * 2 // 5, height * 4 // 5)
                self.run("shell", "input", "swipe", str(width // 2), str(y1), str(width // 2), str(y2), "250")
        raise AssertionError(f"UI control missing: {text}")

    def capture(self, name):
        with (self.evidence / f"{name}.png").open("wb") as image:
            self.run("exec-out", "screencap", "-p", stdout=image)

    def close(self):
        if self.logger is not None:
            self.logger.terminate()
            self.logger.wait(timeout=5)
        if self.output is not None:
            self.output.close()
