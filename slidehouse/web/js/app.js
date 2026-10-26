// SlideHouse editor shell: wiring, outline, inspector and file actions.

import {api} from './api.js';
import {
  state, services, parser, serialize, container, slides, blocks, current, title, autoTitle, dirty,
  setDocument, freshIds,
} from './state.js';
import {mutate, resetHistory, undo, redo, canUndo, canRedo} from './history.js';
import {newBlock} from './elements.js';
import {
  previewHTML, renderPreview, highlight, liveDocument, liveBlock, canvasSize,
} from './preview.js';
import {copySelected, pasteFromStorage, attachClipboard, refreshSelection} from './clipboard.js';

const $ = id => document.getElementById(id);
const BUILD = window.SLIDEHOUSE_BUILD || 'unversioned';

function banner(text) {
  const box = document.createElement('div');
  box.id = 'slidehouse-banner';
  box.textContent = text;
  box.style.cssText = 'position:fixed;inset:0 0 auto 0;z-index:9999;padding:14px 18px;'
    + 'background:#5b1d1d;color:#ffe9e9;font:14px/1.5 system-ui,sans-serif';
  document.body.prepend(box);
}

const message = (text, error = false) => {
  $('status').textContent = text;
  $('status').classList.toggle('error', error);
};

function controls() {
  $('undo').disabled = !canUndo();
  $('redo').disabled = !canRedo();
  $('save').textContent = dirty() ? 'Save •' : 'Saved';
  const hasElement = !!state.doc && state.blockIndex >= 0;
  $('copy-element').disabled = !hasElement;
  $('paste-element').disabled = !state.doc;
}

function button(text, cls, action) {
  const element = document.createElement('button');
  element.textContent = text;
  element.className = cls;
  element.onclick = action;
  return element;
}

function render(skipPreview = false) {
  const list = slides();
  if (!list.length) return;
  state.selected = Math.min(Math.max(0, state.selected), list.length - 1);
  $('count').textContent = list.length;

  $('outline').replaceChildren();
  list.forEach((slide, index) => {
    const item = button(`${index + 1}. ${title(slide.node)}`,
      'slide' + (index === state.selected ? ' active' : '') + (slide.vertical ? ' vertical' : ''), () => {
        state.selected = index;
        state.blockIndex = -1;
        render();
      });
    item.title = 'Double-click to rename this slide';
    item.ondblclick = () => {
      state.selected = index;
      state.blockIndex = -1;
      render(true);
      $('slide-name').focus();
      $('slide-name').select();
    };
    const small = document.createElement('small');
    small.textContent = slide.vertical
      ? `Stack ${slide.h + 1} · ${slide.v + 1}`
      : `${slide.node.querySelectorAll('.sl-block').length} elements`;
    item.append(small);
    $('outline').append(item);
  });

  $('slide-title').textContent = `${state.selected + 1} / ${list.length} · ${title(current().node)}`;
  $('source').value = current().node.outerHTML;

  $('elements').replaceChildren();
  blocks().forEach((block, index) => {
    const type = block.dataset.blockType || 'block';
    const item = button(`${index + 1} · ${type}`, 'element' + (index === state.blockIndex ? ' active' : ''), () => {
      services.selectBlock(index);
    });
    const small = document.createElement('small');
    small.textContent = (block.textContent.trim().replace(/\s+/g, ' ') || block.dataset.name || 'Media / shape').slice(0, 85);
    item.append(small);
    $('elements').append(item);
  });

  renderInspector();
  if (!skipPreview) renderPreview();
  controls();
  refreshSelection();
}

function field(parent, label, value, id, multiline = false) {
  const caption = document.createElement('label');
  caption.textContent = label;
  caption.htmlFor = id;
  const input = document.createElement(multiline ? 'textarea' : 'input');
  input.id = id;
  input.value = value;
  parent.append(caption, input);
  return input;
}

function renameSlide(value) {
  const node = current().node;
  const name = value.trim();
  mutate(() => {
    if (name) node.dataset.title = name;
    else delete node.dataset.title;
  });
}

