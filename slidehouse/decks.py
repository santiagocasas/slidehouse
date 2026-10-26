"""Deck discovery, validation and the atomic save path.

A deck is a folder ``slides_<name>/`` containing an ``index.html`` written by
Slides.com (or by this editor). The folder is the unit of copying: its images,
fonts and reveal.js runtime travel with it.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

DECK_NAME = re.compile(r"^slides_[A-Za-z0-9_-]+$")
BACKUP_DIR = ".slidehouse-backups"
TRANSIENT = {".git", "__pycache__", ".ipynb_checkpoints", ".slidehouse-backups"}


class DeckError(ValueError):
    """A deck name, path or save request that cannot be honoured."""


class DeckChanged(DeckError):
    """The file on disk is not the revision the editor loaded."""


def check_name(name: str) -> str:
    if not isinstance(name, str) or not DECK_NAME.fullmatch(name):
        raise DeckError("Invalid deck name")
    return name


def deck_path(decks_dir: Path, name: str) -> Path:
    """Return the deck folder, refusing anything outside ``decks_dir``."""
    check_name(name)
    folder = (decks_dir / name).resolve()
    if not folder.is_dir() or not folder.is_relative_to(decks_dir.resolve()):
        raise DeckError("Deck not found")
    if not (folder / "index.html").is_file():
        raise DeckError("Deck not found")
    return folder


def list_decks(decks_dir: Path) -> list[dict]:
    decks = []
    for file in sorted(decks_dir.glob("slides_*/index.html")):
        try:
            folder = file.parent
            if not folder.is_dir():
                continue
            text = file.read_text(errors="replace")
            match = re.search(r"<title>(.*?)</title>", text, re.S)
            decks.append({"id": folder.name, "title": (match.group(1).strip() if match else folder.name)})
        except OSError:
            continue
    return decks


def revision(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_deck(decks_dir: Path, name: str) -> tuple[str, str]:
    data = (deck_path(decks_dir, name) / "index.html").read_bytes()
    return data.decode(), revision(data)


def _validate_document(html: str) -> bytes:
    if not isinstance(html, str) or "<html" not in html or 'class="slides"' not in html:
        raise DeckError("Expected a complete slide document")
    return html.encode()


def save_deck(decks_dir: Path, name: str, html: str, expected: str) -> dict:
    """Write ``index.html`` atomically, keeping the previous version as a backup."""
    folder = deck_path(decks_dir, name)
    path = folder / "index.html"
    original = path.read_bytes()
    if expected != revision(original):
        raise DeckChanged("This deck changed on disk. Download your work, then reload before saving.")
    data = _validate_document(html)

    backup_root = decks_dir / BACKUP_DIR / name
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{time.time_ns()}"
    (backup_root / f"{stamp}.html").write_bytes(original)

    fd, temporary = tempfile.mkstemp(dir=folder, prefix=".slidehouse-")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {
        "revision": revision(data),
        "backup": str((backup_root / f"{stamp}.html").relative_to(decks_dir)),
    }


def duplicate_deck(decks_dir: Path, source: str, destination: str) -> dict:
    """Copy a saved deck, excluding backups and other transient folders."""
    source_folder = deck_path(decks_dir, source)
    check_name(destination)
    if destination == source:
        raise DeckError("Choose a different name for the copy")
    target = decks_dir / destination
    if target.exists():
        raise DeckError("A deck with that name already exists")

    def ignore(_folder: str, names: list[str]) -> set[str]:
        return {name for name in names if name in TRANSIENT or name.startswith(".")}

    staging = Path(tempfile.mkdtemp(prefix=".slidehouse-copy-", dir=decks_dir))
    copied = staging / "deck"
    try:
        shutil.copytree(source_folder, copied, ignore=ignore)
        if not (copied / "index.html").is_file():
            raise DeckError("The source deck has no index.html")
        os.replace(copied, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(staging, ignore_errors=True)
    return {"id": destination}
