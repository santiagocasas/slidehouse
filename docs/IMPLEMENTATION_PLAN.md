# v0.1 implementation plan

Status: implemented and verified. This file records the scope and the acceptance
criteria so a later change can be checked against the original intent.

## Goal

A local-first editor for Slides.com-style Reveal.js decks whose primary workflow
is reusing a single element across slides and decks, with assets and appearance
travelling with it.

## Decisions

| Question | Decision |
| --- | --- |
| Repository | Public `santiagocasas/slidehouse`, MIT for the app code |
| Deck location | Separate from the app (`--decks-dir`) |
| Clipboard scope | Same browser, same URL host, one SlideHouse server |
| Pasted look | Preserve the source appearance by default |
| Source of truth | The deck's `index.html`; no proprietary project file |
| Frontend | Native ES modules, no framework or build step |

## Phases and acceptance

### 0. Project

- Local folder and public GitHub repository.
- Application copied out of the course workspace; originals untouched.
- **Accepted:** `git remote -v` points at the repository; nothing pushed.

### 1. Extracted baseline

- `slidehouse` package, `--decks-dir`, rebranded shell.
- **Accepted:** an existing deck loads, edits, saves, presents and exports.

### 2. Refactor

- Backend split into `decks`, `assets`, `transfers`, `export`, `server`, `cli`.
- Frontend split into `state`, `history`, `api`, `elements`, `appearance`,
  `clipboard`, `preview`, `app`.
- **Accepted:** all behaviour from phase 1 still works; 26 backend tests pass.

### 3. Same-deck clipboard

- Versioned payload, canonical HTML, fresh ids, paste selection, undo.
- **Accepted:** text, shape, image and formula paste between slides; save/reload
  keeps them; undo/redo works.

### 4. Cross-tab transfer

- Staged asset snapshots, destination-owned copies, appearance capture, font
  importing, canvas scaling, sanitisation.
- **Accepted:** paste into another deck; delete the source deck; the image and
  font still load; a different canvas scales uniformly; a text field keeps
  native paste.

### 5. Deck reuse

- Duplicate deck, deep links.
- **Accepted:** `?deck=...` selects a deck; duplicate copies runtime and assets;
  collisions are refused.

### 6. Release

- Backend and browser test suites, example deck, documentation, changelog.
- **Accepted:** `python -m unittest discover -s tests -v` passes; the browser
  test passes with Playwright and Chrome; a clean `pip install .` serves its web
  assets from outside the checkout.

## Contract

The clipboard payload and the two transfer endpoints are specified in
`CLIPBOARD_FORMAT.md`. They are the compatibility boundary: change the version
when a field changes meaning.

## Out of scope for 0.1

Multi-selection, cross-machine clipboard, import from non-Reveal formats,
real-time collaboration, drag-and-resize editing, and automatic asset garbage
collection.
