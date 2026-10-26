# Clipboard and transfer format (v1)

This document is the contract between the editor, the browser clipboard and the
local server. Treat it as the compatibility boundary for element copy/paste.

## Payload

The system clipboard carries JSON as `text/plain`. The same text is stored in
`localStorage` under `slidehouse.clipboard.v1` so the explicit **Paste element**
button works even when the browser blocks clipboard reads.

```json
{
  "kind": "slidehouse.element",
  "version": 1,
  "serverInstance": "9c1d...",
  "transferId": "5f0a...",
  "source": {
    "deckId": "slides_source",
    "canvas": {"width": 1280, "height": 720}
  },
  "elementHtml": "<div class=\"sl-block\" data-block-type=\"text\">...</div>",
  "appearance": {
    "version": 1,
    "rules": [
      {"path": [], "props": {"font-size": "40px", "color": "rgb(31, 31, 31)"}},
      {"path": [0, 1], "props": {"font-weight": "700"}}
    ]
  },
  "fonts": [
    {
      "family": "Montserrat",
      "weight": "400",
      "style": "normal",
      "unicodeRange": "U+0000-00FF",
      "ref": "lib/fonts/montserrat/montserrat-regular.woff"
    }
  ]
}
```

Field notes:

- `kind` and `version` are mandatory. Unknown versions are rejected.
- `transferId` is `null` when the element references no local files.
- `serverInstance` is informational; the server validates the transfer id against
  the running process, so a payload from a previous run fails cleanly.
- `source.canvas` is the Reveal.js canvas size where the element was copied.
- `elementHtml` is exactly one `.sl-block` element. Scripts and inline event
  handlers are removed on paste.
- `appearance.rules[].path` is the chain of element-child indices from the block
  root. `[]` is the root itself.
- `appearance` uses computed values captured from the live preview, not the
  stylesheet. Only allowlisted visual properties are captured.
- `fonts` lists the `@font-face` faces actually referenced by the captured
  `font-family` values. `ref` is relative to the source deck.

## Server API

### `POST /api/transfers/prepare`

```json
{"deck": "slides_source", "refs": ["assets/figure.svg", "lib/fonts/x.woff"]}
```

Returns:

```json
{
  "transferId": "5f0a...",
  "serverInstance": "9c1d...",
  "refs": {"assets/figure.svg": "0000.svg"},
  "missing": ["assets/gone.png"]
}
```

- Relative refs are resolved inside the source deck. Paths that escape it are
  reported as missing, never copied.
- `data:` URIs, absolute paths and `http(s)` URLs are ignored: the pasted element
  keeps those references unchanged.
- Files are staged in a temporary folder outside the decks directory.
- Duplicate refs collapse to one staged file.
- At most 128 refs per transfer.

### `POST /api/transfers/materialize`

```json
{"transferId": "5f0a...", "deck": "slides_dest"}
```

Returns:

```json
{"transferId": "5f0a...", "refs": {"assets/figure.svg": "slidehouse-assets/ab12.svg"}}
```

- Files are copied into `<destination>/slidehouse-assets/` with content-hashed
  names. Existing identical files are reused.
- A transfer id is valid only for the lifetime of the server process that
  created it. After a restart the paste fails with a clear message and the user
  copies the element again.
- The destination deck must exist.

## Paste rules

1. Reject anything that is not exactly one `.sl-block`.
2. Remove `script`, `iframe`, `object`, `embed`, `link`, `meta`, `base`, `form`.
3. Remove `on*` attributes and `javascript:` URLs.
4. Materialize assets, then rewrite `src`, `data-src`, `poster`,
   `data-background-image`, `srcset`, SVG `href`/`xlink:href`, and `url(...)`
   inside inline styles and captured appearance.
5. Rename imported font families to a unique `SlideHouse <hash>` family and
   inline a scoped `@font-face` block. This avoids clashing with a destination
   font that happens to share a name.
6. Apply the captured appearance, scaled by
   `min(destinationWidth/sourceWidth, destinationHeight/sourceHeight)`.
7. Regenerate `data-id` and `data-block-id` values, plus internal references.
8. Insert as one undoable change and select the new element.

Text fields and non-collapsed text selections keep native clipboard behaviour.
Only payloads whose `kind` matches are intercepted.
