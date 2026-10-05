#!/usr/bin/env python3
"""Check the Bunny playlist and actual decoder formats through user controls."""
import argparse
import json
import re
import time
import urllib.request

from device_probe import DeviceProbe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--adb")
    args = parser.parse_args()
    probe = DeviceProbe(args.serial, "bunny", args.adb)
    report = {"device": args.serial, "decoder_formats": {}}
    try:
        with urllib.request.urlopen("http://127.0.0.1:8090/bbb/master.m3u8", timeout=5) as response:
            master = response.read().decode()
        assert master.count("#EXT-X-STREAM-INF") == 3
        for resolution in ("640x360", "1280x720", "1920x1080"):
            assert "RESOLUTION=" + resolution in master
        probe.start()
        mark = len(probe.logs())
        probe.click("Bunny")
        probe.wait(r"event=source_mode=BUNNY", mark)
        mark = probe.logs().index("event=source_mode=BUNNY", mark)
        probe.wait(r"event=decoder_format height=\d+[^\n]*", mark)
        probe.wait(r"event=playing=true[^\n]*", mark)
        report["audio"] = probe.wait(r"event=audio_format mime=audio/mp4a-latm channels=2", mark)
        for height in (1080, 360, 720):
            mark = len(probe.logs())
            probe.click(f"{height}p")
            probe.wait(f"event=quality_mode={height}p", mark)
            formats = re.findall(r"event=decoder_format height=(\d+)([^\n]*)", probe.logs())
            if formats and int(formats[-1][0]) == height:
                report["decoder_formats"][str(height)] = "event=decoder_format height=" + "".join(formats[-1])
            else:
                report["decoder_formats"][str(height)] = probe.wait(
                    rf"event=decoder_format height={height}[^\n]*", mark, 35)
            time.sleep(0.5)
            probe.capture(f"bunny-{height}p")
        probe.wait(r"event=state=ENDED[^\n]*", mark, 40)
        mark = len(probe.logs())
        probe.click("Replay")
        probe.wait(r"event=replay", mark)
        report["replay"] = probe.wait(r"event=playing=true[^\n]*", mark)
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
