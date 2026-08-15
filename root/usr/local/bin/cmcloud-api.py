#!/usr/bin/python3
"""Small HTTP control plane for Function Compute custom containers."""

import json
import os
import pathlib
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


STATUS_FILE = pathlib.Path("/config/logs/cmcloud-api-status.json")
LOG_DIR = pathlib.Path("/config/logs")
job_lock = threading.Lock()
job_process: subprocess.Popen | None = None


def write_status(state: str, detail: str = "") -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps({
        "state": state,
        "detail": detail,
        "updatedAt": int(time.time()),
    }), encoding="utf-8")


def read_status() -> dict:
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"state": "idle"}


def run_job() -> None:
    global job_process
    write_status("starting")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "function-job.log").open("ab", buffering=0) as log_file:
        job_process = subprocess.Popen(
            ["/usr/local/bin/launch-cmcloud.sh"],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )
        if os.environ.get("CMCLOUD_AUTO_LOGIN", "1") == "1":
            subprocess.Popen(
                ["/usr/local/bin/cmcloud-autologin.py"],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=os.environ.copy(),
            )
        write_status("running", f"pid={job_process.pid}")
        return_code = job_process.wait()
    write_status("stopped", f"exitCode={return_code}")


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, {"ok": True})
            return
        self.send_json(200, read_status())

    def do_POST(self) -> None:
        global job_process
        if self.path != "/run":
            self.send_json(404, {"error": "not found"})
            return
        with job_lock:
            if job_process is not None and job_process.poll() is None:
                self.send_json(200, {"state": "running", "pid": job_process.pid})
                return
            threading.Thread(target=run_job, daemon=True).start()
        self.send_json(202, {"state": "starting"})

    def log_message(self, format: str, *args: object) -> None:
        print(f"[cmcloud-api] {self.address_string()} {format % args}", flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("FC_SERVER_PORT", "9000"))
    write_status("idle")
    print(f"[cmcloud-api] listening on 0.0.0.0:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
