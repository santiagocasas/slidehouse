// Creating new editable elements.

import {state, blocks, current} from './state.js';

export function newBlock(type, imagePath = '') {
  const doc = state.doc;
  const block = doc.createElement('div');
  block.className = 'sl-block';
  block.dataset.blockType = type;
  block.dataset.blockId = crypto.randomUUID().replaceAll('-', '');
  block.style.cssText = 'left:80px;top:100px;width:600px;height:auto;';
  const content = doc.createElement('div');
  content.className = 'sl-block-content';
  content.style.zIndex = 30;
  block.append(content);
  if (type === 'text') content.innerHTML = '<p>Your text here</p>';
  if (type === 'math') {
    content.classList.add('notranslate');
    content.innerHTML = '<div class="math-input">E = mc^2</div>';
  }
  if (type === 'image') {
    block.style.height = '300px';
    const img = doc.createElement('img');
    img.dataset.src = imagePath;
    content.append(img);
  }
  current().node.append(block);
  state.blockIndex = blocks().indexOf(block);
  return block;
}