function renderInspector() {
  const panel = $('inspector');
  panel.replaceChildren();

  const section = current().node;
  const nameField = field(panel, 'Slide name', section.dataset.title || '', 'slide-name');
  nameField.placeholder = `Auto: ${autoTitle(section)}`;
  nameField.onchange = () => renameSlide(nameField.value);
  const hint = document.createElement('small');
  hint.className = 'hint';
  hint.textContent = 'Leave empty to name the slide from its text.';
  panel.append(hint);

  const block = blocks()[state.blockIndex];
  if (!block) {
    const empty = document.createElement('p');
    empty.className = 'hint';
    empty.textContent = 'Select an element to edit its content and layout.';
    panel.append(empty);
    return;
  }
  const content = block.querySelector('.sl-block-content');
  const type = block.dataset.blockType;
  const heading = document.createElement('strong');
  heading.textContent = `Edit ${type || 'block'}`;
  panel.append(heading);

  let edit = null;
  if (type === 'text') edit = field(panel, 'Content HTML (preserves formatting)', content.innerHTML, 'content', true);
  else if (type === 'math') edit = field(panel, 'LaTeX', block.querySelector('.math-input')?.textContent || '', 'content', true);
  else if (type === 'image') {
    const img = block.querySelector('img');
    edit = field(panel, 'Image path (relative to deck)', img?.getAttribute('data-src') || img?.getAttribute('src') || '', 'content');
    panel.append(button('Upload replacement image', '', () => { uploadingNew = false; $('image-file').click(); }));
  } else {
    const note = document.createElement('p');
    note.className = 'muted';
    note.textContent = 'Edit layout below, or use Advanced slide HTML for this element’s content.';
    panel.append(note);
  }

  const grid = document.createElement('div');
  grid.className = 'grid';
  panel.append(grid);
  const inputs = {};
  for (const [key, label] of [['left', 'X'], ['top', 'Y'], ['width', 'Width'], ['height', 'Height']]) {
    const cell = document.createElement('div');
    grid.append(cell);
    inputs[key] = field(cell, label + ' (px / auto)', block.style[key] || 'auto', key);
  }
  const font = field(panel, 'Font size (e.g. 75% or 28px)', content?.style.fontSize || '', 'font');
  const color = field(panel, 'Text color (CSS)', content?.style.color || '', 'color');

  const actions = document.createElement('div');
  actions.className = 'actions';
  panel.append(actions);
  actions.append(
    button('Apply changes', 'primary', () => {
      const values = {};
      for (const [key, input] of Object.entries(inputs)) {
        let value = input.value.trim();
        if (/^-?\d+(\.\d+)?$/.test(value)) value += 'px';
        if (!CSS.supports(key, value)) return message(`Invalid ${key}: ${value}`, true);
        values[key] = value;
      }
      if (font.value && !CSS.supports('font-size', font.value)) return message('Invalid font size', true);
      if (color.value && !CSS.supports('color', color.value)) return message('Invalid color', true);
      mutate(() => {
        Object.assign(block.style, values);
        if (content) {
          content.style.fontSize = font.value;
          content.style.color = color.value;
        }
        if (type === 'text') content.innerHTML = edit.value;
        if (type === 'math') block.querySelector('.math-input').textContent = edit.value;
        if (type === 'image') {
          let img = block.querySelector('img');
          if (!img) {
            img = state.doc.createElement('img');
            content.append(img);
          }
          img.removeAttribute('src');
          img.removeAttribute('data-lazy-loaded');
          img.setAttribute('data-src', edit.value);
        }
      });
    }),
    button('Delete element', '', () => mutate(() => {
      block.remove();
      state.blockIndex = -1;
    })),
  );
}

