"""Command line entry point."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from . import __version__
from .server import serve


def _default_decks_dir() -> Path:
    configured = os.environ.get("SLIDEHOUSE_DECKS")
    if configured:
        return Path(configured).expanduser()
    here = Path.cwd()
    if any(here.glob("slides_*/index.html")):
        return here
    return here / "decks"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="slidehouse",
        description="Local-first editor for Reveal.js / Slides.com HTML decks.")
    parser.add_argument("--decks-dir", type=Path, default=None,
                        help="folder containing slides_*/index.html decks "
                             "(default: $SLIDEHOUSE_DECKS, the current folder if it has decks, else ./decks)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("SLIDEHOUSE_PORT", "8765")))
    parser.add_argument("--version", action="version", version=f"SlideHouse {__version__}")
    args = parser.parse_args(argv)

    decks_dir = (args.decks_dir or _default_decks_dir()).expanduser().resolve()
    if not decks_dir.is_dir():
        print(f"SlideHouse: deck folder not found: {decks_dir}", file=sys.stderr)
        print("Create it, or pass --decks-dir /path/to/your/slides", file=sys.stderr)
        return 2

    app_dir = Path(__file__).resolve().parent
    serve(app_dir, decks_dir, args.port)
    return 0
