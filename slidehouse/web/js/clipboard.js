// Copying an element here and pasting it on another slide or another tab.
//
// The clipboard carries a versioned payload (see docs/CLIPBOARD_FORMAT.md).
// Local assets are staged on the server and materialized into the destination
// deck, so a pasted element keeps working after the source deck is removed.

import {api} from './api.js';
import {state, services, blocks, current, cloneBlock, freshIds} from './state.js';
import {mutate} from './history.js';
import {
  captureAppearance, applyAppearance, scaleAppearance, usedFamilies, captureFonts,
  applyFonts, renameAppearanceFamilies,
} from './appearance.js';

export const KIND = 'slidehouse.element';
export const VERSION = 1;
const STORAGE_KEY = 'slidehouse.clipboard.v1';
const MAX_TEXT = 2_000_000;

let prepared = null;          // {signature, payload} for the current selection
let prepareTimer = null;

const signature = () => {
  const block = blocks()[state.blockIndex];
  if (!block) return null;
  return `${state.deck}|${state.selected}|${state.blockIndex}|${block.outerHTML}`;
};

const textSelected = win => {
  try { return (win?.getSelection?.()?.toString() || '').trim().length > 0; } catch (_) { return false; }
};

const inTextField = target => {
  if (!target) return false;
  const tag = target.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable;
};

const deckBase = (deck = state.deck) => new URL('/decks/' + deck + '/', location.href);

function toRef(value, base) {
  const raw = (value || '').trim();
  if (!raw || /^data:/i.test(raw)) return null;
  try {
    const url = new URL(raw, base.href);
    if (url.origin !== base.origin || !url.href.startsWith(base.href)) return null;
    return decodeURIComponent(url.href.slice(base.href.length).split('#')[0].split('?')[0]);
  } catch (_) { return null; }
}

function collectRefs(node, appearance, extra = []) {
  const refs = new Set(extra.filter(Boolean));
  const add = value => { const ref = toRef(value, deckBase()); if (ref) refs.add(ref); };
  for (const element of [node, ...node.querySelectorAll('*')]) {
    for (const attr of ['src', 'data-src', 'poster', 'data-background-image']) {
      if (element.hasAttribute(attr)) add(element.getAttribute(attr));
    }
    if (['use', 'image'].includes(element.tagName.toLowerCase())) {
      for (const attr of ['href', 'xlink:href']) if (element.hasAttribute(attr)) add(element.getAttribute(attr));
    }
    for (const attr of ['srcset', 'data-srcset']) {
      if (element.hasAttribute(attr)) element.getAttribute(attr).split(',').forEach(part => add(part.trim().split(/\s+/)[0]));
    }
    const style = element.getAttribute('style');
    if (style) for (const match of style.matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)/gi)) add(match[1]);
    // A previously pasted element carries its own @font-face declarations.
    if (element.tagName === 'STYLE' && element.textContent) {
      for (const match of element.textContent.matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)/gi)) add(match[1]);
    }
  }
  for (const rule of appearance?.rules || []) {
    for (const value of Object.values(rule.props || {})) {
      for (const match of String(value).matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)/gi)) add(match[1]);
    }
  }
  return [...refs];
}

async function prepareSelected() {
  const block = blocks()[state.blockIndex];
  if (!block) throw new Error('Select an element first');
  const signatureBefore = signature();
  const clone = cloneBlock(block);
  const appearance = captureAppearance(services.liveBlock());
  // Fonts only matter for elements that actually show text.
  const families = clone.textContent.trim() ? usedFamilies(appearance) : [];
  const fonts = captureFonts(services.liveDocument(), families, deckBase().href);
  const refs = collectRefs(clone, appearance, fonts.map(face => face.ref));

  const staging = refs.length
    ? await api('/api/transfers/prepare', {deck: state.deck, refs})
    : {transferId: null, serverInstance: null, missing: []};
  if (staging.missing?.length) {
    services.message('Some files are missing and will not be copied: ' + staging.missing.join(', '), true);
  }

  const payload = {
    kind: KIND,
    version: VERSION,
    serverInstance: staging.serverInstance,
    transferId: staging.transferId,
    source: {
      deckId: state.deck,
      canvas: services.canvasSize(),
    },
    elementHtml: clone.outerHTML,
    appearance,
    fonts,
  };
  return {signature: signatureBefore, payload};
}

// Prefetch when a selection changes so Ctrl+C can answer synchronously.
export function refreshSelection() {
  prepared = null;
  clearTimeout(prepareTimer);
  if (state.blockIndex < 0) return;
  prepareTimer = setTimeout(async () => {
    const signatureBefore = signature();
    if (!signatureBefore) return;
    try {
      const result = await prepareSelected();
      if (result.signature === signature()) prepared = result;
    } catch (_) { /* the copy action will report the error */ }
  }, 150);
}

