# Changelog

## 0.1.0

First release.

### Added

- Standalone **SlideHouse** package (`pip install`, `slidehouse` command) that can
  point at any folder of `slides_*/index.html` decks.
- Copy/paste of a single element between slides, between decks and between tabs
  served by the same local instance.
- Text, shapes, images and editable LaTeX formulas.
- Appearance capture (fonts, colours, borders, backgrounds, spacing) so a pasted
  element keeps its look in a differently themed deck, without importing the
  source theme.
- Local assets and web fonts copied into the destination deck under
  `slidehouse-assets/`, making pasted content independent of the source deck.
- Uniform scaling for different slide canvas sizes.
- Fresh element identifiers and internal reference rewriting on paste.
- One undo step per paste.
- **Copy deck…** duplicates a saved deck, excluding backups and transient files.
- Deep links (`/?deck=slides_name`) for opening two decks side by side.
- Slide names in the outline: automatic from the slide text for decks made by
  other tools, with an optional custom name stored as `data-title`.
- Retained save conflict detection, per-save backups, standalone HTML download
  and headless-Chrome PDF export from the original editor.

### Known limitations

- One element at a time; no multi-selection or grouping.
- Cross-tab transfer requires one shared local server on one machine.
- Transfer ids expire when the server restarts.
- Copying does not garbage-collect assets left behind by an undo.
- PDF export requires Chrome or Chromium.
- Pasting a formula needs the destination deck to have a compatible math runtime.
