from __future__ import annotations

import mimetypes
import re
import zipfile
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

from .model import create_document, new_block, new_id

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
}


def parse_docx_document(
    content: bytes,
    source_filename: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    assets: list[dict[str, Any]] = []
    with zipfile.ZipFile(BytesIO(content)) as archive:
        document_xml = archive.read('word/document.xml')
        relationships = _read_relationships(archive)
        numbering = _read_numbering(archive)
        root = ET.fromstring(document_xml)
        body = root.find('w:body', NS)
        blocks: list[dict[str, Any]] = []
        title = _filename_title(source_filename)
        in_references = False

        if body is None:
            return create_document(title, [], {'source_type': 'docx'}), []

        for child in body:
            if child.tag == _q('w', 'p'):
                paragraph_assets = _extract_paragraph_images(child, archive, relationships)
                for asset in paragraph_assets:
                    assets.append(asset)
                text = _paragraph_text(child, relationships).strip()
                style = _paragraph_style(child)
                list_type = _paragraph_list_type(child, style, numbering)
                heading_level = _heading_level(style)
                lower_text = text.casefold()

                if _is_title_style(style) and text:
                    title = text
                    blocks.append(new_block('title', text=text))
                    in_references = False
                elif heading_level and text:
                    blocks.append(new_block('heading', level=heading_level, text=text))
                    in_references = lower_text in {'references', 'bibliography', '参考文献'}
                elif list_type and text:
                    if blocks and blocks[-1].get('type') == list_type:
                        blocks[-1].setdefault('items', []).append({'text': text})
                    else:
                        blocks.append(new_block(list_type, items=[{'text': text}]))
                elif text:
                    if in_references:
                        blocks.append(new_block('citation', keys=[], text=text))
                    else:
                        blocks.append(new_block('paragraph', text=text))

                for asset in paragraph_assets:
                    blocks.append(
                        new_block(
                            'figure',
                            asset_id=asset['id'],
                            src=f'/api/canvas/assets/{asset["id"]}',
                            caption=text if text and len(text) < 180 else '',
                            alt=asset['filename'],
                        )
                    )
            elif child.tag == _q('w', 'tbl'):
                rows = _table_rows(child, relationships)
                if rows:
                    blocks.append(new_block('table', headers=[], rows=rows, caption=''))

    metadata = {'source_type': 'docx'}
    if source_filename:
        metadata['source_filename'] = source_filename
    return create_document(title, blocks, metadata), assets


def _q(prefix: str, tag: str) -> str:
    return f'{{{NS[prefix]}}}{tag}'


def _filename_title(source_filename: str | None) -> str:
    if not source_filename:
        return 'Untitled Paper'
    title = re.sub(r'\.[^.]+$', '', source_filename).strip()
    return title or 'Untitled Paper'


def _read_relationships(archive: zipfile.ZipFile) -> dict[str, dict[str, str]]:
    try:
        rels_xml = archive.read('word/_rels/document.xml.rels')
    except KeyError:
        return {}
    root = ET.fromstring(rels_xml)
    relationships = {}
    for rel in root.findall('rel:Relationship', NS):
        rel_id = rel.attrib.get('Id')
        if not rel_id:
            continue
        relationships[rel_id] = {
            'type': rel.attrib.get('Type', ''),
            'target': rel.attrib.get('Target', ''),
            'target_mode': rel.attrib.get('TargetMode', ''),
        }
    return relationships


def _read_numbering(archive: zipfile.ZipFile) -> dict[str, str]:
    try:
        numbering_xml = archive.read('word/numbering.xml')
    except KeyError:
        return {}
    root = ET.fromstring(numbering_xml)
    abstract_formats: dict[str, str] = {}
    for abstract in root.findall('w:abstractNum', NS):
        abstract_id = abstract.attrib.get(_q('w', 'abstractNumId'))
        fmt = abstract.find('.//w:numFmt', NS)
        if abstract_id and fmt is not None:
            abstract_formats[abstract_id] = fmt.attrib.get(_q('w', 'val'), '')

    num_formats: dict[str, str] = {}
    for num in root.findall('w:num', NS):
        num_id = num.attrib.get(_q('w', 'numId'))
        abstract_ref = num.find('w:abstractNumId', NS)
        abstract_id = abstract_ref.attrib.get(_q('w', 'val')) if abstract_ref is not None else None
        if num_id and abstract_id:
            num_formats[num_id] = abstract_formats.get(abstract_id, '')
    return num_formats


def _paragraph_style(paragraph: ET.Element) -> str:
    style = paragraph.find('w:pPr/w:pStyle', NS)
    return style.attrib.get(_q('w', 'val'), '') if style is not None else ''


def _paragraph_num_id(paragraph: ET.Element) -> str:
    num_id = paragraph.find('w:pPr/w:numPr/w:numId', NS)
    return num_id.attrib.get(_q('w', 'val'), '') if num_id is not None else ''


def _is_title_style(style: str) -> bool:
    return style.casefold().replace(' ', '') in {'title', 'papertitle'}


def _heading_level(style: str) -> int | None:
    normalized = style.casefold().replace(' ', '')
    match = re.search(r'heading([1-6])', normalized)
    if match:
        return int(match.group(1))
    return None


def _paragraph_list_type(
    paragraph: ET.Element,
    style: str,
    numbering: dict[str, str],
) -> str | None:
    num_id = _paragraph_num_id(paragraph)
    style_lower = style.casefold()
    num_fmt = numbering.get(num_id, '')
    if num_fmt == 'bullet' or 'bullet' in style_lower:
        return 'unordered_list'
    if num_id or 'number' in style_lower or 'listparagraph' in style_lower:
        return 'ordered_list'
    return None


def _paragraph_text(
    paragraph: ET.Element,
    relationships: dict[str, dict[str, str]],
) -> str:
    parts: list[str] = []
    for child in paragraph:
        if child.tag == _q('w', 'r'):
            parts.append(_run_text(child))
        elif child.tag == _q('w', 'hyperlink'):
            text = ''.join(_run_text(run) for run in child.findall('w:r', NS))
            rel_id = child.attrib.get(_q('r', 'id'))
            target = relationships.get(rel_id or '', {}).get('target')
            parts.append(f'[{text}]({target})' if target and text else text)
    if not parts:
        parts.append(''.join(node.text or '' for node in paragraph.findall('.//w:t', NS)))
    return ''.join(parts).replace('\xa0', ' ')


def _run_text(run: ET.Element) -> str:
    text = ''.join(node.text or '' for node in run.findall('.//w:t', NS))
    if not text:
        if run.find('w:tab', NS) is not None:
            return '\t'
        if run.find('w:br', NS) is not None:
            return '\n'
        return ''
    props = run.find('w:rPr', NS)
    if props is not None:
        if props.find('w:code', NS) is not None:
            text = f'`{text}`'
        if props.find('w:i', NS) is not None:
            text = f'*{text}*'
        if props.find('w:b', NS) is not None:
            text = f'**{text}**'
    return text


def _extract_paragraph_images(
    paragraph: ET.Element,
    archive: zipfile.ZipFile,
    relationships: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    assets = []
    for blip in paragraph.findall('.//a:blip', NS):
        rel_id = blip.attrib.get(_q('r', 'embed'))
        if not rel_id:
            continue
        target = relationships.get(rel_id, {}).get('target', '')
        if not target:
            continue
        archive_path = str(PurePosixPath('word') / target).replace('/../', '/')
        if archive_path not in archive.namelist() and target.startswith('media/'):
            archive_path = f'word/{target}'
        try:
            data = archive.read(archive_path)
        except KeyError:
            continue
        filename = PurePosixPath(target).name or f'{new_id("image")}.bin'
        mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        assets.append(
            {
                'id': new_id('asset'),
                'filename': filename,
                'mime_type': mime_type,
                'content': data,
            }
        )
    return assets


def _table_rows(table: ET.Element, relationships: dict[str, dict[str, str]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.findall('w:tr', NS):
        cells = []
        for cell in row.findall('w:tc', NS):
            paragraphs = [
                _paragraph_text(paragraph, relationships).strip()
                for paragraph in cell.findall('w:p', NS)
            ]
            cells.append('\n'.join(part for part in paragraphs if part))
        if any(cells):
            rows.append(cells)
    return rows

