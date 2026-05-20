from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = 1

BLOCK_TYPES = {
    'title',
    'heading',
    'paragraph',
    'ordered_list',
    'unordered_list',
    'blockquote',
    'code_block',
    'equation',
    'citation',
    'figure',
    'table',
    'raw_latex',
}

LEGACY_BLOCK_TYPES = {
    'bullet_list': 'unordered_list',
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace('+00:00', 'Z')


def new_id(prefix: str = 'blk') -> str:
    return f'{prefix}_{uuid.uuid4().hex[:12]}'


def new_block(block_type: str, **fields: Any) -> dict[str, Any]:
    normalized_type = LEGACY_BLOCK_TYPES.get(block_type, block_type)
    if normalized_type not in BLOCK_TYPES:
        raise ValueError(f'Unsupported Canvas block type: {block_type}')
    return {'id': new_id(), 'type': normalized_type, **fields}


def create_document(
    title: str = 'Untitled Paper',
    blocks: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = now_iso()
    doc_blocks = blocks or [new_block('title', text=title)]
    document = {
        'schema_version': SCHEMA_VERSION,
        'title': title or 'Untitled Paper',
        'metadata': {
            'created_at': now,
            'updated_at': now,
            **(metadata or {}),
        },
        'blocks': doc_blocks,
    }
    return normalize_document(document)


def normalize_document(document: dict[str, Any]) -> dict[str, Any]:
    title = str(document.get('title') or '').strip() or 'Untitled Paper'
    metadata = dict(document.get('metadata') or {})
    blocks = [
        normalize_block(block)
        for block in document.get('blocks') or []
        if isinstance(block, dict)
    ]
    if not blocks:
        blocks = [new_block('title', text=title)]
    if not any(block.get('type') == 'title' for block in blocks):
        blocks.insert(0, new_block('title', text=title))
    title_block = next((block for block in blocks if block.get('type') == 'title'), None)
    if title_block and title_block.get('text'):
        title = str(title_block['text']).strip() or title
    metadata.setdefault('created_at', now_iso())
    metadata['updated_at'] = now_iso()
    return {
        'schema_version': int(document.get('schema_version') or SCHEMA_VERSION),
        'title': title,
        'metadata': metadata,
        'blocks': blocks,
    }


def normalize_block(block: dict[str, Any]) -> dict[str, Any]:
    block_type = LEGACY_BLOCK_TYPES.get(str(block.get('type') or 'paragraph'), str(block.get('type') or 'paragraph'))
    if block_type not in BLOCK_TYPES:
        block_type = 'raw_latex'
    normalized = {'id': str(block.get('id') or new_id()), 'type': block_type}

    if block_type == 'title':
        normalized['text'] = str(block.get('text') or block.get('content') or '')
    elif block_type == 'heading':
        normalized['text'] = str(block.get('text') or '')
        normalized['level'] = int(block.get('level') or 1)
        if block.get('label'):
            normalized['label'] = str(block['label'])
    elif block_type in {'paragraph', 'blockquote'}:
        normalized['text'] = str(block.get('text') or '')
        citations = block.get('citations') or []
        refs = block.get('refs') or []
        normalized['citations'] = [str(item) for item in citations if str(item)]
        normalized['refs'] = [str(item) for item in refs if str(item)]
    elif block_type in {'ordered_list', 'unordered_list'}:
        raw_items = block.get('items') or []
        normalized['items'] = [
            {'text': str(item.get('text') or '')}
            if isinstance(item, dict)
            else {'text': str(item)}
            for item in raw_items
        ]
    elif block_type == 'code_block':
        normalized['language'] = str(block.get('language') or '')
        normalized['code'] = str(block.get('code') or block.get('text') or '')
    elif block_type == 'equation':
        normalized['latex'] = str(block.get('latex') or block.get('text') or '')
        normalized['numbered'] = bool(block.get('numbered', True))
        if block.get('label'):
            normalized['label'] = str(block['label'])
    elif block_type == 'citation':
        keys = block.get('keys') or []
        normalized['keys'] = [str(item) for item in keys if str(item)]
        normalized['text'] = str(block.get('text') or '')
    elif block_type == 'figure':
        normalized['caption'] = str(block.get('caption') or '')
        normalized['alt'] = str(block.get('alt') or '')
        normalized['src'] = str(block.get('src') or '')
        if block.get('asset_id'):
            normalized['asset_id'] = str(block['asset_id'])
        if block.get('label'):
            normalized['label'] = str(block['label'])
        if block.get('raw_latex'):
            normalized['raw_latex'] = str(block['raw_latex'])
    elif block_type == 'table':
        normalized['caption'] = str(block.get('caption') or '')
        normalized['headers'] = [str(item) for item in block.get('headers') or []]
        rows = block.get('rows') or []
        normalized['rows'] = [
            [str(cell) for cell in row]
            for row in rows
            if isinstance(row, list)
        ]
        if block.get('label'):
            normalized['label'] = str(block['label'])
        if block.get('raw_latex'):
            normalized['raw_latex'] = str(block['raw_latex'])
    elif block_type == 'raw_latex':
        normalized['latex'] = str(block.get('latex') or block.get('text') or '')
    return normalized


def markdown_to_canvas_document(content: str, title: str | None = None) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    pending_paragraph: list[str] = []
    document_title = title or ''

    def flush_paragraph() -> None:
        if pending_paragraph:
            text = '\n'.join(pending_paragraph).strip()
            if text:
                blocks.append(new_block('paragraph', text=text))
            pending_paragraph.clear()

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            continue
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if heading_match:
            flush_paragraph()
            heading_text = heading_match.group(2).strip()
            level = min(len(heading_match.group(1)), 4)
            if level == 1 and not document_title:
                document_title = heading_text
                blocks.append(new_block('title', text=heading_text))
            else:
                blocks.append(new_block('heading', level=level, text=heading_text))
            continue
        ordered_match = re.match(r'^\d+\.\s+(.+)$', stripped)
        unordered_match = re.match(r'^[-*+]\s+(.+)$', stripped)
        if ordered_match or unordered_match:
            flush_paragraph()
            list_type = 'ordered_list' if ordered_match else 'unordered_list'
            item_text = (ordered_match or unordered_match).group(1).strip()
            if blocks and blocks[-1].get('type') == list_type:
                blocks[-1].setdefault('items', []).append({'text': item_text})
            else:
                blocks.append(new_block(list_type, items=[{'text': item_text}]))
            continue
        pending_paragraph.append(stripped)

    flush_paragraph()
    if not document_title:
        first_text = next((block.get('text', '') for block in blocks if block.get('text')), '')
        document_title = title or first_text[:80] or 'Untitled Paper'
    return create_document(document_title, blocks, {'source_type': 'chat'})


def block_plain_text(block: dict[str, Any]) -> str:
    block_type = block.get('type')
    if block_type in {'title', 'heading', 'paragraph', 'blockquote'}:
        return str(block.get('text') or '')
    if block_type in {'ordered_list', 'unordered_list'}:
        return '\n'.join(str(item.get('text') or '') for item in block.get('items') or [])
    if block_type == 'code_block':
        return str(block.get('code') or '')
    if block_type == 'equation':
        return str(block.get('latex') or '')
    if block_type == 'citation':
        return str(block.get('text') or ', '.join(block.get('keys') or []))
    if block_type == 'figure':
        return str(block.get('caption') or block.get('src') or block.get('asset_id') or '')
    if block_type == 'table':
        rows = block.get('rows') or []
        return '\n'.join(' | '.join(str(cell) for cell in row) for row in rows)
    if block_type == 'raw_latex':
        return str(block.get('latex') or '')
    return ''


def document_outline(document: dict[str, Any]) -> list[dict[str, Any]]:
    outline = []
    for block in document.get('blocks') or []:
        if block.get('type') == 'title':
            outline.append({'level': 0, 'text': block.get('text', '')})
        elif block.get('type') == 'heading':
            outline.append(
                {
                    'level': int(block.get('level') or 1),
                    'text': block.get('text', ''),
                    'id': block.get('id'),
                }
            )
    return outline


def selected_context(
    document: dict[str, Any],
    block_id: str | None,
    selected_text: str | None = None,
    neighbor_count: int = 2,
) -> dict[str, Any]:
    blocks = document.get('blocks') or []
    block_index = next(
        (index for index, block in enumerate(blocks) if block.get('id') == block_id),
        -1,
    )
    current_block = blocks[block_index] if block_index >= 0 else None
    start = max(0, block_index - neighbor_count) if block_index >= 0 else 0
    end = min(len(blocks), block_index + neighbor_count + 1) if block_index >= 0 else 0
    section_heading = None
    section_parts: list[str] = []
    if block_index >= 0:
        for index in range(block_index, -1, -1):
            block = blocks[index]
            if block.get('type') in {'title', 'heading'}:
                section_heading = block_plain_text(block)
                break
        for block in blocks[block_index:]:
            if block is not current_block and block.get('type') == 'heading':
                break
            section_parts.append(block_plain_text(block))

    return {
        'title': document.get('title', ''),
        'outline': document_outline(document),
        'selected_text': selected_text or '',
        'current_block': current_block,
        'neighbor_blocks': blocks[start:end],
        'section_heading': section_heading or '',
        'section_excerpt': '\n'.join(part for part in section_parts if part).strip()[:2400],
    }

