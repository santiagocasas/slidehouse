"""The local HTTP server and its JSON API.

Only ``127.0.0.1`` is ever bound, writes are refused for foreign Host/Origin
headers, and static serving is restricted to the two roots the editor needs:
the application's own web assets and the deck folders.
"""

from __future__ import annotations

import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import threading
from urllib.parse import unquote, urlsplit

from . import __version__
from .assets import AssetError, store_upload
from .decks import (DeckChanged, DeckError, deck_path, duplicate_deck, list_decks,
                    read_deck, save_deck)
from .export import export_pdf, standalone_html
from .transfers import TransferError, TransferStore

MAX_BODY = 30_000_000
STATIC_SUFFIXES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".pdf": "application/pdf",
    ".map": "application/json",
}


class SlideCounter:
    """Count leaf <section> elements (one printed page each, before fragments)."""

    def __init__(self, html: str):
        self.leaves = 0
        self._depth = 0
        self._stack: list[bool] = []
        for match in re.finditer(r"<(/?)section\b[^>]*>", html, re.I):
            if match.group(1):
                if self._stack:
                    self.leaves += not self._stack.pop()
            else:
                if self._stack:
                    self._stack[-1] = True
                self._stack.append(False)

    @property
    def pages(self) -> int:
        return max(self.leaves, 1)


class App:
    def __init__(self, app_dir: Path, decks_dir: Path):
        self.app_dir = app_dir
        self.web_dir = app_dir / "web"
        self.decks_dir = decks_dir.resolve()
        self.transfers = TransferStore(self.decks_dir)
        self.lock = threading.Lock()
        self.pdf_lock = threading.Lock()

    def build_token(self) -> str:
        parts = []
        for name in ("index.html", "slidehouse.css", "js/app.js", "js/state.js", "js/history.js",
                     "js/api.js", "js/elements.js", "js/appearance.js", "js/clipboard.js",
                     "js/preview.js"):
            path = self.web_dir / name
            try:
                parts.append(f"{name}:{hashlib.sha256(path.read_bytes()).hexdigest()}")
            except OSError:
                parts.append(f"{name}:missing")
        parts.append(f"version:{__version__}")
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


