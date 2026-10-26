// Capturing and replaying an element's visual appearance.
//
// A pasted element must look the same in its new deck even when that deck uses
// a different theme. We therefore read a small allowlist of computed styles
// from the live rendered element and write them back as inline styles. Layout
// coordinates stay separate (they live on the .sl-block itself).
//
// The source deck's stylesheet is deliberately NOT copied: that would restyle
// every other slide in the destination.

const PROPS = [
  'font-family', 'font-size', 'font-weight', 'font-style', 'font-variant',
  'line-height', 'letter-spacing', 'word-spacing', 'text-align', 'text-transform',
  'text-decoration-line', 'text-decoration-color', 'white-space', 'vertical-align',
  'color', 'background-color', 'background-image', 'background-size',
  'background-repeat', 'background-position', 'opacity',
  'border-top-width', 'border-right-width', 'border-bottom-width', 'border-left-width',
  'border-top-style', 'border-right-style', 'border-bottom-style', 'border-left-style',
  'border-top-color', 'border-right-color', 'border-bottom-color', 'border-left-color',
  'border-radius', 'box-shadow',
  'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
  'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
  'fill', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-opacity',
  'z-index', 'overflow', 'list-style-type',
];

const GENERIC_FAMILIES = new Set([
  'serif', 'sans-serif', 'monospace', 'cursive', 'fantasy', 'system-ui',
  'ui-serif', 'ui-sans-serif', 'ui-monospace', 'math', 'emoji', 'fangsong',
]);

const MAX_NODES = 200;
const GENERATED = '.math-output, .katex, .katex-html, mjx-container';

const pathTo = (node, root) => {
  const chain = [];
  let walk = node;
  while (walk && walk !== root) {
    const parent = walk.parentElement;
    if (!parent) return null;
    chain.unshift([...parent.children].indexOf(walk));
    walk = parent;
  }
  return walk === root ? chain : null;
};

export function captureAppearance(root) {
  if (!root) return {version: 1, rules: []};
  const win = root.ownerDocument.defaultView;
  const rules = [];
  const visit = (node, path) => {
    if (node.nodeType !== 1 || rules.length >= MAX_NODES) return;
    if (node.matches(GENERATED) || node.closest(GENERATED)) return;
    const computed = win.getComputedStyle(node);
    const props = {};
    for (const name of PROPS) {
      const value = computed.getPropertyValue(name);
      if (value) props[name] = value;
    }
    rules.push({path, props});
    [...node.children].forEach((child, index) => visit(child, [...path, index]));
  };
  visit(root, []);
  return {version: 1, rules};
}

export function applyAppearance(root, appearance) {
  if (!appearance || appearance.version !== 1) return;
  for (const rule of appearance.rules || []) {
    let node = root;
    for (const index of rule.path || []) {
      node = node?.children?.[index];
      if (!node) break;
    }
    if (!node) continue;
    for (const [name, value] of Object.entries(rule.props || {})) {
      try { node.style.setProperty(name, value); } catch (_) { /* ignore an invalid captured value */ }
    }
  }
}

export const scalePx = (value, factor) =>
  String(value).replace(/(-?\d*\.?\d+)px/g, (_, number) => `${(Number(number) * factor).toFixed(2)}px`);

const PX_PROPS = new Set([
  'font-size', 'letter-spacing', 'word-spacing', 'line-height', 'border-radius',
  'border-top-width', 'border-right-width', 'border-bottom-width', 'border-left-width',
  'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
  'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
  'stroke-width',
]);

export function scaleAppearance(appearance, factor) {
  if (!appearance || factor === 1) return appearance;
  const rules = (appearance.rules || []).map(rule => ({
    path: rule.path,
    props: Object.fromEntries(Object.entries(rule.props || {}).map(([name, value]) =>
      [name, PX_PROPS.has(name) ? scalePx(value, factor) : value])),
  }));
  return {...appearance, rules};
}

