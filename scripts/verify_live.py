#!/usr/bin/env python3
"""Verify ordinary live HLS rolling windows, pause return and producer recovery."""
import argparse
import json
import re
import time
import urllib.error
import urllib.request

from device_probe import DeviceProbe


def request(path, values=None):
    data = json.dumps(values).encode() if values is not None else None
    with urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8090" + path, data), timeout=10) as response:
        return response.read().decode()


def sequence(playlist):
    return int(re.search(r"#EXT-X-MEDIA-SEQUENCE:(\d+)", playlist)[1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb")
    args = parser.parse_args()
    probe = DeviceProbe(args.serial, "live", args.adb)
    report = {"device": args.serial, "checks": {}, "events": {}}

    def offset_after(mark):
        probe.wait(r"event=live_metrics offset_ms=\d+[^\n]*", mark, 20)
        matches = re.findall(r"event=live_metrics offset_ms=(\d+)[^\n]*", probe.logs()[mark:])
        return int(matches[-1])

    def published(previous=None):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                text = request("/live/index.m3u8")
                if text.count("#EXTINF:") >= 3 and (previous is None or sequence(text) > previous):
                    return text
            except urllib.error.HTTPError:
                pass
            time.sleep(0.5)
        raise AssertionError("Live playlist not published")

    try:
        request("/control", {"kbps": 0, "fail": False})
        request("/live-control", {"running": True})
        first = published()
        time.sleep(3)
        second = published(sequence(first))
        assert second.count("#EXTINF:") <= 6 and "#EXT-X-ENDLIST" not in second
        assert "#EXT-X-PART" not in second and "#EXT-X-PROGRAM-DATE-TIME" in second
        report["checks"]["ordinary_sliding_window"] = True
        probe.start()
        mark = len(probe.logs())
        probe.click("Live")
        probe.wait(r"event=decoder_format height=360[^\n]*", mark)
        probe.wait(r"event=live_metrics offset_ms=\d+[^\n]*dynamic=true playing=true", mark)
        initial = offset_after(mark)
        assert 0 < initial <= 12_000, f"Unexpected initial live offset: {initial}"
        report["initial_offset_ms"] = initial
        probe.capture("01-live-playing")

        mark = len(probe.logs())
        probe.click("Pause")
        probe.wait(r"event=playing=false[^\n]*", mark)
        time.sleep(14)
        paused = offset_after(mark)
        assert paused >= initial + 8_000, f"Offset did not grow while paused: {paused}"
        report["paused_offset_ms"] = paused
        probe.capture("02-live-paused")
        mark = len(probe.logs())
        probe.click("Go live")
        report["events"]["go_live"] = probe.wait(r"event=go_live[^\n]*", mark)
        probe.wait(r"event=playing=true[^\n]*", mark)
        time.sleep(2)
        restored = offset_after(mark)
        assert restored <= 12_000 and restored < paused - 5_000
        report["returned_offset_ms"] = restored
        report["checks"]["pause_and_return"] = True
        probe.capture("03-returned-live")

        mark = len(probe.logs())
        stopped = json.loads(request("/live-control", {"running": False}))
        assert not stopped["running"]
        frozen = request("/live/index.m3u8")
        time.sleep(3)
        assert request("/live/index.m3u8") == frozen
        report["events"]["outage"] = probe.wait(r"event=player_error code=\S+[^\n]*", mark, 75)
        probe.capture("04-producer-stopped")
        request("/live-control", {"running": True})
        restarted = published(sequence(frozen))
        report["restart_sequence"] = sequence(restarted)
        mark = len(probe.logs())
        probe.click("Retry")
        report["events"]["retry"] = probe.wait(r"event=retry[^\n]*", mark)
        probe.wait(r"event=decoder_format height=360[^\n]*", mark)
        probe.wait(r"event=live_metrics offset_ms=\d+[^\n]*dynamic=true playing=true", mark)
        recovered = offset_after(mark)
        assert 0 < recovered <= 12_000, f"Recovered into an old window: {recovered}"
        report["recovered_offset_ms"] = recovered
        report["checks"]["producer_stop_and_restart"] = True
        probe.capture("05-live-recovered")
        report["status"] = "PASS"
    except Exception as error:
        report["status"] = "FAIL"
        report["error"] = str(error)
        raise
    finally:
        probe.close()
        (probe.evidence / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
