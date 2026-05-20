(function () {
  const $ = (selector) => document.querySelector(selector);
  const state = {
    documents: [],
    record: null,
    document: null,
    selectedBlockId: null,
    selectedBlockIds: [],
    selectedText: '',
    messages: [],
    skills: [],
    pendingChanges: [],
  };

  const urlParams = new URLSearchParams(window.location.search);
  const canvasThreadId = urlParams.get('thread') || window.localStorage.getItem('lunlunCanvasThreadId') || '';
  if (urlParams.get('thread')) window.localStorage.setItem('lunlunCanvasThreadId', urlParams.get('thread'));

  const editor = $('#editor');
  const emptyState = $('#editor-empty');
  const documentList = $('#document-list');
  const preview = $('#preview');
  const toastNode = $('#toast');

  function clone(value) {
    if (typeof structuredClone === 'function') return structuredClone(value);
    return JSON.parse(JSON.stringify(value));
  }

  function uid(prefix = 'blk') {
    if (window.crypto?.randomUUID) {
      return `${prefix}_${window.crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`;
    }
    return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
  }

  function showToast(message) {
    toastNode.textContent = message;
    toastNode.classList.add('show');
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => toastNode.classList.remove('show'), 2600);
  }

  function requestHeaders(headers = {}) {
    const nextHeaders = new Headers(headers || {});
    if (canvasThreadId) nextHeaders.set('X-Lunlun-Thread-Id', canvasThreadId);
    return nextHeaders;
  }

  async function api(path, options = {}) {
    const headers = requestHeaders(options.headers || {});
    const response = await fetch(path, { ...options, headers });
    if (!response.ok) {
      let detail = response.statusText;
      try {
        const data = await response.json();
        detail = data.detail || detail;
      } catch (_ignored) {}
      throw new Error(detail);
    }
    return response.json();
  }

  function newBlock(type) {
    const base = { id: uid(), type };
    if (type === 'title') return { ...base, text: 'Untitled Paper' };
    if (type === 'heading') return { ...base, level: 1, text: 'New Heading' };
    if (type === 'ordered_list' || type === 'unordered_list') return { ...base, items: [{ text: 'List item' }] };
    if (type === 'blockquote') return { ...base, text: 'Quote' };
    if (type === 'code_block') return { ...base, language: '', code: '' };
    if (type === 'equation') return { ...base, latex: '' };
    if (type === 'citation') return { ...base, keys: [], text: '' };
    if (type === 'figure') return { ...base, src: '', caption: '', alt: '' };
    if (type === 'table') return { ...base, headers: [], rows: [['']], caption: '' };
    if (type === 'raw_latex') return { ...base, latex: '' };
    return { ...base, text: '' };
  }

  function currentBlocks() {
    return state.document?.blocks || [];
  }

  function selectedBlock() {
    return currentBlocks().find((block) => block.id === state.selectedBlockId) || null;
  }

  function selectedBlocks() {
    const selected = new Set(state.selectedBlockIds || []);
    return currentBlocks().filter((block) => selected.has(block.id));
  }

  function normalizeSelectedBlocks() {
    const existing = new Set(currentBlocks().map((block) => block.id));
    state.selectedBlockIds = (state.selectedBlockIds || []).filter((id) => existing.has(id));
    if (state.selectedBlockId && !existing.has(state.selectedBlockId)) {
      state.selectedBlockId = state.selectedBlockIds[0] || null;
    }
  }

  function pendingChangesForBlock(blockId) {
    return state.pendingChanges.filter((change) => change.block_id === blockId && (change.status || 'pending') === 'pending');
  }

  function setSelectedBlock(id, options = {}) {
    normalizeSelectedBlocks();
    if (!id) {
      state.selectedBlockId = null;
      state.selectedBlockIds = [];
    } else if (options.range && state.selectedBlockId) {
      const blocks = currentBlocks();
      const start = blocks.findIndex((block) => block.id === state.selectedBlockId);
      const end = blocks.findIndex((block) => block.id === id);
      if (start >= 0 && end >= 0) {
        const [from, to] = start < end ? [start, end] : [end, start];
        const merged = new Set(state.selectedBlockIds);
        blocks.slice(from, to + 1).forEach((block) => merged.add(block.id));
        state.selectedBlockIds = [...merged];
      } else {
        state.selectedBlockIds = [id];
      }
      state.selectedBlockId = id;
    } else if (options.toggle) {
      const selected = new Set(state.selectedBlockIds);
      if (selected.has(id)) selected.delete(id);
      else selected.add(id);
      state.selectedBlockIds = [...selected];
      state.selectedBlockId = selected.has(id) ? id : (state.selectedBlockIds[state.selectedBlockIds.length - 1] || null);
    } else {
      state.selectedBlockId = id;
      state.selectedBlockIds = [id];
    }

    editor.querySelectorAll('.canvas-block').forEach((node) => {
      const blockId = node.dataset.blockId;
      node.classList.toggle('selected', state.selectedBlockIds.includes(blockId));
      node.classList.toggle('active-block', blockId === state.selectedBlockId);
      const checkbox = node.querySelector('.block-select-checkbox');
      if (checkbox) checkbox.checked = state.selectedBlockIds.includes(blockId);
    });
    const blocks = selectedBlocks();
    const block = selectedBlock();
    const chip = $('#selected-block-chip');
    if (blocks.length > 1) chip.textContent = `已选 ${blocks.length} 个 block`;
    else chip.textContent = block ? `${block.type} · ${block.id}` : '未选中';
    updateSelectionPreview();
    renderContextPanel();
  }

  function blockPlainText(block) {
    if (!block) return '';
    if (['title', 'heading', 'paragraph', 'blockquote'].includes(block.type)) return block.text || '';
    if (['ordered_list', 'unordered_list'].includes(block.type)) return (block.items || []).map((item) => item.text || '').join('\n');
    if (block.type === 'code_block') return block.code || '';
    if (block.type === 'equation') return block.latex || '';
    if (block.type === 'citation') return block.text || (block.keys || []).join(', ');
    if (block.type === 'figure') return block.caption || block.alt || block.src || '';
    if (block.type === 'table') return tableToText(block);
    if (block.type === 'raw_latex') return block.latex || '';
    return '';
  }

  function updateSelectionPreview() {
    const blocks = selectedBlocks();
    const text = state.selectedText || (blocks.length ? blocks.map(blockPlainText).filter(Boolean).join('\n\n') : blockPlainText(selectedBlock()));
    $('#selection-preview').textContent = text || '选中文本，或点击一个或多个 block 作为当前上下文。';
  }

  function renderContextPanel() {
    const summary = $('#context-summary');
    const list = $('#context-list');
    if (!summary || !list) return;
    const blocks = selectedBlocks();
    const block = selectedBlock();
    const selectionLength = state.selectedText ? state.selectedText.length : 0;
    const title = state.document?.title || state.record?.title || '未打开文档';
    const contextCount = blocks.length || (block ? 1 : 0);
    summary.textContent = `${title} · ${contextCount || 0} 个 block${selectionLength ? ` · 选区 ${selectionLength} 字` : ''}`;
    list.innerHTML = '';
    const visibleBlocks = blocks.length ? blocks : (block ? [block] : []);
    if (!visibleBlocks.length && !state.selectedText) {
      list.innerHTML = '<div class="context-empty">未选择上下文。点击 block、勾选多个 block，或拖选文本。</div>';
      return;
    }
    visibleBlocks.slice(0, 8).forEach((item) => {
      const row = document.createElement('div');
      row.className = 'context-row';
      const text = blockPlainText(item).replace(/\s+/g, ' ').trim();
      row.innerHTML = `<strong>${escapeHtml(item.type || 'block')}</strong><span>${escapeHtml(text.slice(0, 120) || item.id)}</span>`;
      list.appendChild(row);
    });
    if (visibleBlocks.length > 8) {
      const more = document.createElement('div');
      more.className = 'context-empty';
      more.textContent = `还有 ${visibleBlocks.length - 8} 个 block 会一并提交给 Agent。`;
      list.appendChild(more);
    }
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function inlineMarkup(value) {
    let html = escapeHtml(value);
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/`(.+?)`/g, '<code>$1</code>');
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
    return html;
  }

  function parseSseEvent(rawEvent) {
    if (!rawEvent.trim()) return null;
    let event = 'message';
    const dataLines = [];
    rawEvent.split('\n').forEach((line) => {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
    });
    const dataText = dataLines.join('\n');
    let data = {};
    if (dataText) {
      try {
        data = JSON.parse(dataText);
      } catch (_ignored) {
        data = { raw: dataText };
      }
    }
    return { event, data };
  }

  async function readSseStream(response, handlers = {}) {
    if (!response.body) throw new Error('当前浏览器不支持流式响应。');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    const flush = () => {
      buffer = buffer.replace(/\r\n/g, '\n');
      let boundary = buffer.indexOf('\n\n');
      while (boundary >= 0) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const parsed = parseSseEvent(rawEvent);
        if (parsed && handlers[parsed.event]) handlers[parsed.event](parsed.data);
        boundary = buffer.indexOf('\n\n');
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      flush();
    }
    buffer += decoder.decode();
    if (buffer.trim()) {
      buffer += '\n\n';
      flush();
    }
  }

  function makeMeta(block) {
    const meta = document.createElement('div');
    meta.className = 'block-meta';
    const left = document.createElement('div');
    left.className = 'block-meta-left';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'block-select-checkbox';
    checkbox.checked = (state.selectedBlockIds || []).includes(block.id);
    checkbox.addEventListener('click', (event) => {
      event.stopPropagation();
      state.selectedText = '';
      setSelectedBlock(block.id, { toggle: true });
    });
    left.addEventListener('click', (event) => {
      event.stopPropagation();
      if (event.target === checkbox) return;
      state.selectedText = '';
      setSelectedBlock(block.id, { toggle: true });
    });
    const label = document.createElement('span');
    label.textContent = `${block.type} · ${block.id}`;
    left.appendChild(checkbox);
    left.appendChild(label);
    meta.appendChild(left);
    if (block.type === 'heading') {
      const level = document.createElement('select');
      [1, 2, 3].forEach((value) => {
        const option = document.createElement('option');
        option.value = String(value);
        option.textContent = `H${value}`;
        option.selected = Number(block.level || 1) === value;
        level.appendChild(option);
      });
      level.addEventListener('change', () => {
        block.level = Number(level.value);
        renderPreview();
      });
      meta.appendChild(level);
    }
    return meta;
  }

  function textEditable(block, prop, className = '') {
    const node = document.createElement('div');
    node.className = `text-edit ${className}`.trim();
    node.contentEditable = 'true';
    node.spellcheck = true;
    node.textContent = block[prop] || '';
    node.addEventListener('input', () => {
      block[prop] = node.textContent;
      if (block.type === 'title') state.document.title = node.textContent.trim() || state.document.title;
      renderPreview();
      updateExportLinks();
    });
    node.addEventListener('mouseup', captureSelection);
    node.addEventListener('keyup', captureSelection);
    node.addEventListener('focus', () => setSelectedBlock(block.id));
    return node;
  }

  function textarea(block, prop, className = '', rows = 5) {
    const node = document.createElement('textarea');
    node.className = className;
    node.rows = rows;
    node.value = block[prop] || '';
    node.addEventListener('input', () => {
      block[prop] = node.value;
      renderPreview();
    });
    node.addEventListener('mouseup', captureSelection);
    node.addEventListener('keyup', captureSelection);
    node.addEventListener('focus', () => setSelectedBlock(block.id));
    return node;
  }

  function input(block, prop, placeholder = '') {
    const node = document.createElement('input');
    node.type = 'text';
    node.placeholder = placeholder;
    node.value = block[prop] || '';
    node.addEventListener('input', () => {
      block[prop] = node.value;
      renderPreview();
      updateExportLinks();
    });
    node.addEventListener('focus', () => setSelectedBlock(block.id));
    return node;
  }

  function renderBlock(block) {
    const wrapper = document.createElement('section');
    const pending = pendingChangesForBlock(block.id);
    wrapper.className = `canvas-block ${pending.length ? 'has-pending-change' : ''}`;
    wrapper.dataset.blockId = block.id;
    wrapper.appendChild(makeMeta(block));
    wrapper.addEventListener('click', (event) => {
      if (event.target.closest('input, textarea, select, button, a')) return;
      state.selectedText = '';
      setSelectedBlock(block.id, {
        toggle: event.metaKey || event.ctrlKey,
        range: event.shiftKey,
      });
    });

    if (block.type === 'title') wrapper.appendChild(textEditable(block, 'text', 'title-edit'));
    else if (block.type === 'heading') wrapper.appendChild(textEditable(block, 'text', 'heading-edit'));
    else if (block.type === 'paragraph' || block.type === 'blockquote') wrapper.appendChild(textEditable(block, 'text'));
    else if (block.type === 'ordered_list' || block.type === 'unordered_list') {
      const node = document.createElement('textarea');
      node.rows = Math.max(3, (block.items || []).length + 1);
      node.value = (block.items || []).map((item) => item.text || '').join('\n');
      node.addEventListener('input', () => {
        block.items = node.value.split('\n').map((line) => ({ text: line })).filter((item) => item.text.trim());
        renderPreview();
      });
      node.addEventListener('mouseup', captureSelection);
      node.addEventListener('keyup', captureSelection);
      node.addEventListener('focus', () => setSelectedBlock(block.id));
      wrapper.appendChild(node);
    } else if (block.type === 'code_block') {
      wrapper.appendChild(input(block, 'language', 'language'));
      wrapper.appendChild(textarea(block, 'code', 'code-editor', 8));
    } else if (block.type === 'equation') {
      wrapper.appendChild(textarea(block, 'latex', 'latex-editor', 5));
    } else if (block.type === 'citation') {
      const fields = document.createElement('div');
      fields.className = 'citation-fields';
      const keys = document.createElement('input');
      keys.type = 'text';
      keys.placeholder = 'citation keys, comma separated';
      keys.value = (block.keys || []).join(', ');
      keys.addEventListener('input', () => {
        block.keys = keys.value.split(',').map((item) => item.trim()).filter(Boolean);
        renderPreview();
      });
      keys.addEventListener('focus', () => setSelectedBlock(block.id));
      fields.appendChild(keys);
      fields.appendChild(textarea(block, 'text', '', 3));
      wrapper.appendChild(fields);
    } else if (block.type === 'figure') {
      const fields = document.createElement('div');
      fields.className = 'figure-fields';
      fields.appendChild(input(block, 'src', 'image URL or asset placeholder'));
      if (block.src || block.asset_id) {
        const image = document.createElement('img');
        image.className = 'figure-preview';
        image.alt = block.alt || block.caption || 'figure';
        image.src = block.src || `/api/canvas/assets/${block.asset_id}`;
        fields.appendChild(image);
      }
      fields.appendChild(textarea(block, 'caption', '', 3));
      fields.appendChild(input(block, 'alt', 'alt text'));
      wrapper.appendChild(fields);
    } else if (block.type === 'table') {
      const node = document.createElement('textarea');
      node.rows = Math.max(4, (block.rows || []).length + 2);
      node.value = tableToText(block);
      node.addEventListener('input', () => {
        const parsed = textToTable(node.value);
        block.headers = parsed.headers;
        block.rows = parsed.rows;
        renderPreview();
      });
      node.addEventListener('mouseup', captureSelection);
      node.addEventListener('keyup', captureSelection);
      node.addEventListener('focus', () => setSelectedBlock(block.id));
      wrapper.appendChild(node);
      wrapper.appendChild(textarea(block, 'caption', '', 2));
    } else if (block.type === 'raw_latex') {
      wrapper.appendChild(textarea(block, 'latex', 'latex-editor', 7));
    }

    if (pending.length) wrapper.appendChild(renderBlockDiff(block, pending));
    if ((state.selectedBlockIds || []).includes(block.id)) wrapper.classList.add('selected');
    if (block.id === state.selectedBlockId) wrapper.classList.add('active-block');
    return wrapper;
  }

  function renderBlockDiff(block, changes) {
    const panel = document.createElement('div');
    panel.className = 'block-diff-panel';
    const title = document.createElement('div');
    title.className = 'diff-title';
    title.textContent = `Agent 修改建议 · ${changes.length}`;
    panel.appendChild(title);
    changes.forEach((change) => panel.appendChild(renderChangeCard(change, { compact: true })));
    return panel;
  }

  function tableToText(block) {
    const rows = [];
    if ((block.headers || []).length) rows.push(block.headers);
    rows.push(...(block.rows || []));
    return rows.map((row) => row.join(' | ')).join('\n');
  }

  function textToTable(value) {
    const lines = value.split('\n').map((line) => line.trim()).filter(Boolean);
    const rows = lines.map((line) => line.split('|').map((cell) => cell.trim()));
    return { headers: [], rows };
  }

  function renderEditor() {
    editor.innerHTML = '';
    const hasDocument = Boolean(state.document);
    emptyState.style.display = hasDocument ? 'none' : 'block';
    editor.style.display = hasDocument ? 'block' : 'none';
    if (!hasDocument) {
      preview.innerHTML = '';
      updateExportLinks();
      updatePendingChangesBar();
      renderContextPanel();
      return;
    }
    currentBlocks().forEach((block) => editor.appendChild(renderBlock(block)));
    renderPreview();
    updateExportLinks();
    updatePendingChangesBar();
    renderContextPanel();
  }

  function renderPreview() {
    if (!state.document) {
      preview.innerHTML = '';
      return;
    }
    const htmlParts = currentBlocks().map((block) => {
      if (block.type === 'title') return `<h1>${inlineMarkup(block.text || '')}</h1>`;
      if (block.type === 'heading') {
        const level = Math.min(Number(block.level || 1) + 1, 4);
        return `<h${level}>${inlineMarkup(block.text || '')}</h${level}>`;
      }
      if (block.type === 'paragraph') return `<p>${inlineMarkup(block.text || '')}</p>`;
      if (block.type === 'blockquote') return `<blockquote>${inlineMarkup(block.text || '')}</blockquote>`;
      if (block.type === 'ordered_list' || block.type === 'unordered_list') {
        const tag = block.type === 'ordered_list' ? 'ol' : 'ul';
        const items = (block.items || []).map((item) => `<li>${inlineMarkup(item.text || '')}</li>`).join('');
        return `<${tag}>${items}</${tag}>`;
      }
      if (block.type === 'code_block') return `<pre><code>${escapeHtml(block.code || '')}</code></pre>`;
      if (block.type === 'equation') return `<div>$$${escapeHtml(block.latex || '')}$$</div>`;
      if (block.type === 'citation') return `<p class="citation-token">${inlineMarkup(block.text || (block.keys || []).join(', '))}</p>`;
      if (block.type === 'figure') {
        const src = block.src || (block.asset_id ? `/api/canvas/assets/${block.asset_id}` : '');
        return `<figure>${src ? `<img src="${escapeHtml(src)}" alt="${escapeHtml(block.alt || '')}" />` : ''}<figcaption>${inlineMarkup(block.caption || '')}</figcaption></figure>`;
      }
      if (block.type === 'table') return renderTablePreview(block);
      if (block.type === 'raw_latex') return `<pre class="raw-latex-preview">${escapeHtml(block.latex || '')}</pre>`;
      return '';
    });
    preview.innerHTML = htmlParts.join('\n');
    if (window.MathJax?.typesetPromise) window.MathJax.typesetPromise([preview]).catch(() => {});
  }

  function renderTablePreview(block) {
    const headers = block.headers || [];
    const rows = block.rows || [];
    const thead = headers.length ? `<thead><tr>${headers.map((cell) => `<th>${inlineMarkup(cell)}</th>`).join('')}</tr></thead>` : '';
    const tbody = `<tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${inlineMarkup(cell)}</td>`).join('')}</tr>`).join('')}</tbody>`;
    const caption = block.caption ? `<caption>${inlineMarkup(block.caption)}</caption>` : '';
    return `<table>${caption}${thead}${tbody}</table>`;
  }

  async function loadSkills() {
    const data = await api('/api/canvas/skills');
    state.skills = data.skills || [];
  }

  async function loadDocuments(preferredId = null) {
    await refreshDocuments();
    const queryDoc = new URLSearchParams(window.location.search).get('doc');
    const id = preferredId || queryDoc || state.record?.id;
    if (id) await openDocument(id).catch(() => {});
  }

  async function refreshDocuments() {
    const data = await api('/api/canvas/documents');
    state.documents = data.documents || [];
    renderDocumentList();
  }

  function renderDocumentList() {
    documentList.innerHTML = '';
    if (!state.documents.length) {
      documentList.innerHTML = '<div class="empty-state">还没有 Canvas 文档。</div>';
      return;
    }
    state.documents.forEach((doc) => {
      const row = document.createElement('button');
      row.type = 'button';
      row.className = `document-row ${state.record?.id === doc.id ? 'active' : ''}`;
      row.innerHTML = `<div class="document-row-title">${escapeHtml(doc.title)}</div><div class="document-row-meta">${escapeHtml(doc.source_type || 'manual')} · v${doc.version_number || 1} · ${doc.block_count || 0} blocks</div>`;
      row.addEventListener('click', () => openDocument(doc.id));
      documentList.appendChild(row);
    });
  }

  async function openDocument(id) {
    const record = await api(`/api/canvas/documents/${id}`);
    state.record = record;
    state.document = record.document;
    state.selectedBlockId = state.document.blocks?.[0]?.id || null;
    state.selectedBlockIds = state.selectedBlockId ? [state.selectedBlockId] : [];
    state.selectedText = '';
    state.pendingChanges = [];
    renderDocumentList();
    await loadCanvasChat();
    renderEditor();
    setSelectedBlock(state.selectedBlockId);
    await loadVersions();
    const params = new URLSearchParams({ doc: id });
    if (canvasThreadId) params.set('thread', canvasThreadId);
    history.replaceState(null, '', `/canvas?${params.toString()}`);
  }

  async function createDocument() {
    const title = window.prompt('文档标题', 'Untitled Paper') || 'Untitled Paper';
    const record = await api('/api/canvas/documents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    showToast('文档已创建');
    await loadDocuments(record.id);
  }

  async function saveDocument(source = 'manual_save', extra = {}) {
    if (!state.record || !state.document) return;
    const record = await api(`/api/canvas/documents/${state.record.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document: state.document, source, ...extra }),
    });
    state.record = record;
    state.document = record.document;
    normalizeSelectedBlocks();
    renderEditor();
    await refreshDocuments();
    await loadVersions();
    showToast('已保存');
  }

  async function deleteDocument() {
    if (!state.record) {
      showToast('请先选择要删除的文档');
      return;
    }
    const title = state.record.title || state.document?.title || '当前文档';
    if (!window.confirm(`确认删除「${title}」？`)) return;
    await api(`/api/canvas/documents/${state.record.id}`, { method: 'DELETE' });
    state.record = null;
    state.document = null;
    state.selectedBlockId = null;
    state.selectedBlockIds = [];
    state.selectedText = '';
    state.messages = [];
    state.pendingChanges = [];
    hideUtilityPanel();
    renderEditor();
    renderAgentMessages();
    updateExportLinks();
    await refreshDocuments();
    if (state.documents[0]) await openDocument(state.documents[0].id);
    else renderDocumentList();
    showToast('文档已删除');
  }

  async function importDocument(file) {
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    const record = await api('/api/canvas/import', { method: 'POST', body: form });
    showToast('导入完成');
    await loadDocuments(record.id);
    $('#import-file').value = '';
  }

  async function loadVersions() {
    const list = $('#version-list');
    list.innerHTML = '';
    if (!state.record) return;
    const data = await api(`/api/canvas/documents/${state.record.id}/versions`);
    (data.versions || []).forEach((version) => {
      const row = document.createElement('div');
      row.className = 'version-row';
      row.innerHTML = `<div>v${version.version_number} · ${escapeHtml(version.source || '')}</div><small>${escapeHtml(version.created_at || '')}</small>`;
      const restore = document.createElement('button');
      restore.type = 'button';
      restore.textContent = '恢复';
      restore.addEventListener('click', async () => {
        const record = await api(`/api/canvas/documents/${state.record.id}/versions/${version.id}/restore`, { method: 'POST' });
        showToast(`已恢复 v${version.version_number}`);
        await loadDocuments(record.id);
      });
      row.appendChild(restore);
      list.appendChild(row);
    });
  }

  function openUtilityPanel(mode) {
    const panel = $('#utility-panel');
    const version = $('#version-utility');
    const previewPanel = $('#preview-utility');
    const title = $('#utility-title');
    panel.classList.remove('hidden');
    version.classList.toggle('hidden', mode !== 'versions');
    previewPanel.classList.toggle('hidden', mode !== 'preview');
    title.textContent = mode === 'preview' ? '快速预览' : '版本';
    if (mode === 'versions') loadVersions().catch((error) => showToast(error.message));
    if (mode === 'preview') renderPreview();
  }

  function hideUtilityPanel() {
    $('#utility-panel')?.classList.add('hidden');
  }

  function updateExportLinks() {
    const tex = $('#export-tex');
    const docx = $('#export-docx');
    if (!state.record) {
      tex.classList.add('disabled');
      docx.classList.add('disabled');
      tex.href = '#';
      docx.href = '#';
      return;
    }
    tex.classList.remove('disabled');
    docx.classList.remove('disabled');
    tex.href = `/api/canvas/documents/${state.record.id}/export/tex`;
    docx.href = `/api/canvas/documents/${state.record.id}/export/docx`;
  }

  async function loadCanvasChat() {
    if (!state.record) return;
    const data = await api(`/api/canvas/documents/${state.record.id}/chat`);
    state.skills = data.skills || state.skills || [];
    hydrateMessages(data.messages || []);
    renderAgentMessages();
  }

  function hydrateMessages(messages) {
    state.messages = messages || [];
    const pending = [];
    state.messages.forEach((message) => {
      const response = message.response || {};
      const changes = Array.isArray(response.changes) ? response.changes : [];
      changes.forEach((change, index) => {
        change.id = change.id || `chg_${index + 1}`;
        change.message_id = message.id;
        change.key = `${message.id}:${change.id}`;
        change.status = change.status || 'pending';
        if (change.status === 'pending') pending.push(change);
      });
    });
    state.pendingChanges = pending;
    updatePendingChangesBar();
  }

  function renderThinkingPanel(thinkingText = '', options = {}) {
    const panel = document.createElement('details');
    panel.className = 'thinking-panel';
    if (options.open) panel.open = true;
    const summary = document.createElement('summary');
    summary.textContent = thinkingText ? '思考过程' : '思考过程 · 等待模型输出';
    const content = document.createElement('pre');
    content.className = 'thinking-content';
    content.textContent = thinkingText || '正在等待模型输出思考过程...';
    panel.appendChild(summary);
    panel.appendChild(content);
    return panel;
  }

  function renderAgentMessageNode(message, options = {}) {
    const node = document.createElement('div');
    node.className = `agent-message ${message.role}`;
    if (options.streaming) node.classList.add('streaming');
    const role = document.createElement('div');
    role.className = 'message-role';
    role.textContent = message.role === 'user' ? '你' : '论论';
    node.appendChild(role);

    const thinkingText = message.response?.thinking_text || message.thinking_text || '';
    if (message.role === 'assistant' && (thinkingText || options.forceThinking)) {
      node.appendChild(renderThinkingPanel(thinkingText, { open: Boolean(options.thinkingOpen) }));
    }

    const content = document.createElement('div');
    content.className = 'message-content';
    if (options.pending && !message.content) content.textContent = '正在生成正文...';
    else content.innerHTML = inlineMarkup(message.content || '');
    node.appendChild(content);

    const changes = message.response?.changes || [];
    if (message.role === 'assistant' && changes.length) {
      const list = document.createElement('div');
      list.className = 'message-change-list';
      changes.forEach((change) => list.appendChild(renderChangeCard(change)));
      node.appendChild(list);
    }
    return node;
  }

  function appendStreamingAgentConversation(userContent) {
    const box = $('#agent-messages');
    if (box.querySelector('.empty-state')) box.innerHTML = '';
    const userNode = renderAgentMessageNode({ role: 'user', content: userContent });
    const assistantNode = renderAgentMessageNode(
      { role: 'assistant', content: '', response: {} },
      { forceThinking: true, thinkingOpen: true, pending: true, streaming: true },
    );
    box.appendChild(userNode);
    box.appendChild(assistantNode);
    box.scrollTop = box.scrollHeight;
    return {
      box,
      assistantNode,
      thinkingPanel: assistantNode.querySelector('.thinking-panel'),
      thinkingContent: assistantNode.querySelector('.thinking-content'),
      messageContent: assistantNode.querySelector('.message-content'),
    };
  }

  function renderAgentMessages() {
    const box = $('#agent-messages');
    box.innerHTML = '';
    if (!state.record) {
      box.innerHTML = '<div class="empty-state">打开一个文档后，可以在这里和 Canvas Agent 对话。</div>';
      return;
    }
    if (!state.messages.length) {
      box.innerHTML = '<div class="empty-state">选中文本，然后直接说“润色这段”或输入 / 选择 skill。</div>';
      return;
    }
    state.messages.forEach((message) => {
      box.appendChild(renderAgentMessageNode(message));
    });
    box.scrollTop = box.scrollHeight;
    updatePendingChangesBar();
  }

  function renderChangeCard(change, options = {}) {
    const card = document.createElement('div');
    card.className = `diff-card status-${change.status || 'pending'} ${options.compact ? 'compact' : ''}`;
    const header = document.createElement('div');
    header.className = 'diff-card-header';
    header.innerHTML = `<span>${escapeHtml(change.block_id || '')}</span><strong>${escapeHtml(statusLabel(change.status))}</strong>`;
    card.appendChild(header);
    const before = document.createElement('pre');
    before.className = 'diff-before';
    before.textContent = `- ${change.before || ''}`;
    const after = document.createElement('pre');
    after.className = 'diff-after';
    after.textContent = `+ ${change.after || ''}`;
    card.appendChild(before);
    card.appendChild(after);
    if (change.reason) {
      const reason = document.createElement('div');
      reason.className = 'diff-reason';
      reason.textContent = change.reason;
      card.appendChild(reason);
    }
    if ((change.status || 'pending') === 'pending') {
      const actions = document.createElement('div');
      actions.className = 'diff-actions';
      const accept = document.createElement('button');
      accept.type = 'button';
      accept.textContent = '接受';
      accept.addEventListener('click', () => acceptChange(change).catch((error) => showToast(error.message)));
      const reject = document.createElement('button');
      reject.type = 'button';
      reject.textContent = '拒绝';
      reject.addEventListener('click', () => rejectChange(change).catch((error) => showToast(error.message)));
      actions.appendChild(accept);
      actions.appendChild(reject);
      card.appendChild(actions);
    }
    return card;
  }

  function statusLabel(status) {
    if (status === 'accepted') return '已接受';
    if (status === 'rejected') return '已拒绝';
    return '待确认';
  }

  function updatePendingChangesBar() {
    const bar = $('#pending-changes-bar');
    const count = state.pendingChanges.filter((change) => (change.status || 'pending') === 'pending').length;
    $('#pending-changes-count').textContent = `${count} 条修改建议`;
    bar.classList.toggle('hidden', count === 0);
  }

  async function syncChangeStatus(change) {
    const message = state.messages.find((item) => item.id === change.message_id);
    if (!message) return;
    await api(`/api/canvas/documents/${state.record.id}/chat/messages/${message.id}/response`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ response: message.response || {} }),
    });
  }

  async function acceptChange(change) {
    if (!state.record || !state.document) return;
    const block = currentBlocks().find((item) => item.id === change.block_id);
    if (!block) throw new Error('找不到修改对应的 block。');
    const beforeBlock = clone(block);
    const beforeDocument = clone(state.document);
    const previousStatus = change.status || 'pending';
    change.status = 'accepted';
    applyReplacement(block, change.before || '', change.after || '');
    try {
      await saveDocument('agent_apply', {
        block_id: block.id,
        instruction: change.reason || 'Canvas Agent 修改',
        before_json: beforeBlock,
        after_json: clone(block),
        metadata: { change },
      });
    } catch (error) {
      change.status = previousStatus;
      state.document = beforeDocument;
      renderEditor();
      throw error;
    }
    await syncChangeStatus(change);
    hydrateMessages(state.messages);
    renderEditor();
    renderAgentMessages();
    showToast('已接受修改');
  }

  async function rejectChange(change) {
    const previousStatus = change.status || 'pending';
    change.status = 'rejected';
    try {
      await syncChangeStatus(change);
    } catch (error) {
      change.status = previousStatus;
      throw error;
    }
    hydrateMessages(state.messages);
    renderEditor();
    renderAgentMessages();
    showToast('已拒绝修改');
  }

  async function acceptAllChanges() {
    const changes = [...state.pendingChanges];
    for (const change of changes) {
      if ((change.status || 'pending') === 'pending') await acceptChange(change);
    }
  }

  async function rejectAllChanges() {
    const changes = [...state.pendingChanges];
    for (const change of changes) {
      if ((change.status || 'pending') === 'pending') await rejectChange(change);
    }
  }

  function applyReplacement(block, selectedText, replacement) {
    const prop = mainTextProp(block);
    if (!prop) return;
    if (block.type === 'ordered_list' || block.type === 'unordered_list') {
      const joined = (block.items || []).map((item) => item.text || '').join('\n');
      const next = selectedText && joined.includes(selectedText) ? joined.replace(selectedText, replacement) : replacement;
      block.items = next.split('\n').map((line) => ({ text: line })).filter((item) => item.text.trim());
      return;
    }
    const oldValue = block[prop] || '';
    block[prop] = selectedText && oldValue.includes(selectedText) ? oldValue.replace(selectedText, replacement) : replacement;
    if (block.type === 'title') state.document.title = block[prop];
  }

  function mainTextProp(block) {
    if (['title', 'heading', 'paragraph', 'blockquote'].includes(block.type)) return 'text';
    if (block.type === 'code_block') return 'code';
    if (block.type === 'equation') return 'latex';
    if (block.type === 'citation') return 'text';
    if (block.type === 'figure') return 'caption';
    if (block.type === 'raw_latex') return 'latex';
    if (block.type === 'ordered_list' || block.type === 'unordered_list') return 'items';
    return null;
  }

  function captureSelection() {
    const selection = window.getSelection();
    const text = selection ? selection.toString() : '';
    const anchor = selection?.anchorNode?.nodeType === Node.TEXT_NODE ? selection.anchorNode.parentElement : selection?.anchorNode;
    const blockNode = anchor?.closest?.('.canvas-block');
    if (!blockNode) return;
    setSelectedBlock(blockNode.dataset.blockId);
    state.selectedText = text.trim();
    updateSelectionPreview();
    renderContextPanel();
  }

  function wrapSelection(mark) {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return;
    const range = selection.getRangeAt(0);
    const container = range.commonAncestorContainer.nodeType === Node.TEXT_NODE ? range.commonAncestorContainer.parentElement : range.commonAncestorContainer;
    if (!container?.closest?.('#editor')) return;
    const selected = selection.toString();
    if (!selected) return;
    const replacement = mark === 'link'
      ? `[${selected}](https://)`
      : mark === 'bold'
        ? `**${selected}**`
        : mark === 'italic'
          ? `*${selected}*`
          : `\`${selected}\``;
    range.deleteContents();
    range.insertNode(document.createTextNode(replacement));
    const editable = container.closest('[contenteditable="true"]');
    if (editable) editable.dispatchEvent(new InputEvent('input', { bubbles: true }));
    captureSelection();
  }

  function addBlock() {
    if (!state.document) return;
    const block = newBlock($('#block-type').value);
    const blocks = currentBlocks();
    const index = blocks.findIndex((item) => item.id === state.selectedBlockId);
    blocks.splice(index >= 0 ? index + 1 : blocks.length, 0, block);
    state.selectedBlockId = block.id;
    renderEditor();
    setSelectedBlock(block.id);
  }

  function deleteBlock() {
    if (!state.document || !state.selectedBlockId) return;
    const ids = new Set(state.selectedBlockIds.length ? state.selectedBlockIds : [state.selectedBlockId]);
    const blocks = currentBlocks();
    if (ids.size >= blocks.length) {
      showToast('至少保留一个 block');
      return;
    }
    const firstIndex = blocks.findIndex((block) => ids.has(block.id));
    state.document.blocks = blocks.filter((block) => !ids.has(block.id));
    const nextIndex = Math.min(Math.max(firstIndex, 0), state.document.blocks.length - 1);
    state.selectedBlockId = state.document.blocks[nextIndex]?.id || null;
    state.selectedBlockIds = state.selectedBlockId ? [state.selectedBlockId] : [];
    state.selectedText = '';
    renderEditor();
    setSelectedBlock(state.selectedBlockId);
  }

  async function sendAgentMessage(event) {
    if (event) event.preventDefault();
    if (!state.record || !state.document) {
      showToast('请先打开一个 Canvas 文档');
      return;
    }
    const input = $('#agent-input');
    const message = input.value.trim();
    if (!message) return;
    const block = selectedBlock();
    const blocks = selectedBlocks();
    const selectedBlockIds = blocks.map((item) => item.id);
    const selectedText = state.selectedText || blocks.map(blockPlainText).filter(Boolean).join('\n\n');
    const live = appendStreamingAgentConversation(message);
    let finalReceived = false;
    $('#send-agent').disabled = true;
    showToast('Agent 正在处理');
    try {
      const response = await fetch(`/api/canvas/documents/${state.record.id}/chat/stream`, {
        method: 'POST',
        headers: requestHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          message,
          block_id: block?.id || selectedBlockIds[0] || null,
          selected_block_ids: selectedBlockIds,
          selected_text: selectedText,
        }),
      });
      if (!response.ok) {
        let detail = response.statusText;
        try {
          const data = await response.json();
          detail = data.detail || detail;
        } catch (_ignored) {}
        throw new Error(detail);
      }

      await readSseStream(response, {
        thinking(data) {
          const delta = String(data.delta || '');
          if (!delta && !data.replace) return;
          const placeholder = '正在等待模型输出思考过程...';
          const current = live.thinkingContent.textContent === placeholder ? '' : live.thinkingContent.textContent;
          live.thinkingContent.textContent = data.replace ? delta : current + delta;
          live.thinkingPanel.open = true;
          const summary = live.thinkingPanel.querySelector('summary');
          if (summary) summary.textContent = '思考过程';
          live.box.scrollTop = live.box.scrollHeight;
        },
        answer_progress() {
          if (live.messageContent.textContent === '正在生成正文...') {
            live.messageContent.textContent = '正在整理正文...';
          }
        },
        final(data) {
          finalReceived = true;
          if (live.thinkingPanel) live.thinkingPanel.open = false;
          hydrateMessages(data.messages || []);
          input.value = '';
          hideSkillSuggestions();
          renderEditor();
          renderAgentMessages();
          if ((data.changes || []).length) showToast('已生成修改建议');
        },
        error(data) {
          finalReceived = true;
          if (live.thinkingPanel) live.thinkingPanel.open = false;
          if (data.messages) {
            hydrateMessages(data.messages || []);
            renderAgentMessages();
          } else {
            live.messageContent.textContent = data.message || 'Canvas Agent 调用失败';
          }
          showToast(data.message || 'Canvas Agent 调用失败');
        },
      });
      if (!finalReceived) throw new Error('Canvas Agent 没有返回正文。');
    } catch (error) {
      if (live.thinkingPanel) live.thinkingPanel.open = false;
      live.messageContent.textContent = error.message;
      live.assistantNode.classList.remove('streaming');
      showToast(error.message);
    } finally {
      $('#send-agent').disabled = false;
    }
  }

  function showSkillSuggestions() {
    const input = $('#agent-input');
    const box = $('#skill-suggestions');
    const cursor = input.selectionStart || input.value.length;
    const beforeCursor = input.value.slice(0, cursor);
    const token = beforeCursor.split(/\s/).pop() || '';
    if (!token.startsWith('/')) {
      hideSkillSuggestions();
      return;
    }
    const query = token.slice(1).toLowerCase();
    const skills = state.skills.filter((skill) => skill.name.toLowerCase().includes(query)).slice(0, 8);
    if (!skills.length) {
      box.innerHTML = '<div class="skill-empty">没有匹配的 skill</div>';
      box.classList.remove('hidden');
      return;
    }
    box.innerHTML = '';
    skills.forEach((skill) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'skill-option';
      button.innerHTML = `<strong>/${escapeHtml(skill.name)}</strong><span>${escapeHtml(skill.description || '')}</span>`;
      button.addEventListener('click', () => {
        const value = input.value;
        const start = beforeCursor.lastIndexOf(token);
        input.value = `${value.slice(0, start)}/${skill.name} ${value.slice(cursor)}`;
        input.focus();
        input.selectionStart = input.selectionEnd = start + skill.name.length + 2;
        hideSkillSuggestions();
      });
      box.appendChild(button);
    });
    box.classList.remove('hidden');
  }

  function hideSkillSuggestions() {
    $('#skill-suggestions').classList.add('hidden');
  }

  function bindEvents() {
    $('#refresh-docs').addEventListener('click', () => loadDocuments().catch((error) => showToast(error.message)));
    $('#new-doc').addEventListener('click', () => createDocument().catch((error) => showToast(error.message)));
    $('#save-doc').addEventListener('click', () => saveDocument().catch((error) => showToast(error.message)));
    $('#delete-doc').addEventListener('click', () => deleteDocument().catch((error) => showToast(error.message)));
    $('#import-file').addEventListener('change', (event) => importDocument(event.target.files?.[0]).catch((error) => showToast(error.message)));
    $('#add-block').addEventListener('click', addBlock);
    $('#delete-block').addEventListener('click', deleteBlock);
    $('#refresh-preview').addEventListener('click', renderPreview);
    $('#open-versions').addEventListener('click', () => openUtilityPanel('versions'));
    $('#open-preview').addEventListener('click', () => openUtilityPanel('preview'));
    $('#close-utility').addEventListener('click', hideUtilityPanel);
    $('#agent-form').addEventListener('submit', sendAgentMessage);
    $('#agent-input').addEventListener('input', showSkillSuggestions);
    $('#agent-input').addEventListener('focus', showSkillSuggestions);
    $('#agent-input').addEventListener('keydown', (event) => {
      if (event.key === 'Escape') hideSkillSuggestions();
      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') sendAgentMessage(event);
    });
    $('#accept-all-changes').addEventListener('click', () => acceptAllChanges().catch((error) => showToast(error.message)));
    $('#reject-all-changes').addEventListener('click', () => rejectAllChanges().catch((error) => showToast(error.message)));
    $('#restore-prev').addEventListener('click', async () => {
      if (!state.record) return;
      try {
        const record = await api(`/api/canvas/documents/${state.record.id}/restore-previous`, { method: 'POST' });
        showToast('已恢复上一版');
        await loadDocuments(record.id);
      } catch (error) {
        showToast(error.message);
      }
    });
    document.querySelectorAll('[data-format]').forEach((button) => {
      button.addEventListener('click', () => wrapSelection(button.dataset.format));
    });
    document.addEventListener('selectionchange', () => {
      if (document.activeElement?.closest?.('#editor')) captureSelection();
    });
  }

  bindEvents();
  Promise.all([loadSkills(), loadDocuments()]).catch((error) => showToast(error.message));
})();