function persist(text) {
  try { localStorage.setItem(STORAGE_KEY, text); } catch (_) { /* private mode */ }
}

async function writeClipboard(text) {
  persist(text);
  try { await navigator.clipboard.writeText(text); } catch (_) { /* Paste button still works */ }
}

export async function copySelected() {
  if (state.blockIndex < 0) {
    services.message('Select an element to copy', true);
    return false;
  }
  services.message('Preparing element…');
  try {
    if (!prepared || prepared.signature !== signature()) prepared = await prepareSelected();
    const text = JSON.stringify(prepared.payload);
    if (text.length > MAX_TEXT) throw new Error('This element is too large to copy');
    await writeClipboard(text);
    services.message('Element copied · paste it on another slide or another SlideHouse tab');
    return true;
  } catch (error) {
    services.message(error.message, true);
    return false;
  }
}

function onCopy(event) {
  const win = event.target?.ownerDocument?.defaultView;
  if (inTextField(event.target) || textSelected(win) || state.blockIndex < 0) return;
  const currentSignature = signature();
  if (prepared?.signature === currentSignature) {
    const text = JSON.stringify(prepared.payload);
    event.preventDefault();
    event.clipboardData.setData('text/plain', text);
    persist(text);
    services.message('Element copied · paste it on another slide or another SlideHouse tab');
  } else {
    event.preventDefault();
    copySelected();
  }
}

function onPaste(event) {
  if (inTextField(event.target)) return;
  const text = event.clipboardData?.getData('text/plain') || '';
  if (!text.includes(KIND)) return;
  let payload;
  try { payload = JSON.parse(text); } catch (_) { return; }
  if (payload?.kind !== KIND) return;
  event.preventDefault();
  pastePayload(payload);
}

export function attachClipboard(doc) {
  if (!doc || doc.__slidehouseClipboard) return;
  doc.__slidehouseClipboard = true;
  doc.addEventListener('copy', onCopy);
  doc.addEventListener('paste', onPaste);
}

export async function pasteFromStorage() {
  let text = null;
  try { text = localStorage.getItem(STORAGE_KEY); } catch (_) { /* private mode */ }
  if (!text) {
    try { text = await navigator.clipboard.readText(); } catch (_) { text = null; }
  }
  if (!text) {
    services.message('Nothing copied yet. Select an element and press Copy first.', true);
    return false;
  }
  let payload;
  try { payload = JSON.parse(text); } catch (_) {
    services.message('The clipboard does not contain a SlideHouse element', true);
    return false;
  }
  return pastePayload(payload);
}

const BANNED = 'script,iframe,object,embed,link,meta,base,form';
const URL_ATTRIBUTES = ['href', 'src', 'xlink:href'];

function sanitize(node) {
  for (const element of node.querySelectorAll(BANNED)) element.remove();
  for (const element of [node, ...node.querySelectorAll('*')]) {
    element.classList.remove('studio-selected');
    for (const attr of [...element.attributes]) {
      const name = attr.name.toLowerCase();
      if (name.startsWith('on')) element.removeAttribute(attr.name);
      if (URL_ATTRIBUTES.includes(name) && /^\s*javascript:/i.test(attr.value)) element.removeAttribute(attr.name);
    }
  }
}

function rewriteCssValue(value, base, mapping) {
  return String(value).replace(/url\(\s*["']?([^"')]+)["']?\s*\)/gi, (whole, ref) => {
    const key = toRef(ref, base);
    return key && mapping[key] ? `url("${mapping[key]}")` : whole;
  });
}

function rewriteRefs(node, mapping, base) {
  const mapValue = value => {
    const key = toRef(value, base);
    return key && mapping[key] ? mapping[key] : value;
  };
  for (const element of [node, ...node.querySelectorAll('*')]) {
    for (const attr of ['src', 'data-src', 'poster', 'data-background-image']) {
      if (element.hasAttribute(attr)) element.setAttribute(attr, mapValue(element.getAttribute(attr)));
    }
    if (['use', 'image'].includes(element.tagName.toLowerCase())) {
      for (const attr of ['href', 'xlink:href']) {
        if (element.hasAttribute(attr)) element.setAttribute(attr, mapValue(element.getAttribute(attr)));
      }
    }
    for (const attr of ['srcset', 'data-srcset']) {
      if (!element.hasAttribute(attr)) continue;
      const parts = element.getAttribute(attr).split(',').map(part => {
        const bits = part.trim().split(/\s+/);
        bits[0] = mapValue(bits[0]);
        return bits.join(' ');
      });
      element.setAttribute(attr, parts.join(', '));
    }
    element.removeAttribute('data-lazy-loaded');
    const style = element.getAttribute('style');
    if (style && style.includes('url(')) element.setAttribute('style', rewriteCssValue(style, base, mapping));
    if (element.tagName === 'STYLE' && element.textContent?.includes('url(')) {
      element.textContent = rewriteCssValue(element.textContent, base, mapping);
    }
  }
}