class Handler(BaseHTTPRequestHandler):
    server_version = f"SlideHouse/{__version__}"

    # -- response helpers -------------------------------------------------
    @property
    def app(self) -> App:
        return self.server.app  # type: ignore[attr-defined]

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def reply(self, code: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_bytes(self, body: bytes, content_type: str, code: int = 200, headers: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_file(self, path: Path, download: str | None = None):
        content_type = STATIC_SUFFIXES.get(path.suffix.lower(), "application/octet-stream")
        headers = {"Content-Disposition": f'attachment; filename="{download}"'} if download else None
        self.send_bytes(path.read_bytes(), content_type, headers=headers)

    def send_studio(self):
        token = self.app.build_token()
        page = (self.app.web_dir / "index.html").read_text()
        page = page.replace("/app/slidehouse.css", f"/app/slidehouse.css?v={token}")
        page = page.replace("/app/js/app.js", f"/app/js/app.js?v={token}")
        page = page.replace("</head>", f'  <script>window.SLIDEHOUSE_BUILD="{token}";</script>\n</head>', 1)
        self.send_bytes(page.encode(), "text/html; charset=utf-8")

    # -- routing ----------------------------------------------------------
    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        try:
            if path == "/api/decks":
                return self.reply(200, list_decks(self.app.decks_dir))
            if path.startswith("/api/deck/"):
                html, rev = read_deck(self.app.decks_dir, path.removeprefix("/api/deck/"))
                return self.reply(200, {"html": html, "revision": rev})
            if path == "/api/build":
                return self.reply(200, {"build": self.app.build_token(), "version": __version__})
            if path in ("/", "/index.html"):
                return self.send_studio()
            if path.startswith("/app/"):
                return self.serve_static(self.app.web_dir, path.removeprefix("/app/"))
            if path.startswith("/decks/"):
                rest = path.removeprefix("/decks/")
                name, _, relative = rest.partition("/")
                folder = deck_path(self.app.decks_dir, name)
                return self.serve_static(folder, relative or "index.html")
            return self.reply(404, {"error": "Not found"})
        except (DeckError, OSError) as exc:
            return self.reply(404, {"error": str(exc)})

    def serve_static(self, root: Path, relative: str):
        if not relative or ".." in Path(relative).parts:
            return self.reply(404, {"error": "Not found"})
        target = (root / relative).resolve()
        if not target.is_relative_to(root.resolve()):
            return self.reply(403, {"error": "Not available"})
        if any(part.startswith(".") for part in target.relative_to(root.resolve()).parts):
            return self.reply(403, {"error": "Not available"})
        if target.is_dir():
            return self.reply(404, {"error": "Directory listing disabled"})
        if not target.is_file():
            return self.reply(404, {"error": "Not found"})
        return self.send_file(target)

    def do_HEAD(self):
        return self.do_GET()

    def do_POST(self):
        if self.headers.get("Host") not in {f"127.0.0.1:{self.server.server_port}",
                                            f"localhost:{self.server.server_port}"}:
            return self.reply(403, {"error": "Local host required"})
        origin = self.headers.get("Origin")
        if origin and origin != f'http://{self.headers.get("Host")}':
            return self.reply(403, {"error": "Cross-origin writes refused"})
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.reply(415, {"error": "Expected JSON"})
        route = urlsplit(self.path).path
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BODY:
                return self.reply(413, {"error": "Request must be under 30 MB"})
            body = json.loads(self.rfile.read(size))
            return self.handle_post(route, body)
        except DeckChanged as exc:
            return self.reply(409, {"error": str(exc)})
        except (DeckError, AssetError, TransferError) as exc:
            return self.reply(400, {"error": str(exc)})
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            return self.reply(400, {"error": f"Invalid request: {exc}"})
        except OSError as exc:
            return self.reply(500, {"error": str(exc)})

    def handle_post(self, route: str, body: dict):
        decks = self.app.decks_dir
        if route == "/api/save":
            with self.app.lock:
                return self.reply(200, save_deck(decks, body["deck"], body["html"], body["revision"]))
        if route == "/api/upload":
            with self.app.lock:
                path = deck_path(decks, body["deck"])
                stored = store_upload(path, body["name"], body["data"])
                return self.reply(200, {"path": stored})
        if route == "/api/decks/duplicate":
            with self.app.lock:
                return self.reply(200, duplicate_deck(decks, body["sourceDeck"], body["destinationDeck"]))
        if route == "/api/transfers/prepare":
            return self.reply(200, self.app.transfers.prepare(body["deck"], body["refs"]))
        if route == "/api/transfers/materialize":
            with self.app.lock:
                return self.reply(200, self.app.transfers.materialize(body["transferId"], body["deck"]))
        if route == "/api/export-html":
            path = deck_path(decks, body["deck"])
            data = standalone_html(body["html"], path).encode()
            return self.send_bytes(data, "text/html; charset=utf-8",
                                   headers={"Content-Disposition": f'attachment; filename="{path.name}.html"'})
        if route == "/api/export-pdf":
            path = deck_path(decks, body["deck"])
            html = (path / "index.html").read_text(errors="replace")
            pages = SlideCounter(html).pages
            url = f'http://127.0.0.1:{self.server.server_port}/decks/{path.name}/index.html?print-pdf'
            with self.app.pdf_lock:
                return self.reply(200, export_pdf(path / "index.html", url, pages))
        return self.reply(404, {"error": "Unknown operation"})


def serve(app_dir: Path, decks_dir: Path, port: int) -> None:
    app = App(app_dir, decks_dir)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.app = app  # type: ignore[attr-defined]
    print(f"SlideHouse {__version__}: http://127.0.0.1:{port}")
    print(f"Decks in {app.decks_dir}")
    print("Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.transfers.close()
