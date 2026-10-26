// Undo / redo over whole-document snapshots.

import {state, parser, serialize, services} from './state.js';

let history = [];
let future = [];

const snapshot = () => ({html: serialize(), selected: state.selected, blockIndex: state.blockIndex});

export const canUndo = () => history.length > 0;
export const canRedo = () => future.length > 0;

export function resetHistory() {
  history = [];
  future = [];
}

export function mutate(action) {
  const before = snapshot();
  action();
  if (before.html === serialize()) return;
  state.docVersion++;
  history.push(before);
  if (history.length > 80) history.shift();
  future = [];
  services.render();
  services.message('Unsaved changes');
}

export function restore(from, to) {
  if (!from.length) return;
  to.push(snapshot());
  const step = from.pop();
  state.doc = parser.parseFromString(step.html, 'text/html');
  state.docVersion++;
  state.selected = step.selected;
  state.blockIndex = step.blockIndex;
  services.render();
  services.message('Unsaved changes');
}

export const undo = () => restore(history, future);
export const redo = () => restore(future, history);
