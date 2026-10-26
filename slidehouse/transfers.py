"""Staging area for elements copied between decks.

Copying an element cannot simply keep the source-relative image path: the
destination deck must own its own files. A copy therefore runs in two steps:

1. ``prepare`` snapshots the referenced files into a temporary transfer folder.
2. ``materialize`` copies them into the destination deck on paste.

The clipboard payload only carries a transfer id, never the binary content.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
import uuid
from pathlib import Path

from .assets import AssetError, REMOTE, import_asset, safe_file

MAX_REFS = 128
MAX_REF_LENGTH = 512
MAX_TRANSFERS = 50


class TransferError(ValueError):
    """Unknown or expired transfer."""


class TransferStore:
    def __init__(self, decks_dir: Path, root: Path | None = None):
        self.decks_dir = decks_dir
        self.session_id = uuid.uuid4().hex
        self.root = Path(root or tempfile.mkdtemp(prefix="slidehouse-transfers-"))
        self.root.mkdir(parents=True, exist_ok=True)
        self._transfers: dict[str, float] = {}

    def _evict(self) -> None:
        while len(self._transfers) > MAX_TRANSFERS:
            oldest = min(self._transfers, key=self._transfers.get)
            self._transfers.pop(oldest, None)
            shutil.rmtree(self.root / oldest, ignore_errors=True)

    def prepare(self, deck_name: str, refs: list[str]) -> dict:
        from .decks import deck_path  # local import keeps module imports acyclic

        if not isinstance(refs, list) or len(refs) > MAX_REFS:
            raise AssetError("Too many asset references in this element")
        source = deck_path(self.decks_dir, deck_name)
        transfer_id = uuid.uuid4().hex
        folder = self.root / transfer_id
        folder.mkdir()

        mapping: dict[str, str] = {}
        missing: list[str] = []
        for ref in refs:
            if not isinstance(ref, str) or len(ref) > MAX_REF_LENGTH:
                raise AssetError("Invalid asset reference")
            if REMOTE.match(ref.strip()):
                continue  # external or data URI: stays as it is
            path = safe_file(source, ref)
            if path is None:
                missing.append(ref)
                continue
            name = f"{len(mapping):04d}{path.suffix.lower()}"
            shutil.copy2(path, folder / name)
            mapping[ref] = name

        (folder / "manifest.json").write_text(json.dumps({"refs": mapping}, indent=2))
        self._transfers[transfer_id] = time.time()
        self._evict()
        return {
            "transferId": transfer_id,
            "serverInstance": self.session_id,
            "refs": mapping,
            "missing": missing,
        }

    def materialize(self, transfer_id: str, deck_name: str) -> dict:
        from .decks import deck_path

        if transfer_id not in self._transfers:
            raise TransferError("This copied element expired (the editor was restarted). Copy it again.")
        folder = self.root / transfer_id
        manifest = json.loads((folder / "manifest.json").read_text())
        mapping = manifest.get("refs", {})
        destination = deck_path(self.decks_dir, deck_name)
        rewritten = {}
        for ref, name in mapping.items():
            rewritten[ref] = import_asset(folder / name, destination)
        return {"transferId": transfer_id, "refs": rewritten}

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
        self._transfers.clear()