export function usedFamilies(appearance) {
  const families = new Set();
  for (const rule of appearance.rules || []) {
    const value = rule.props?.['font-family'];
    if (!value) continue;
    for (const part of value.split(',')) {
      const name = part.trim().replace(/^["']|["']$/g, '');
      if (name && !GENERIC_FAMILIES.has(name.toLowerCase())) families.add(name);
    }
  }
  return [...families];
}

function fontRef(css, sheetHref, deckBase) {
  const match = /url\(\s*["']?([^"')]+)["']?\s*\)/i.exec(css || '');
  if (!match || /^data:/i.test(match[1])) return null;
  try {
    const url = new URL(match[1], sheetHref);
    if (url.origin !== new URL(deckBase).origin) return null;
    if (!url.href.startsWith(deckBase)) return null;
    return decodeURIComponent(url.href.slice(deckBase.length).split('#')[0].split('?')[0]);
  } catch (_) {
    return null;
  }
}

function collectSheets(sheet, depth, into) {
  if (!sheet || depth > 4) return;
  into.push(sheet);
  let rules;
  try { rules = sheet.cssRules; } catch (_) { return; }
  for (const rule of rules) if (rule.styleSheet) collectSheets(rule.styleSheet, depth + 1, into);
}

export function captureFonts(doc, families, deckBase) {
  if (!families.length) return [];
  const wanted = new Set(families);
  const faces = [];
  const sheets = [];
  for (const sheet of doc.styleSheets) collectSheets(sheet, 0, sheets);
  for (const sheet of sheets) {
    let rules;
    try { rules = sheet.cssRules; } catch (_) { continue; }
    if (!rules) continue;
    for (const rule of rules) {
      const isFace = rule.constructor?.name === 'CSSFontFaceRule' || rule.type === 5;
      if (!isFace || !rule.style) continue;
      const family = (rule.style.getPropertyValue('font-family') || '').trim().replace(/^["']|["']$/g, '');
      if (!wanted.has(family)) continue;
      const ref = fontRef(rule.style.getPropertyValue('src'), sheet.href || deckBase, deckBase);
      if (!ref) continue;
      faces.push({
        family,
        weight: rule.style.getPropertyValue('font-weight') || 'normal',
        style: rule.style.getPropertyValue('font-style') || 'normal',
        unicodeRange: rule.style.getPropertyValue('unicode-range') || '',
        ref,
      });
    }
  }
  return faces;
}

export function rewriteFamilies(value, rename) {
  return value.split(',').map(part => {
    const name = part.trim().replace(/^["']|["']$/g, '');
    return rename.has(name) ? `"${rename.get(name)}"` : part;
  }).join(',');
}

const hash8 = text => {
  let hash = 2166136261;
  for (const char of text) {
    hash ^= char.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
};

export function applyFonts(root, fonts, materialized) {
  const usable = [];
  const rename = new Map();
  for (const face of fonts || []) {
    const destination = materialized?.[face.ref];
    if (!destination) continue;
    const unique = `SlideHouse ${hash8(face.ref + '|' + face.family)}`;
    usable.push({...face, unique, destination});
    if (!rename.has(face.family)) rename.set(face.family, unique);
  }
  if (!usable.length) return rename;

  for (const element of [root, ...root.querySelectorAll('*')]) {
    if (element.style?.fontFamily) element.style.fontFamily = rewriteFamilies(element.style.fontFamily, rename);
  }

  const css = usable.map(face => '@font-face{font-family:"' + face.unique + '";src:url("' + face.destination + '");'
    + 'font-weight:' + (face.weight || 'normal') + ';font-style:' + (face.style || 'normal') + ';'
    + (face.unicodeRange ? 'unicode-range:' + face.unicodeRange + ';' : '') + '}').join('\n');
  const style = root.ownerDocument.createElement('style');
  style.dataset.slidehouseFont = '1';
  style.textContent = css;
  // Append, never prepend: appearance rules are addressed by child index.
  root.append(style);
  return rename;
}

export function renameAppearanceFamilies(appearance, rename) {
  if (!rename.size) return appearance;
  const rules = (appearance.rules || []).map(rule => ({
    path: rule.path,
    props: Object.fromEntries(Object.entries(rule.props || {}).map(([name, value]) =>
      [name, name === 'font-family' ? rewriteFamilies(value, rename) : value])),
  }));
  return {...appearance, rules};
}