function rewriteAppearanceRefs(appearance, mapping, base) {
  if (!appearance) return appearance;
  return {
    ...appearance,
    rules: (appearance.rules || []).map(rule => ({
      path: rule.path,
      props: Object.fromEntries(Object.entries(rule.props || {}).map(([name, value]) =>
        [name, String(value).includes('url(') ? rewriteCssValue(value, base, mapping) : value])),
    })),
  };
}

function rewriteInternalRefs(node, renamed) {
  if (!renamed.size) return;
  const replaceUrlId = value => value.replace(/url\(\s*#([^)"']+)\s*\)/g,
    (whole, id) => renamed.has(id) ? `url(#${renamed.get(id)})` : whole);
  for (const element of [node, ...node.querySelectorAll('*')]) {
    for (const attr of ['href', 'xlink:href', 'aria-labelledby', 'aria-describedby', 'aria-controls', 'for']) {
      if (!element.hasAttribute(attr)) continue;
      const value = element.getAttribute(attr);
      if (value.startsWith('#')) {
        const id = value.slice(1);
        if (renamed.has(id)) element.setAttribute(attr, '#' + renamed.get(id));
      } else if (attr.startsWith('aria-')) {
        element.setAttribute(attr, value.split(/\s+/).map(part => renamed.get(part) || part).join(' '));
      }
    }
    for (const attr of ['style', 'fill', 'stroke', 'clip-path', 'mask', 'filter']) {
      if (!element.hasAttribute(attr)) continue;
      const value = element.getAttribute(attr);
      if (value.includes('url(#')) element.setAttribute(attr, replaceUrlId(value));
    }
  }
}

function scaleLayout(node, factor) {
  for (const name of ['left', 'top', 'width', 'height']) {
    const value = node.style[name];
    if (!value || value === 'auto') continue;
    const pixels = parseFloat(value);
    if (Number.isFinite(pixels)) node.style[name] = `${(pixels * factor).toFixed(2)}px`;
  }
}

export async function pastePayload(payload) {
  if (!payload || payload.kind !== KIND || payload.version !== VERSION) {
    services.message('Unsupported element payload', true);
    return false;
  }
  if (typeof payload.elementHtml !== 'string' || payload.elementHtml.length > MAX_TEXT) {
    services.message('That element is too large to paste', true);
    return false;
  }
  if (!state.doc) {
    services.message('Load a deck first', true);
    return false;
  }

  const template = document.createElement('template');
  template.innerHTML = payload.elementHtml.trim();
  if (template.content.children.length !== 1) {
    services.message('The copied data is not a single element', true);
    return false;
  }
  const node = template.content.firstElementChild;
  if (!node?.classList?.contains('sl-block')) {
    services.message('The copied data is not a SlideHouse element', true);
    return false;
  }
  sanitize(node);

  const targetDeck = state.deck;
  const targetSlide = current().node;
  const version = state.docVersion;

  let mapping = {};
  if (payload.transferId) {
    services.message('Copying assets…');
    try {
      mapping = (await api('/api/transfers/materialize', {transferId: payload.transferId, deck: targetDeck})).refs || {};
    } catch (error) {
      services.message(error.message, true);
      return false;
    }
  }
  if (state.deck !== targetDeck || current().node !== targetSlide || state.docVersion !== version) {
    services.message('The deck or slide changed while copying; paste again', true);
    return false;
  }

  const sourceBase = deckBase(payload.source?.deckId || targetDeck);
  rewriteRefs(node, mapping, sourceBase);

  let appearance = rewriteAppearanceRefs(payload.appearance, mapping, sourceBase);
  const rename = applyFonts(node, payload.fonts, mapping);
  appearance = renameAppearanceFamilies(appearance, rename);

  const sourceCanvas = payload.source?.canvas;
  const destinationCanvas = services.canvasSize();
  const factor = sourceCanvas && destinationCanvas
    ? Math.min(destinationCanvas.width / sourceCanvas.width, destinationCanvas.height / sourceCanvas.height)
    : 1;
  if (factor !== 1) {
    scaleLayout(node, factor);
    appearance = scaleAppearance(appearance, factor);
  }
  applyAppearance(node, appearance);

  const left = parseFloat(node.style.left) || 0;
  const top = parseFloat(node.style.top) || 0;
  const clash = blocks().some(block => Math.abs((parseFloat(block.style.left) || 0) - left) < 2
    && Math.abs((parseFloat(block.style.top) || 0) - top) < 2);
  if (clash) {
    const step = 20 * Math.max(factor, 0.25);
    node.style.left = `${left + step}px`;
    node.style.top = `${top + step}px`;
  }

  rewriteInternalRefs(node, freshIds(node));

  mutate(() => {
    current().node.append(node);
    state.blockIndex = blocks().indexOf(node);
  });
  services.message('Pasted element');
  return true;
}
