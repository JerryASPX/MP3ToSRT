#!/usr/bin/env python
"""Local single-page UI backend for media_to_subtitle.py."""
from __future__ import annotations

import cgi
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
JOBS = DATA / "jobs"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
CONVERTER = ROOT / "media_to_subtitle.py"
LOCK = threading.RLock()
STATE = {
    "job": None,
    "events": [],
}


def ensure_dirs() -> None:
    UPLOADS.mkdir(parents=True, exist_ok=True)
    JOBS.mkdir(parents=True, exist_ok=True)


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def add_event(message: str, level: str = "info") -> None:
    with LOCK:
        STATE["events"].insert(0, {"time": now_text(), "level": level, "message": message})
        STATE["events"] = STATE["events"][:80]


def json_response(handler: BaseHTTPRequestHandler, data: dict, status: int = 200) -> None:
    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def safe_output_file(path_text: str) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text).resolve()
    # Downloads outputs and local tool outputs are allowed for download links.
    allowed_roots = [ROOT.resolve(), Path.home().resolve()]
    try:
        if any(path == root or root in path.parents for root in allowed_roots):
            return path
    except OSError:
        return None
    return None


def make_downloads(input_path: Path, output_dir: Path | None = None, output_format: str = "all") -> list[dict]:
    out_dir = output_dir or input_path.parent
    exts = ("srt", "vtt", "txt") if output_format == "all" else (output_format,)
    downloads = []
    for ext in exts:
        path = out_dir / f"{input_path.stem}.{ext}"
        if path.exists():
            downloads.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "size": path.stat().st_size,
                    "url": "/download?path=" + urllib.parse.quote(str(path)),
                }
            )
    return downloads


def read_preview(downloads: list[dict]) -> str:
    for item in downloads:
        if item["name"].lower().endswith(".srt"):
            try:
                return Path(item["path"]).read_text(encoding="utf-8-sig")[:2000]
            except UnicodeDecodeError:
                return Path(item["path"]).read_text(encoding="utf-8", errors="replace")[:2000]
    return ""


