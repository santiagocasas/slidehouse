// Shared editor state and small DOM helpers.
// Every module reads from `state` rather than keeping its own copy, so the
// preview, the inspector and the clipboard always describe the same document.

export const state = {
  doc: null,
  deck: null,
  revision: '',
  saved: '',
  selected: 0,
  blockIndex: -1,
  docVersion: 0,
  generation: 0,
};

// Filled in by app.js. Keeping the UI callbacks here avoids circular imports
// between the modules that change the document and the ones that draw it.
export const services = {
  render() {},
  renderInspector() {},
  highlight() {},
  message() {},
  selectBlock() {},
  onSlideChanged() {},
  canvasSize() { return null; },
  attachClipboard() {},
  onPreviewReady() {},
  livePreview() { return null; },
};

export const parser = new DOMParser();
export const serialize = () => '<!DOCTYPE html>\n' + state.doc.documentElement.outerHTML;
export const container = () => state.doc.querySelector('.reveal .slides');
export const isStack = node => [...node.children].some(child => child.tagName === 'SECTION');

export function slides() {
  const result = [];
  [...container().children].filter(n => n.tagName === 'SECTION').forEach((node, h) => {
    if (isStack(node)) {
      [...node.children].filter(n => n.tagName === 'SECTION')
        .forEach((slide, v) => result.push({node: slide, h, v, vertical: true}));
    } else {
      result.push({node, h, v: 0, vertical: false});
    }
  });
  return result;
}

export const current = () => slides()[state.selected];
export const blocks = () => [...current().node.querySelectorAll('.sl-block')];

const clean = text => (text || '').replace(/\s+/g, ' ').trim().slice(0, 85);

// Slides.com exports rarely contain <h1> or <p>: the text sits in
// .sl-block-content wrappers. Read the real content so the outline is useful
// even for decks written by another tool.
export function autoTitle(node) {
  for (const heading of node.querySelectorAll('h1,h2,h3,h4')) {
    const text = clean(heading.textContent);
    if (text) return text;
  }
  for (const block of node.querySelectorAll('.sl-block[data-block-type="text"] .sl-block-content')) {
    const text = clean(block.textContent);
    if (text) return text;
  }
  for (const block of node.querySelectorAll('.sl-block-content')) {
    const text = clean(block.textContent);
    if (text) return text;
  }
  return 'Untitled slide';
}

// data-title is the editor's own name; it wins over the text on the slide and
// travels with the saved HTML.
export const title = node => clean(node.dataset.title) || autoTitle(node);
export const dirty = () => !!state.doc && serialize() !== state.saved;

export function freshIds(node) {
  const renamed = new Map();
  for (const el of [node, ...node.querySelectorAll('[data-id],[data-block-id]')]) {
    if (el.hasAttribute('data-id')) {
      const before = el.getAttribute('data-id');
      const after = crypto.randomUUID().replaceAll('-', '');
      el.dataset.id = after;
      if (before) renamed.set(before, after);
    }
    if (el.hasAttribute('data-block-id')) el.dataset.blockId = crypto.randomUUID().replaceAll('-', '');
  }
  return renamed;
}

export function setDocument(doc, {deck, revision, saved}) {
  state.doc = doc;
  state.deck = deck;
  state.revision = revision;
  state.saved = saved;
  state.docVersion++;
  state.selected = 0;
  state.blockIndex = -1;
}

export const cloneBlock = block => {
  const clone = block.cloneNode(true);
  clone.classList.remove('studio-selected');
  return clone;
};
