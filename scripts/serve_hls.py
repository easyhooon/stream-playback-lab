#!/usr/bin/env python3
"""Loopback-only HLS server with reproducible per-request throttling and faults."""
import argparse
import json
import mimetypes
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from live_source import LiveSource


class LabServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, root, live_source=None):
        super().__init__(address, LabHandler)
        self.root = Path(root).resolve()
        self.lock = threading.Lock()
        self.kbps = 0
        self.fail = False
        self.live_source = live_source

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
        if self.path not in ("/control", "/live-control"):
            self.respond(404, b'{}')
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024:
                raise ValueError("invalid body size")
            values = json.loads(self.rfile.read(size))
            if self.path == "/live-control":
                if self.server.live_source is None:
                    self.respond(409, b'{"error":"Start server with --live"}')
                    return
                if not isinstance(values, dict) or set(values) != {"running"} or type(values["running"]) is not bool:
                    raise ValueError("running: boolean is required")
                source = self.server.live_source
                status = source.start() if values["running"] else source.stop()
                self.respond(200, json.dumps(status).encode())
                return
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
            status = self.server.settings()
            if self.server.live_source is not None:
                status["live"] = self.server.live_source.status()
            self.respond(200, json.dumps(status).encode())
            return
        target = (self.server.root / path.lstrip("/")).resolve()
        if not target.is_relative_to(self.server.root) or target.suffix == ".tmp" or not target.is_file():
            self.respond(404, b'{}')
            return
        if self.server.settings()["fail"]:
            self.respond(503, b'{"error":"injected outage"}')
            print(json.dumps({"event": "request", "path": path, "status": 503}), flush=True)
            return
        try:
            media = target.open("rb")
        except FileNotFoundError:
            self.respond(404, b'{}')
            return
        # Snapshot a playlist before setting Content-Length: FFmpeg atomically replaces it.
        if target.suffix == ".m3u8":
            with media:
                data = media.read()
            self.respond(200, data, "application/vnd.apple.mpegurl")
            return
        size = os.fstat(media.fileno()).st_size
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
            with media:
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
    parser.add_argument("--live", action="store_true", help="Run an owned synthetic live HLS producer")
    args = parser.parse_args()
    if not args.live and not (args.root / "hls/master.m3u8").is_file():
        parser.error("Run scripts/generate_hls.sh first, or use --live")
    source = LiveSource(args.root) if args.live else None
    server = LabServer(("127.0.0.1", args.port), args.root, source)
    if source is not None:
        source.start()
    print(f"Loopback HLS: http://127.0.0.1:{args.port}/hls/master.m3u8", flush=True)
    if source is not None:
        print(f"Ordinary live HLS: http://127.0.0.1:{args.port}/live/index.m3u8", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if source is not None:
            source.close()
        server.server_close()


if __name__ == "__main__":
    main()