services.message = message;
services.render = () => render();
services.renderInspector = renderInspector;
services.highlight = highlight;
services.canvasSize = canvasSize;
services.liveDocument = liveDocument;
services.liveBlock = liveBlock;
services.attachClipboard = attachClipboard;
services.onPreviewReady = () => refreshSelection();
services.selectBlock = index => {
  state.blockIndex = index;
  renderInspector();
  highlight();
  [...$('elements').children].forEach((item, position) => item.classList.toggle('active', position === index));
  controls();
  refreshSelection();
};
services.onSlideChanged = (h, v) => {
  const index = slides().findIndex(slide => slide.h === h && slide.v === v);
  if (index !== -1 && index !== state.selected) {
    state.selected = index;
    state.blockIndex = -1;
    render(true);
    message(`Slide ${index + 1} / ${slides().length}`);
  }
};

// --- loading -------------------------------------------------------------
function rememberDeck(id) {
  try { history.replaceState(null, '', id ? '?deck=' + encodeURIComponent(id) : location.pathname); } catch (_) {}
}

async function load(id) {
  if (dirty() && !confirm('Discard unsaved changes and load the deck from disk?')) {
    $('decks').value = state.deck;
    return;
  }
  try {
    const result = await api('/api/deck/' + encodeURIComponent(id));
    setDocument(parser.parseFromString(result.html, 'text/html'), {deck: id, revision: result.revision, saved: ''});
    state.saved = serialize();
    resetHistory();
    $('decks').value = id;
    rememberDeck(id);
    render();
    message('Loaded from disk · changes are saved only when you click Save');
  } catch (error) {
    message(error.message, true);
  }
}

async function refreshDeckList(select = state.deck) {
  try {
    const decks = await api('/api/decks');
    $('decks').replaceChildren();
    for (const item of decks) {
      const option = document.createElement('option');
      option.value = item.id;
      option.textContent = item.title;
      $('decks').append(option);
    }
    if (select) $('decks').value = select;
    return decks;
  } catch (error) {
    message(error.message, true);
    return [];
  }
}

// --- file actions --------------------------------------------------------
async function saveDeck() {
  if (!state.doc) return;
  const html = serialize();
  const savingDeck = state.deck;
  try {
    $('save').disabled = true;
    const result = await api('/api/save', {deck: state.deck, revision: state.revision, html});
    if (state.deck === savingDeck) {
      state.revision = result.revision;
      state.saved = html;
      controls();
    }
    message('Saved · backup: ' + result.backup);
  } catch (error) {
    message(error.message, true);
  } finally {
    $('save').disabled = false;
  }
}

async function downloadHtml() {
  if (!state.doc) return message('Load a presentation first', true);
  try {
    $('download').disabled = true;
    message('Building standalone HTML…');
    let response;
    try {
      response = await fetch('/api/export-html', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({deck: state.deck, html: serialize()}),
      });
    } catch (_) { throw new Error('Cannot reach the SlideHouse server'); }
    if (!response.ok) {
      let text = response.statusText;
      try { text = (await response.json()).error || text; } catch (_) {}
      throw new Error(text);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = state.deck + '.html';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    message('Downloaded ' + state.deck + '.html · self-contained ('
      + (blob.size / 1e6).toFixed(1) + ' MB)');
  } catch (error) {
    message(error.message, true);
  } finally {
    $('download').disabled = false;
  }
}

async function exportPdf() {
  if (!state.doc) return message('Load a presentation first', true);
  if (dirty()) return message('Save first: the PDF is printed from the saved deck', true);
  try {
    $('export-pdf').disabled = true;
    message('Exporting PDF… this takes about 20 s');
    const result = await api('/api/export-pdf', {deck: state.deck});
    message('PDF: ' + result.path + ' · ' + result.pages + ' pages');
    window.open('/decks/' + result.path, '_blank');
  } catch (error) {
    message(error.message, true);
  } finally {
    $('export-pdf').disabled = false;
  }
}

async function duplicateDeck() {
  if (!state.doc) return message('Load a presentation first', true);
  if (dirty()) return message('Save this deck before copying it', true);
  const suggested = state.deck + '-copy';
  const name = prompt('Name for the new deck (must start with "slides_")', suggested);
  if (name === null) return;
  const destination = name.trim();
  if (!/^slides_[A-Za-z0-9_-]+$/.test(destination)) return message('Use slides_ followed by letters, digits, - or _', true);
  try {
    const result = await api('/api/decks/duplicate', {sourceDeck: state.deck, destinationDeck: destination});
    await refreshDeckList(result.id);
    await load(result.id);
    message('Copied deck to ' + result.id);
  } catch (error) {
    message(error.message, true);
  }
}

