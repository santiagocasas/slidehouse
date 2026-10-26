# Manual test checklist

Run through this before tagging a release. Automated coverage lives in
`tests/`; the checks below are the ones that need eyes on a rendered slide.

Start the server against a scratch copy of the example, never against real decks:

```bash
cp -r examples/slides_demo /tmp/slidehouse-decks/slides_demo
cp -r examples/slides_demo /tmp/slidehouse-decks/slides_dest
slidehouse --decks-dir /tmp/slidehouse-decks
```

## Same deck

- [ ] Select a text block; Ctrl/Cmd+C then Ctrl/Cmd+V on another slide.
- [ ] The pasted text keeps its font, size, colour and position.
- [ ] Copy a shape; the pasted shape keeps its fill and geometry.
- [ ] Copy an image; the pasted image displays without a broken-image icon.
- [ ] Copy a formula; the LaTeX remains editable in the inspector.
- [ ] Paste twice; the second copy is offset and visible.
- [ ] Undo once removes the last paste only; redo restores it.
- [ ] Save, reload the browser, reopen the deck: pasted elements are still there.

## Across decks

- [ ] Copy a text block in tab 1, paste in tab 2 (`?deck=slides_dest`), save.
- [ ] Copy an image, paste in tab 2, save. A file appears in
      `slides_dest/slidehouse-assets/`.
- [ ] Copy a formula, paste in tab 2, save. The formula renders.
- [ ] Delete the source deck folder, reload tab 2: pasted assets still load.
- [ ] Destination uses a different canvas size: the pasted element is scaled
      uniformly, not stretched.
- [ ] Destination uses a different theme: the pasted element keeps its own look,
      and the rest of the slide is unchanged.
- [ ] Text typed in the inspector textarea pastes as text, not as an element.

## Native clipboard behaviour

- [ ] Select body text in the preview and press Ctrl/Cmd+C: ordinary text copies.
- [ ] Paste ordinary text into the slide HTML panel: it appears as text.
- [ ] Copy from the element list button (not the keyboard): works.

## Deck operations

- [ ] Add, duplicate, delete and reorder a slide; vertical stacks still navigate.
- [ ] **Copy deck…** creates `slides_<name>` and opens it.
- [ ] **Copy deck…** refuses a name that already exists.
- [ ] Saving after an external edit is refused with a conflict message.
- [ ] A backup appears under `.slidehouse-backups/<deck>/` after each save.

## Export

- [ ] **Download HTML** produces a file that opens with no server running.
- [ ] **Export PDF** produces one page per slide (not a single page).
- [ ] A pasted, cross-deck element appears in both exports.

## Failure modes

- [ ] Restart the server, then paste an element copied before the restart: the
      message explains that the copy expired.
- [ ] Rename an image inside a deck before pasting: the message names the missing
      file, and the rest of the element still pastes.
- [ ] Stop the server while the editor is open: the preview explains the problem
      instead of failing silently.
