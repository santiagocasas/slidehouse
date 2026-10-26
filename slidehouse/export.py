"""Standalone HTML download and headless-Chrome PDF export."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.parse import urlsplit
import urllib.request

from .assets import MIME, safe_file

BROWSERS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge")


def _data_uri(path: Path) -> str:
    mime = MIME.get(path.suffix.lower(), "application/octet-stream")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _local_file(base: Path, ref: str) -> Path | None:
    return safe_file(base, ref)


def _inline_css(css_path: Path, keep_import, seen=None) -> str:
    """Return CSS text with @imports expanded and url() files turned into data URIs."""
    seen = set() if seen is None else seen
    if css_path in seen:
        return ""
    seen.add(css_path)
    base = css_path.parent
    text = css_path.read_text(errors="replace")

    def expand(match):
        ref = match.group(1) or match.group(2)
        target = _local_file(base, ref)
        if target is None or not keep_import(target):
            return ""
        return _inline_css(target, keep_import, seen)

    text = re.sub(r"@import\s+(?:url\(\s*[\"']?([^\"')]+)[\"']?\s*\)|[\"']([^\"']+)[\"'])[^;]*;", expand, text)

    def url(match):
        target = _local_file(base, match.group(2))
        return f'url("{_data_uri(target)}")' if target else match.group(0)

    return re.sub(r"url\(\s*([\"']?)([^\"')]+)\1\s*\)", url, text)


def standalone_html(html: str, deck_dir: Path) -> str:
    """One HTML file that opens anywhere: CSS, scripts, fonts and media inlined.

    Only the deck's own theme font and KaTeX are embedded, not all bundled font
    families, which keeps the file a few MB instead of ten.
    """
    body = re.search(r'<body[^>]*class="([^"]*)"', html)
    theme = re.search(r"theme-font-([\w-]+)", body.group(1) if body else "")
    wanted = {"katex", "opensans", theme.group(1) if theme else "montserrat"}

    def keep_import(path):
        parts = path.relative_to(deck_dir).parts
        if "fonts" not in parts:
            return True
        rest = parts[parts.index("fonts") + 1:]
        return not rest or rest[0] in wanted

    def stylesheet(match):
        tag = match.group(0)
        href = re.search(r'href="([^"]+)"', tag)
        target = _local_file(deck_dir, href.group(1)) if href else None
        if target is None:
            return tag
        return "<style>\n" + _inline_css(target, keep_import) + "\n</style>"

    html = re.sub(r'<link\b[^>]*rel="stylesheet"[^>]*>', stylesheet, html)

    def script(match):
        target = _local_file(deck_dir, match.group(1))
        if target is None:
            return match.group(0)
        code = target.read_text(errors="replace").replace("</script", "<\\/script")
        return "<script>\n" + code + "\n</script>"

    html = re.sub(r'<script\b[^>]*\bsrc="([^"]+)"[^>]*>\s*</script>', script, html)

    cache: dict[Path, str] = {}

    def media(match):
        target = _local_file(deck_dir, match.group(2))
        if target is None:
            return match.group(0)
        if target not in cache:
            cache[target] = _data_uri(target)
        return f'{match.group(1)}="{cache[target]}"'

    return re.sub(r'\b(src|data-src|poster|data-background-image|data-background-video)="([^"]+)"', media, html)


def find_browser() -> str:
    explicit = os.environ.get("SLIDEHOUSE_CHROME") or os.environ.get("STUDIO_CHROME")
    if explicit:
        return explicit
    for name in BROWSERS:
        found = shutil.which(name)
        if found:
            return found
    raise ValueError("PDF export needs Chrome or Chromium; set SLIDEHOUSE_CHROME to its path")


class _DevTools:
    """Minimal Chrome DevTools Protocol client over a stdlib WebSocket."""

    def __init__(self, ws_url, timeout=60):
        parts = urlsplit(ws_url)
        self.sock = socket.create_connection((parts.hostname, parts.port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {parts.path} HTTP/1.1\r\nHost: {parts.netloc}\r\n"
                           "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise OSError("DevTools handshake failed")
            head += chunk
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise OSError("DevTools handshake refused")
        self.buffer = head.split(b"\r\n\r\n", 1)[1]
        self.next_id = 0

    def _read(self, n):
        while len(self.buffer) < n:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise OSError("DevTools connection closed")
            self.buffer += chunk
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    def _message(self):
        payload = b""
        while True:
            b1, b2 = self._read(2)
            length = b2 & 0x7F
            if length == 126:
                length = int.from_bytes(self._read(2), "big")
            elif length == 127:
                length = int.from_bytes(self._read(8), "big")
            mask = self._read(4) if b2 & 0x80 else None
            data = self._read(length)
            if mask:
                data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
            if b1 & 0x0F in (0x0, 0x1, 0x2):
                payload += data
                if b1 & 0x80:
                    return json.loads(payload)
            elif b1 & 0x0F == 0x8:
                raise OSError("DevTools connection closed")

    def call(self, method, **params):
        self.next_id += 1
        data = json.dumps({"id": self.next_id, "method": method, "params": params}).encode()
        header = bytes([0x81])
        if len(data) < 126:
            header += bytes([0x80 | len(data)])
        elif len(data) < 1 << 16:
            header += bytes([0x80 | 126]) + len(data).to_bytes(2, "big")
        else:
            header += bytes([0x80 | 127]) + len(data).to_bytes(8, "big")
        mask = os.urandom(4)
        self.sock.sendall(header + mask + bytes(c ^ mask[i % 4] for i, c in enumerate(data)))
        while True:
            reply = self._message()
            if reply.get("id") == self.next_id:
                if "error" in reply:
                    raise OSError(f"{method}: {reply['error'].get('message')}")
                return reply.get("result", {})

    def close(self):
        self.sock.close()


_PDF_READY = """(() => {
  const pages = document.querySelectorAll('.pdf-page').length;
  const images = [...document.images].every(img => img.complete);
  return JSON.stringify({pages, ready: document.readyState === 'complete' &&
    document.fonts.status === 'loaded' && images});
})()"""


def export_pdf(deck_path: Path, deck_url: str, expected_pages: int) -> dict:
    """Print the saved deck in reveal's print-pdf mode through headless Chrome.

    Chrome is driven over the DevTools protocol so the print waits until reveal
    has built one .pdf-page per slide; a plain --print-to-pdf can fire before
    that and produce a single page.
    """
    target = deck_path.parent / f"{deck_path.parent.name}.pdf"
    browser = find_browser()
    with tempfile.TemporaryDirectory(prefix="slidehouse-pdf-") as tmp:
        profile = Path(tmp) / "profile"
        proc = subprocess.Popen(
            [browser, "--headless=new", "--disable-gpu", "--no-first-run",
             "--no-default-browser-check", "--remote-debugging-port=0",
             "--remote-allow-origins=*", f"--user-data-dir={profile}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        devtools = None
        try:
            active = profile / "DevToolsActivePort"
            deadline = time.time() + 30
            while not (active.is_file() and active.read_text().strip()):
                if time.time() > deadline or proc.poll() is not None:
                    raise OSError("Chrome did not start for the PDF export")
                time.sleep(0.1)
            debug_port = int(active.read_text().split()[0])
            with urllib.request.urlopen(f"http://127.0.0.1:{debug_port}/json/list", timeout=10) as reply:
                page = next(t for t in json.load(reply) if t.get("type") == "page")
            devtools = _DevTools(page["webSocketDebuggerUrl"])
            devtools.call("Page.enable")
            devtools.call("Page.navigate", url=deck_url)
            deadline, state, stable = time.time() + 60, {}, 0
            while time.time() < deadline:
                time.sleep(0.25)
                result = devtools.call("Runtime.evaluate", expression=_PDF_READY, returnByValue=True)
                try:
                    state = json.loads(result["result"]["value"])
                except (KeyError, TypeError, ValueError):
                    continue
                stable = stable + 1 if state["ready"] and state["pages"] >= expected_pages else 0
                if stable >= 4:  # ready for one second: maths and layout have settled
                    break
            else:
                raise OSError(f"PDF export timed out: reveal laid out {state.get('pages', 0)} "
                              f"of {expected_pages} pages")
            result = devtools.call("Page.printToPDF", printBackground=True, preferCSSPageSize=True,
                                   displayHeaderFooter=False, marginTop=0, marginBottom=0,
                                   marginLeft=0, marginRight=0)
            data = base64.b64decode(result["data"])
        finally:
            if devtools:
                devtools.close()
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

    pages = len(re.findall(rb"/Type\s*/Page(?![s\w])", data))
    if pages < expected_pages:
        raise OSError(f"PDF export incomplete: got {pages} of {expected_pages} pages; try again")
    partial = target.with_suffix(".pdf.part")
    partial.write_bytes(data)
    os.replace(partial, target)
    return {"path": f"{deck_path.parent.name}/{target.name}", "pages": pages, "size": len(data)}