// --- slide and element actions ------------------------------------------
function addSlide() {
  mutate(() => {
    const node = state.doc.createElement('section');
    node.dataset.id = crypto.randomUUID().replaceAll('-', '');
    const background = current().node.getAttribute('data-background-color');
    if (background) node.setAttribute('data-background-color', background);
    current().node.after(node);
    state.selected = slides().findIndex(slide => slide.node === node);
    newBlock('text');
  });
}

function duplicateSlide() {
  mutate(() => {
    const node = current().node.cloneNode(true);
    freshIds(node);
    current().node.after(node);
    state.selected = slides().findIndex(slide => slide.node === node);
    state.blockIndex = -1;
  });
}

function deleteSlide() {
  if (slides().length === 1) return message('Keep at least one slide', true);
  if (!confirm('Delete this slide? You can undo this change.')) return;
  mutate(() => {
    const node = current().node;
    const parent = node.parentElement;
    node.remove();
    if (parent !== container() && parent.children.length === 0) parent.remove();
    state.selected = Math.min(state.selected, slides().length - 1);
    state.blockIndex = -1;
  });
}

function moveSlide(direction) {
  const node = current().node;
  const sibling = direction < 0 ? node.previousElementSibling : node.nextElementSibling;
  if (!sibling || sibling.tagName !== 'SECTION') return message('Reached the edge of this slide stack');
  mutate(() => {
    if (direction < 0) sibling.before(node);
    else sibling.after(node);
    state.selected = slides().findIndex(slide => slide.node === node);
  });
}

function navigate(step) {
  if (!state.doc) return;
  const list = slides();
  const next = state.selected + step;
  if (next < 0) return message('Already at the first slide');
  if (next >= list.length) return message('Already at the last slide');
  state.selected = next;
  state.blockIndex = -1;
  render();
  message(`Slide ${next + 1} / ${list.length}`);
}

let uploadingNew = false;

// --- wiring --------------------------------------------------------------
const missing = ['decks', 'reload', 'undo', 'redo', 'copy-element', 'paste-element', 'duplicate-deck',
  'download', 'export-pdf', 'save', 'present', 'count', 'add-slide', 'duplicate', 'delete-slide',
  'up', 'down', 'outline', 'prev-slide', 'next-slide', 'slide-title', 'preview', 'source',
  'apply-source', 'add-text', 'add-math', 'add-image', 'elements', 'inspector', 'status', 'image-file']
  .filter(id => !$(id));
if (missing.length) {
  banner('This tab is running an outdated cached copy of SlideHouse (missing: ' + missing.join(', ')
    + '). Press Ctrl+Shift+R (⌘⇧R on macOS) to reload it.');
  throw new Error('SlideHouse shell out of date: ' + missing.join(', '));
}

$('decks').onchange = () => load($('decks').value);
$('reload').onclick = () => load(state.deck);
$('undo').onclick = undo;
$('redo').onclick = redo;
$('copy-element').onclick = () => copySelected();
$('paste-element').onclick = () => pasteFromStorage();
$('duplicate-deck').onclick = duplicateDeck;
$('save').onclick = saveDeck;
$('download').onclick = downloadHtml;
$('export-pdf').onclick = exportPdf;
$('present').onclick = () => {
  if (!state.doc) return message('Load a presentation first', true);
  if (!dirty()) {
    const win = window.open('/decks/' + state.deck + '/index.html', '_blank');
    if (!win) return message('Allow pop-ups to open the presentation', true);
    win.focus();
    return message('Presenting the saved deck · arrows / space to advance');
  }
  const win = window.open('about:blank', '_blank');
  if (!win) return message('Allow pop-ups to open the presentation', true);
  win.document.open();
  win.document.write(previewHTML(true));
  win.document.close();
  win.focus();
  message('Presenting your unsaved edits · save for the full-fidelity version');
};
$('add-slide').onclick = addSlide;
$('duplicate').onclick = duplicateSlide;
$('delete-slide').onclick = deleteSlide;
$('up').onclick = () => moveSlide(-1);
$('down').onclick = () => moveSlide(1);
$('prev-slide').onclick = () => navigate(-1);
$('next-slide').onclick = () => navigate(1);
$('add-text').onclick = () => mutate(() => newBlock('text'));
$('add-math').onclick = () => mutate(() => newBlock('math'));
$('add-image').onclick = () => { uploadingNew = true; $('image-file').click(); };

