#!/usr/bin/python3
"""Small HTTP control plane for Function Compute custom containers."""

import json
import os
import pathlib
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


STATUS_FILE = pathlib.Path("/config/logs/cmcloud-api-status.json")
LOG_DIR = pathlib.Path("/config/logs")
job_lock = threading.Lock()
job_process: subprocess.Popen | None = None


def redact(text: str) -> str:
    for name in ("CMCLOUD_USERNAME", "CMCLOUD_PASSWORD", "PASSWORD"):
        value = os.environ.get(name, "")
        if value:
            text = text.replace(value, "<redacted>")
    return text


def tail_file(path: pathlib.Path, limit: int = 12000) -> str:
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - limit))
            data = stream.read()
        return redact(data.decode("utf-8", errors="replace"))
    except OSError:
        return ""


def process_snapshot(pid: int) -> dict:
    snapshot: dict[str, object] = {"pid": pid}
    try:
        snapshot["cmdline"] = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(
            "utf-8", errors="replace"
        ).strip()
        status_lines = pathlib.Path(f"/proc/{pid}/status").read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
        wanted = ("Name:", "State:", "Pid:", "PPid:", "Threads:", "Seccomp:", "Seccomp_filters:")
        snapshot["status"] = {line.split(":", 1)[0]: line.split(":", 1)[1].strip()
                              for line in status_lines if line.startswith(wanted)}
    except OSError:
        snapshot["exited"] = True
    return snapshot


def diagnostics() -> dict:
    result = read_status()
    if job_process is not None:
        result["process"] = process_snapshot(job_process.pid)
    result["logs"] = {
        "job": tail_file(LOG_DIR / "function-job.log"),
        "wine": tail_file(LOG_DIR / "cmcloud-wine.log"),
        "autologin": tail_file(LOG_DIR / "autologin.log"),
        "winebootStrace": tail_file(LOG_DIR / "wineboot.strace", limit=24000),
    }
    return result


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
    if return_code < 0:
        signal_number = -return_code
        signal_name = signal.Signals(signal_number).name
        detail = f"signal={signal_name}({signal_number})"
    elif return_code >= 128:
        signal_number = return_code - 128
        try:
            signal_name = signal.Signals(signal_number).name
            detail = f"exitCode={return_code}, shellSignal={signal_name}({signal_number})"
        except ValueError:
            detail = f"exitCode={return_code}"
    else:
        detail = f"exitCode={return_code}"
    write_status("stopped", detail)


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
        if self.path == "/diagnostics":
            self.send_json(200, diagnostics())
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
