// The live Reveal.js preview iframe.

import {state, services, current} from './state.js';

const frame = () => document.getElementById('preview');

export function previewHTML(present = false) {
  const clone = state.doc.cloneNode(true);
  const base = clone.createElement('base');
  base.href = new URL('/decks/' + state.deck + '/', location.href).href;
  clone.head.prepend(base);

  // srcdoc documents have no history, and Reveal's hash option would throw on
  // every slide change.
  const guard = clone.createElement('script');
  guard.textContent = "if(location.protocol!=='http:'&&location.protocol!=='https:'){history.replaceState=history.pushState=function(){};}";
  clone.head.prepend(guard);

  if (!present) {
    const style = clone.createElement('style');
    style.textContent = '.studio-selected{outline:3px solid #94e1c0!important;outline-offset:5px}'
      + '.reveal .slides .fragment{opacity:1!important;visibility:visible!important}'
      + '.sl-block{cursor:pointer!important}';
    clone.head.append(style);
  }

  const script = clone.createElement('script');
  const slide = current();
  script.textContent = 'window.addEventListener("load",()=>{const run=()=>{Reveal.configure('
    + (present ? '{}' : '{controls:true,keyboard:true,touch:true,autoSlide:0,loop:false,transition:"none"}')
    + ');Reveal.slide(' + slide.h + ',' + slide.v + ');};if(Reveal.isReady())run();else Reveal.on("ready",run);});';
  clone.body.append(script);
  return '<!DOCTYPE html>\n' + clone.documentElement.outerHTML;
}

export function renderPreview() {
  const view = frame();
  const token = ++state.generation;
  const version = state.docVersion;
  const deckId = state.deck;
  const win = view.contentWindow;

  // Same deck and same document: just move the live preview, no reload flicker.
  if (view.dataset.deck === deckId && Number(view.dataset.version) === version && win?.Reveal?.isReady()) {
    try {
      const slide = current();
      win.Reveal.slide(slide.h, slide.v);
      highlight();
      return;
    } catch (_) { /* fall through and reload */ }
  }

  view.style.opacity = '0';
  const failsafe = setTimeout(() => {
    if (state.generation !== token) return;
    view.style.opacity = '1';
    services.message('Preview could not finish loading. Is the SlideHouse server still running? Click Reload.', true);
  }, 10000);

  view.onload = () => {
    if (state.generation !== token) { clearTimeout(failsafe); return; }
    view.dataset.deck = deckId;
    view.dataset.version = String(version);
    const live = view.contentWindow;
    const attach = () => {
      clearTimeout(failsafe);
      if (state.generation !== token) return;
      highlight();
      view.style.opacity = '1';
      live.Reveal.on('slidechanged', event => {
        services.onSlideChanged(event.indexh, event.indexv || 0);
      });
      live.document.addEventListener('click', event => {
        const block = event.target.closest('.sl-block');
        if (!block) return; // controls, links and fragments keep working
        event.preventDefault();
        event.stopPropagation();
        const section = block.closest('section');
        services.selectBlock([...section.querySelectorAll('.sl-block')].indexOf(block));
      }, true);
      // Clipboard shortcuts pressed while the iframe has focus.
      services.attachClipboard?.(live.document, live);
      services.onPreviewReady?.();
    };
    if (!live || !live.Reveal) {
      clearTimeout(failsafe);
      view.style.opacity = '1';
      return services.message('This deck’s reveal.js did not load. Check that lib/ sits next to index.html, then click Reload.', true);
    }
    if (live.Reveal.isReady()) attach();
    else live.Reveal.on('ready', attach);
  };
  view.srcdoc = previewHTML();
}

export function highlight() {
  const view = frame();
  const win = view.contentWindow;
  win.document.querySelectorAll('.studio-selected').forEach(node => node.classList.remove('studio-selected'));
  const section = win.Reveal?.getCurrentSlide();
  section?.querySelectorAll('.sl-block')[state.blockIndex]?.classList.add('studio-selected');
}

export function liveDocument() {
  try { return frame().contentWindow?.document || null; } catch (_) { return null; }
}

export function liveBlock() {
  const doc = liveDocument();
  const section = frame().contentWindow?.Reveal?.getCurrentSlide();
  if (!doc || !section) return null;
  return section.querySelectorAll('.sl-block')[state.blockIndex] || null;
}

export function canvasSize() {
  const config = frame().contentWindow?.Reveal?.getConfig?.();
  if (!config?.width) return null;
  return {width: config.width, height: config.height};
}
