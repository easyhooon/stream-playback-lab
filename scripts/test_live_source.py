import json
import re
import shutil
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from live_source import LiveSource
from serve_hls import LabServer


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required for the live integration test")
class LiveSourceTest(unittest.TestCase):
    def test_real_time_window_http_stop_and_restart_preserve_vod(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "media"
            (root / "hls").mkdir(parents=True)
            vod = root / "hls/master.m3u8"
            vod.write_text("#EXTM3U\n#EXT-X-ENDLIST\n")
            source = LiveSource(root, window_segments=3)
            server = LabServer(("127.0.0.1", 0), root, source)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"

            def control(running):
                request = urllib.request.Request(base + "/live-control", json.dumps({"running": running}).encode())
                with urllib.request.urlopen(request, timeout=10) as response:
                    return json.load(response)

            def playlist():
                with urllib.request.urlopen(base + "/live/index.m3u8", timeout=5) as response:
                    data = response.read()
                    self.assertEqual(len(data), int(response.headers["Content-Length"]))
                    return data.decode()

            def wait_playlist(minimum_sequence=None):
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    try:
                        value = playlist()
                        sequence = int(re.search(r"#EXT-X-MEDIA-SEQUENCE:(\d+)", value)[1])
                        if value.count("#EXTINF:") == 3 and (minimum_sequence is None or sequence > minimum_sequence):
                            return sequence, value
                    except (urllib.error.HTTPError, FileNotFoundError):
                        pass
                    time.sleep(0.25)
                self.fail("Live window was not published/advanced in real time")

            try:
                self.assertTrue(control(True)["running"])
                first_sequence, first = wait_playlist()
                next_sequence, current = wait_playlist(first_sequence)
                self.assertGreater(next_sequence, first_sequence)
                self.assertEqual(current.count("#EXTINF:"), 3)
                self.assertIn("#EXT-X-PROGRAM-DATE-TIME:", current)
                self.assertNotIn("#EXT-X-ENDLIST", current)
                self.assertNotIn("#EXT-X-PART", current)
                self.assertLessEqual(len(list((root / "live").glob("*.ts"))), 5)
                with urllib.request.urlopen(base + "/hls/master.m3u8", timeout=5) as response:
                    self.assertIn(b"#EXT-X-ENDLIST", response.read())
                self.assertFalse(control(False)["running"])
                frozen = playlist()
                time.sleep(2.5)
                self.assertEqual(playlist(), frozen)
                self.assertNotIn("#EXT-X-ENDLIST", frozen)
                self.assertTrue(control(True)["running"])
                _, restarted = wait_playlist(next_sequence)
                self.assertNotEqual(restarted, frozen)
                self.assertEqual(vod.read_text(), "#EXTM3U\n#EXT-X-ENDLIST\n")
            finally:
                source.close()
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()
