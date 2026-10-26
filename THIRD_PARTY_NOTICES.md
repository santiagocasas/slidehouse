# Third-party notices

The SlideHouse application code (`slidehouse/`) has no runtime dependencies
beyond the Python standard library.

## Bundled example deck

`examples/slides_demo/` is a small deck built on the runtime files of a
Slides.com HTML export, kept so the editor can be tried without any external
download. It includes:

- **Reveal.js** — MIT licence, © Hakim El Hattab and contributors.
  <https://revealjs.com>
- **KaTeX** — MIT licence, © Khan Academy and contributors.
  <https://katex.org>
- **Reveal.js plugins** (zoom, notes, markdown, highlight) — MIT licence.
- **highlight.js** — BSD 3-Clause licence.
- **Fonts** under `examples/slides_demo/lib/fonts/` (Montserrat, Open Sans,
  Lato, Merriweather Sans, Asul, Cabin Sketch, Josefin Sans, League,
  News Cycle, Oxygen, Overpass, Quicksand and others). Each family keeps its own
  licence; see the `*.css` and licence files in the respective font folder, and
  the upstream projects (most are SIL Open Font License 1.1).
- **Slides.com offline runtime** (`lib/offline.js`, `lib/offline-v2.css`) as
  shipped inside the HTML export. Its use here is limited to rendering decks in
  the same format; refer to the Slides.com terms for redistribution outside this
  example.

The example chart (`examples/slides_demo/assets/demo-chart.svg`) was generated
for SlideHouse and is covered by the project licence.

Do not relicense third-party files as SlideHouse code. If you replace the
example deck, keep the corresponding notices.