def run_job(job: dict) -> None:
    input_path = Path(job["input_path"]).resolve()
    output_dir = Path(job["output_dir"]).resolve() if job.get("output_dir") else input_path.parent
    args = [
        str(PYTHON if PYTHON.exists() else sys.executable),
        str(CONVERTER),
        str(input_path),
        "--language",
        job.get("language") or "zh",
        "--model",
        job.get("model") or "medium",
        "--format",
        job.get("format") or "all",
        "--chinese",
        job.get("chinese") or "tw",
        "-o",
        str(output_dir),
    ]
    if job.get("vad_filter", True):
        args.append("--vad-filter")
    if not job.get("auto_correct", True):
        args.append("--no-auto-correct")

    with LOCK:
        STATE["job"] = {**job, "status": "running", "started_at": now_text(), "log": "", "downloads": []}
    add_event(f"開始轉字幕：{input_path.name}")

    try:
        proc = subprocess.run(
            args,
            cwd=str(ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60 * 60,
        )
        downloads = make_downloads(input_path, output_dir, job.get("format") or "all")
        preview = read_preview(downloads)
        status = "completed" if proc.returncode == 0 and downloads else "failed"
        with LOCK:
            STATE["job"].update(
                {
                    "status": status,
                    "finished_at": now_text(),
                    "returncode": proc.returncode,
                    "log": proc.stdout,
                    "downloads": downloads,
                    "preview": preview,
                }
            )
        if status == "completed":
            add_event(f"完成：產生 {len(downloads)} 個字幕/逐字稿檔案")
        else:
            add_event("轉字幕失敗，請查看執行記錄", "error")
    except Exception as exc:  # noqa: BLE001
        with LOCK:
            if STATE.get("job"):
                STATE["job"].update(
                    {
                        "status": "failed",
                        "finished_at": now_text(),
                        "error": str(exc),
                        "log": traceback.format_exc(),
                    }
                )
        add_event(f"轉字幕例外：{exc}", "error")


class Handler(BaseHTTPRequestHandler):
    server_version = "SubtitleTool/1.0"

    def log_message(self, fmt: str, *args) -> None:  # keep terminal clean-ish
        print(f"[{now_text()}] {self.address_string()} {fmt % args}")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self.serve_file(INDEX)
            return
        if parsed.path == "/api/status":
            with LOCK:
                payload = {"ok": True, "tool_dir": str(ROOT), "python": str(PYTHON if PYTHON.exists() else sys.executable), **STATE}
            json_response(self, payload)
            return
        if parsed.path == "/download":
            query = urllib.parse.parse_qs(parsed.query)
            path = safe_output_file(query.get("path", [""])[0])
            if not path or not path.exists() or not path.is_file():
                self.send_error(404, "file not found")
                return
            self.serve_file(path, download=True)
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/transcribe":
            self.api_transcribe()
            return
        if parsed.path == "/api/upload-and-transcribe":
            self.api_upload_and_transcribe()
            return
        self.send_error(404)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(raw or "{}")

    def start_job(self, job: dict) -> None:
        with LOCK:
            current = STATE.get("job")
            if current and current.get("status") == "running":
                json_response(self, {"ok": False, "error": "已有轉檔工作執行中，請等完成後再開始下一個。"}, 409)
                return
        thread = threading.Thread(target=run_job, args=(job,), daemon=True)
        thread.start()
        json_response(self, {"ok": True, "message": "已開始轉字幕", "job": job})

    def api_transcribe(self) -> None:
        try:
            data = self.read_json()
            input_path = Path(data.get("input_path", "")).expanduser().resolve()
            if not input_path.exists() or not input_path.is_file():
                json_response(self, {"ok": False, "error": f"找不到檔案：{input_path}"}, 400)
                return
            output_dir_text = data.get("output_dir") or ""
            output_dir = Path(output_dir_text).expanduser().resolve() if output_dir_text else input_path.parent
            output_dir.mkdir(parents=True, exist_ok=True)
            self.start_job(
                {
                    "input_path": str(input_path),
                    "output_dir": str(output_dir),
                    "language": data.get("language") or "zh",
                    "model": data.get("model") or "medium",
                    "format": data.get("format") or "all",
                    "chinese": data.get("chinese") or "tw",
                    "vad_filter": bool(data.get("vad_filter", True)),
                    "auto_correct": bool(data.get("auto_correct", True)),
                }
            )
        except Exception as exc:  # noqa: BLE001
            json_response(self, {"ok": False, "error": str(exc)}, 500)

    def api_upload_and_transcribe(self) -> None:
        try:
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
            file_item = form["media"] if "media" in form else None
            if not file_item or not getattr(file_item, "filename", ""):
                json_response(self, {"ok": False, "error": "請選擇影片或音檔。"}, 400)
                return
            filename = Path(file_item.filename).name
            target = UPLOADS / f"{int(time.time())}_{filename}"
            with target.open("wb") as f:
                shutil.copyfileobj(file_item.file, f)
            output_dir = Path(form.getfirst("output_dir") or target.parent).expanduser().resolve()
            output_dir.mkdir(parents=True, exist_ok=True)
            self.start_job(
                {
                    "input_path": str(target.resolve()),
                    "output_dir": str(output_dir),
                    "language": form.getfirst("language") or "zh",
                    "model": form.getfirst("model") or "medium",
                    "format": form.getfirst("format") or "all",
                    "chinese": form.getfirst("chinese") or "tw",
                    "vad_filter": form.getfirst("vad_filter", "true") == "true",
                    "auto_correct": form.getfirst("auto_correct", "true") == "true",
                }
            )
        except Exception as exc:  # noqa: BLE001
            json_response(self, {"ok": False, "error": str(exc)}, 500)

    def serve_file(self, path: Path, download: bool = False) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if download:
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(path.name)}")
        self.end_headers()
        self.wfile.write(data)


def main() -> int:
    ensure_dirs()
    port = int(os.environ.get("SUBTITLE_TOOL_PORT", "8766"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Subtitle UI: http://127.0.0.1:{port}/")
    print("Press Ctrl+C to stop.")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
