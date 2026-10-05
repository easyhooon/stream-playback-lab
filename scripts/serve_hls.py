#!/usr/bin/env python3
"""Loopback-only HLS server with reproducible per-request throttling and faults."""
import argparse
import json
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class LabServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, root):
        super().__init__(address, LabHandler)
        self.root = Path(root).resolve()
        self.lock = threading.Lock()
        self.kbps = 0
        self.fail = False

    def settings(self):
        with self.lock:
            return {"kbps": self.kbps, "fail": self.fail}


class LabHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass

    def respond(self, code, data, content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/control":
            self.respond(404, b'{}')
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024:
                raise ValueError("invalid body size")
            values = json.loads(self.rfile.read(size))
            if not isinstance(values, dict) or set(values) - {"kbps", "fail"}:
                raise ValueError("only kbps and fail are supported")
            current = self.server.settings()
            rate, fail = values.get("kbps", current["kbps"]), values.get("fail", current["fail"])
            if type(rate) is not int or not 0 <= rate <= 100000 or type(fail) is not bool:
                raise ValueError("kbps: integer 0..100000, fail: boolean")
            with self.server.lock:
                self.server.kbps, self.server.fail = rate, fail
            self.respond(200, json.dumps(self.server.settings()).encode())
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self.respond(400, json.dumps({"error": str(error)}).encode())

    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if path == "/status":
            self.respond(200, json.dumps(self.server.settings()).encode())
            return
        target = (self.server.root / path.lstrip("/")).resolve()
        if not target.is_relative_to(self.server.root) or not target.is_file():
            self.respond(404, b'{}')
            return
        if self.server.settings()["fail"]:
            self.respond(503, b'{"error":"injected outage"}')
            print(json.dumps({"event": "request", "path": path, "status": 503}), flush=True)
            return
        size = target.stat().st_size
        content_type = {".m3u8": "application/vnd.apple.mpegurl", ".ts": "video/mp2t"}.get(
            target.suffix, mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        )
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        started = time.monotonic()
        sent = 0
        try:
            with target.open("rb") as media:
                while chunk := media.read(8192):
                    settings = self.server.settings()
                    if settings["fail"]:
                        self.close_connection = True
                        break
                    # Throttle media bodies, not playlists or control requests.
                    if settings["kbps"] and target.suffix == ".ts":
                        time.sleep(len(chunk) * 8 / (settings["kbps"] * 1000))
                    self.wfile.write(chunk)
                    self.wfile.flush()
                    sent += len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            print(json.dumps({"event": "request", "path": path, "status": 200,
                              "bytes": sent, "elapsed_ms": round((time.monotonic() - started) * 1000),
                              **self.server.settings()}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / ".local/media")
    args = parser.parse_args()
    if not (args.root / "hls/master.m3u8").is_file():
        parser.error("Run scripts/generate_hls.sh first")
    server = LabServer(("127.0.0.1", args.port), args.root)
    print(f"Loopback HLS: http://127.0.0.1:{args.port}/hls/master.m3u8", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