$('image-file').onchange = async event => {
  const file = event.target.files[0];
  if (!file) return;
  const targetDeck = state.deck;
  const targetSlide = current().node;
  const block = blocks()[state.blockIndex];
  const add = uploadingNew;
  try {
    if (file.size > 20_000_000) throw new Error('Choose an image smaller than 20 MB');
    const data = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
    const result = await api('/api/upload', {deck: targetDeck, name: file.name, data});
    if (state.deck !== targetDeck || current().node !== targetSlide
        || (!add && blocks()[state.blockIndex] !== block)) {
      throw new Error('Selection changed during upload. Image saved to ' + result.path + '; select its path to use it.');
    }
    mutate(() => {
      if (add) newBlock('image', result.path);
      else {
        let img = block.querySelector('img');
        if (!img) {
          img = state.doc.createElement('img');
          block.querySelector('.sl-block-content').append(img);
        }
        img.removeAttribute('src');
        img.removeAttribute('data-lazy-loaded');
        img.dataset.src = result.path;
      }
    });
  } catch (error) {
    message(error.message, true);
  }
  event.target.value = '';
};

$('apply-source').onclick = () => {
  const template = document.createElement('template');
  template.innerHTML = $('source').value.trim();
  const node = template.content.firstElementChild;
  if (!node || node.tagName !== 'SECTION' || template.content.children.length !== 1 || node.querySelector('section')) {
    return message('Enter one leaf <section> (no nested slides)', true);
  }
  mutate(() => {
    current().node.replaceWith(node);
    state.blockIndex = -1;
  });
};

window.addEventListener('beforeunload', event => {
  if (dirty()) {
    event.preventDefault();
    event.returnValue = '';
  }
});

document.addEventListener('keydown', event => {
  const modifier = event.ctrlKey || event.metaKey;
  const target = event.target;
  const typing = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA'
    || target.tagName === 'SELECT' || target.isContentEditable);
  if (modifier && event.key.toLowerCase() === 's') {
    event.preventDefault();
    $('save').click();
    return;
  }
  if (modifier && event.key.toLowerCase() === 'z') {
    if (typing) return;
    event.preventDefault();
    if (event.shiftKey) redo(); else undo();
    return;
  }
  if (modifier && event.key.toLowerCase() === 'y') {
    if (typing) return;
    event.preventDefault();
    redo();
    return;
  }
  if (modifier || event.altKey || !state.doc || typing) return;
  const step = {ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1}[event.key];
  if (!step) return;
  event.preventDefault();
  navigate(step);
});

attachClipboard(document, window);

(async () => {
  const tagline = document.querySelector('footer span:last-child');
  if (tagline) tagline.textContent = 'Local-first · HTML files · build ' + BUILD;
  try {
    const live = await api('/api/build');
    if (live.build !== BUILD && sessionStorage.getItem('slidehouse-refresh') !== live.build) {
      sessionStorage.setItem('slidehouse-refresh', live.build);
      return location.replace('/?v=' + live.build);
    }
    const decks = await refreshDeckList(null);
    if (!decks.length) return message('No slides_*/index.html decks found in the configured folder', true);
    const requested = new URLSearchParams(location.search).get('deck');
    const initial = decks.some(deck => deck.id === requested) ? requested : decks[0].id;
    await load(initial);
  } catch (error) {
    message(error.message, true);
  }
})();
