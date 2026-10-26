"""Asset handling shared by uploads, clipboard transfers and deck duplication."""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path
from urllib.parse import unquote

ASSET_DIR = "slidehouse-assets"

UPLOAD_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif"}
MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".svg": "image/svg+xml",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}

REMOTE = re.compile(r"^(?:[a-z][\w+.-]*:|//|/)", re.I)


class AssetError(ValueError):
    """An asset reference that cannot be resolved inside a deck."""


def safe_file(base: Path, ref: str) -> Path | None:
    """Resolve a relative reference inside ``base``.

    Returns ``None`` for data URIs, remote URLs and absolute paths: those are
    left untouched and the caller keeps the original reference.
    """
    ref = unquote(ref.split("#")[0].split("?")[0]).strip()
    if not ref or REMOTE.match(ref):
        return None
    path = (base / ref).resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file():
        return None
    return path


def store_upload(deck_dir: Path, name: str, data: str) -> str:
    """Decode and store an uploaded image under content-hashed name."""
    extension = Path(name or "").suffix.lower()
    if extension not in UPLOAD_SUFFIXES:
        raise AssetError("Choose a PNG, JPEG, GIF, WebP or AVIF image")
    try:
        raw = base64.b64decode(data, validate=True)
    except (ValueError, TypeError) as exc:
        raise AssetError("The image data is not valid base64") from exc
    if not raw:
        raise AssetError("The uploaded image is empty")
    folder = deck_dir / ASSET_DIR
    folder.mkdir(exist_ok=True)
    filename = f"{hashlib.sha256(raw).hexdigest()[:24]}{extension}"
    (folder / filename).write_bytes(raw)
    return f"{ASSET_DIR}/{filename}"


def import_asset(source: Path, destination_dir: Path, subdir: str = ASSET_DIR) -> str:
    """Copy ``source`` into ``destination_dir`` under a content-hashed name.

    The destination owns its own copy: deleting the source deck afterwards must
    not break the element that was pasted.
    """
    data = source.read_bytes()
    folder = destination_dir / subdir
    folder.mkdir(exist_ok=True)
    filename = f"{hashlib.sha256(data).hexdigest()[:24]}{source.suffix.lower()}"
    target = folder / filename
    if not target.exists():
        target.write_bytes(data)
    return f"{subdir}/{filename}"
