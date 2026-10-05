import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from serve_hls import LabServer


class LabServerTest(unittest.TestCase):
    def setUp(self):
        self.files = tempfile.TemporaryDirectory()
        root = Path(self.files.name)
        (root / "hls").mkdir()
        (root / "hls/master.m3u8").write_text("#EXTM3U\n")
        (root / "hls/segment.ts").write_bytes(b"x" * 16000)
        self.server = LabServer(("127.0.0.1", 0), root)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.files.cleanup()

    def control(self, values):
        request = urllib.request.Request(self.url + "/control", json.dumps(values).encode(),
                                         {"Content-Type": "application/json"})
        return urllib.request.urlopen(request, timeout=5)

    def test_throttle_and_recovery(self):
        with self.control({"kbps": 128}) as response:
            self.assertEqual(json.load(response), {"kbps": 128, "fail": False})
        started = time.monotonic()
        with urllib.request.urlopen(self.url + "/hls/segment.ts", timeout=5) as response:
            self.assertEqual(len(response.read()), 16000)
            self.assertEqual(response.headers["Content-Type"], "video/mp2t")
        self.assertGreaterEqual(time.monotonic() - started, 0.95)
        with self.control({"fail": True}):
            pass
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(self.url + "/hls/master.m3u8", timeout=5)
        self.assertEqual(error.exception.code, 503)
        with self.control({"fail": False, "kbps": 0}):
            pass
        with urllib.request.urlopen(self.url + "/hls/master.m3u8", timeout=5) as response:
            self.assertEqual(response.read(), b"#EXTM3U\n")

    def test_traversal_and_invalid_control(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(self.url + "/../outside.txt", timeout=5)
        self.assertEqual(error.exception.code, 404)
        for values in ({"kbps": -1}, {"kbps": True}, {"fail": "true"}, {"port": 8000}):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.control(values)
            self.assertEqual(error.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
