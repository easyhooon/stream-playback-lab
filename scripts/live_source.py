"""Owned FFmpeg process producing ordinary live HLS from synthetic sources."""
import signal
import subprocess
import threading
import time
from pathlib import Path


class LiveSource:
    def __init__(self, media_root, window_segments=6):
        self.root = Path(media_root) / "live"
        self.window_segments = window_segments
        self.lock = threading.RLock()
        self.process = None
        self.generation = None
        self.log = None

    def status(self):
        with self.lock:
            return {"running": self.process is not None and self.process.poll() is None,
                    "generation": self.generation, "window_segments": self.window_segments,
                    "segment_seconds": 2}

    def start(self):
        with self.lock:
            if self.status()["running"]:
                return self.status()
            self.root.mkdir(parents=True, exist_ok=True)
            # Only this producer's generated live files; VOD directories are untouched.
            for pattern in ("segment_*.ts", "segment_*.ts.tmp", "index.m3u8", "index.m3u8.tmp"):
                for path in self.root.glob(pattern):
                    path.unlink(missing_ok=True)
            self.generation = time.time_ns()
            if self.log is not None:
                self.log.close()
            self.log = (self.root.parent.parent / "live-encoder.log").open("ab")
            command = [
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "warning", "-y",
                "-re", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
                "-re", "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=48000",
                "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
                "-threads", "2", "-pix_fmt", "yuv420p", "-g", "60", "-keyint_min", "60",
                "-sc_threshold", "0", "-b:v", "600k", "-maxrate", "600k", "-bufsize", "1200k",
                "-c:a", "aac", "-b:a", "64k", "-ac", "2",
                "-f", "hls", "-hls_time", "2", "-hls_list_size", str(self.window_segments),
                "-hls_delete_threshold", "2", "-hls_start_number_source", "epoch_us",
                "-hls_flags", "delete_segments+independent_segments+program_date_time+temp_file+omit_endlist+discont_start",
                "-hls_segment_filename", str(self.root / "segment_%d.ts"),
                str(self.root / "index.m3u8"),
            ]
            self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log)
            return self.status()

    def stop(self):
        with self.lock:
            if self.status()["running"]:
                self.process.send_signal(signal.SIGINT)
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            return self.status()

    def close(self):
        self.stop()
        if self.log is not None:
            self.log.close()
