from __future__ import annotations

import json
import sys
import threading
import webbrowser
from datetime import date, datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from create_ekyte import CreateEkyteError, apply_created_to_row, create_web_task
from ignored import (
    MOTIVOS,
    apply_ignore,
    clear_ignore,
    ignore_thread,
    stamp_snapshot,
    unignore_thread,
)
from paths import OUTPUT, load_config

SNAPSHOT = OUTPUT / "snapshot.json"
CREATES_LOG = OUTPUT / "creates.jsonl"
_LOCK = threading.Lock()


def load_snapshot() -> dict:
    if not SNAPSHOT.exists():
        return {"pedidos": []}
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def save_snapshot(data: dict) -> None:
    SNAPSHOT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def find_row(snapshot: dict, thread: str) -> dict | None:
    for row in snapshot.get("pedidos") or []:
        if row.get("thread") == thread:
            return row
    return None


def replace_row(snapshot: dict, thread: str, updated: dict) -> dict:
    for idx, item in enumerate(snapshot.get("pedidos") or []):
        if item.get("thread") == thread:
            snapshot["pedidos"][idx] = updated
            break
    save_snapshot(snapshot)
    return updated


class RadarHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, password: str, **kwargs):
        self.password = password
        super().__init__(*args, directory=str(OUTPUT), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[radar] " + (fmt % args) + "\n")

    def _auth_ok(self) -> bool:
        header = (self.headers.get("X-Radar-Password") or "").strip()
        if header and header == self.password:
            return True
        auth = (self.headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            return auth.split(" ", 1)[1].strip() == self.password
        return False

    def _json(self, code: int, payload: dict) -> None:
        blob = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _read_json(self) -> tuple[dict | None, str | None]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 200_000:
            return None, "payload inválido"
        try:
            return json.loads(self.rfile.read(length).decode("utf-8")), None
        except json.JSONDecodeError:
            return None, "JSON inválido"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json(200, {"ok": True, "service": "web-seo-radar"})
            return
        if path == "/api/snapshot":
            if not self._auth_ok():
                self._json(401, {"ok": False, "error": "senha inválida"})
                return
            with _LOCK:
                self._json(200, stamp_snapshot(load_snapshot()))
            return
        if path in {"/", "/index.html"}:
            self.path = "/index.html"
        try:
            super().do_GET()
        except (BrokenPipeError, ConnectionResetError, FileNotFoundError):
            return

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/api/criar-task", "/api/ignorar", "/api/desfazer"}:
            self._json(404, {"ok": False, "error": "rota inexistente"})
            return
        if not self._auth_ok():
            self._json(401, {"ok": False, "error": "senha inválida"})
            return
        body, err = self._read_json()
        if err:
            self._json(400, {"ok": False, "error": err})
            return
        thread = str((body or {}).get("thread") or "").strip()
        if not thread:
            self._json(400, {"ok": False, "error": "thread ausente"})
            return
        if path == "/api/criar-task":
            self._criar_task(thread, body or {})
            return
        if path == "/api/ignorar":
            self._ignorar(thread, body or {})
            return
        self._desfazer(thread)

    def _criar_task(self, thread: str, body: dict) -> None:
        executor = str(body.get("executor") or "rafael").strip().lower()
        due_raw = str(body.get("due") or "").strip()
        due = None
        if due_raw:
            try:
                due = date.fromisoformat(due_raw[:10])
            except ValueError:
                self._json(400, {"ok": False, "error": "prazo inválido"})
                return
        with _LOCK:
            snapshot = load_snapshot()
            row = find_row(snapshot, thread)
            if not row:
                self._json(404, {"ok": False, "error": "pedido não está neste snapshot. Rode o radar de novo."})
                return
            try:
                result = create_web_task(row, executor, due)
            except CreateEkyteError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:  # noqa: BLE001
                self._json(500, {"ok": False, "error": f"falha ao criar a task: {exc}"})
                return
            unignore_thread(thread)
            updated = apply_created_to_row(clear_ignore(row), result)
            replace_row(snapshot, thread, updated)
            CREATES_LOG.parent.mkdir(parents=True, exist_ok=True)
            with CREATES_LOG.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "at": datetime.now().isoformat(timespec="seconds"),
                            "thread": thread,
                            "task_id": result.get("task_id"),
                            "task_url": result.get("task_url"),
                            "created": result.get("created"),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        self._json(200, {"ok": True, "pedido": updated, **result})

    def _ignorar(self, thread: str, body: dict) -> None:
        motivo = str(body.get("motivo") or "ja_resolvido").strip()
        if motivo not in MOTIVOS:
            motivo = "ja_resolvido"
        with _LOCK:
            snapshot = load_snapshot()
            row = find_row(snapshot, thread)
            if not row:
                self._json(404, {"ok": False, "error": "pedido não está neste snapshot. Rode o radar de novo."})
                return
            record = ignore_thread(thread, row, motivo)
            updated = apply_ignore(row, record)
            replace_row(snapshot, thread, updated)
        self._json(200, {"ok": True, "pedido": updated})

    def _desfazer(self, thread: str) -> None:
        with _LOCK:
            snapshot = load_snapshot()
            row = find_row(snapshot, thread)
            if not row:
                self._json(404, {"ok": False, "error": "pedido não está neste snapshot. Rode o radar de novo."})
                return
            unignore_thread(thread)
            updated = clear_ignore(row)
            replace_row(snapshot, thread, updated)
        self._json(200, {"ok": True, "pedido": updated})


def serve(port: int | None = None, open_browser: bool = False) -> None:
    config = load_config()
    port = int(port or (config.get("ekyte") or {}).get("serve_port") or 8768)
    password = str(config.get("gate_password") or "")
    handler = partial(RadarHandler, password=password)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"servidor em {url}  Ctrl+C para parar", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nservidor parado", flush=True)
    finally:
        httpd.server_close()
