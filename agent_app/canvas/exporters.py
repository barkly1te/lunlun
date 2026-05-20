from __future__ import annotations

import re
import zipfile
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET

from .model import block_plain_text

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG_REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'

ET.register_namespace('w', W_NS)
ET.register_namespace('r', R_NS)


def export_latex(document: dict[str, Any]) -> str:
    title = document.get('title') or 'Untitled Paper'
    lines = [
        r'\documentclass{article}',
        r'\usepackage{amsmath}',
        r'\usepackage{graphicx}',
        r'\usepackage{booktabs}',
        r'\usepackage{hyperref}',
        '',
        f'\\title{{{_escape_latex(title)}}}',
        r'\date{}',
        '',
        r'\begin{document}',
        r'\maketitle',
        '',
    ]
    first_title_seen = False
    for block in document.get('blocks') or []:
        block_type = block.get('type')
        if block_type == 'title':
            if first_title_seen:
                lines.extend([f'\\section*{{{_escape_latex(block_plain_text(block))}}}', ''])
            first_title_seen = True
        elif block_type == 'heading':
            lines.extend([_heading_command(block), ''])
        elif block_type == 'paragraph':
            lines.extend([_inline_to_latex(block.get('text') or ''), ''])
        elif block_type == 'blockquote':
            lines.extend([r'\begin{quote}', _inline_to_latex(block.get('text') or ''), r'\end{quote}', ''])
        elif block_type in {'ordered_list', 'unordered_list'}:
            env = 'enumerate' if block_type == 'ordered_list' else 'itemize'
            lines.append(f'\\begin{{{env}}}')
            for item in block.get('items') or []:
                lines.append(f'\\item {_inline_to_latex(item.get("text") or "")}')
            lines.extend([f'\\end{{{env}}}', ''])
        elif block_type == 'code_block':
            lines.extend([r'\begin{verbatim}', block.get('code') or '', r'\end{verbatim}', ''])
        elif block_type == 'equation':
            env = 'equation' if block.get('numbered', True) else 'equation*'
            lines.append(f'\\begin{{{env}}}')
            if block.get('label'):
                lines.append(f'\\label{{{_escape_latex_label(block["label"])}}}')
            lines.extend([(block.get('latex') or '').strip(), f'\\end{{{env}}}', ''])
        elif block_type == 'figure':
            lines.extend(_figure_to_latex(block))
        elif block_type == 'table':
            lines.extend(_table_to_latex(block))
        elif block_type == 'citation':
            citation_text = block.get('text') or ''
            keys = block.get('keys') or []
            if citation_text.startswith('\\'):
                lines.extend([citation_text, ''])
            elif keys:
                lines.extend([f'\\bibliography{{{",".join(_escape_latex_label(key) for key in keys)}}}', ''])
            elif citation_text:
                lines.extend([_inline_to_latex(citation_text), ''])
        elif block_type == 'raw_latex':
            lines.extend([(block.get('latex') or '').strip(), ''])
    lines.append(r'\end{document}')
    return '\n'.join(lines).replace('\n\n\n', '\n\n')


def export_docx(document: dict[str, Any]) -> bytes:
    word_document = ET.Element(_w('document'))
    body = ET.SubElement(word_document, _w('body'))

    first_title_seen = False
    for block in document.get('blocks') or []:
        block_type = block.get('type')
        if block_type == 'title':
            if first_title_seen:
                _append_paragraph(body, block_plain_text(block), style='Title')
            else:
                _append_paragraph(body, block_plain_text(block), style='Title')
                first_title_seen = True
        elif block_type == 'heading':
            _append_paragraph(body, block.get('text') or '', style=f'Heading{min(int(block.get("level") or 1), 3)}')
        elif block_type == 'paragraph':
            _append_paragraph(body, block.get('text') or '')
        elif block_type == 'blockquote':
            _append_paragraph(body, block.get('text') or '', style='Quote')
        elif block_type in {'ordered_list', 'unordered_list'}:
            prefix = '1. ' if block_type == 'ordered_list' else '- '
            for item in block.get('items') or []:
                _append_paragraph(body, prefix + (item.get('text') or ''))
        elif block_type == 'code_block':
            _append_paragraph(body, block.get('code') or '', style='Code')
        elif block_type == 'equation':
            _append_paragraph(body, f'Equation: {block.get("latex") or ""}', style='Equation')
        elif block_type == 'figure':
            caption = block.get('caption') or block.get('alt') or 'Figure'
            src = block.get('src') or block.get('asset_id') or ''
            _append_paragraph(body, f'Figure: {caption}' + (f' ({src})' if src else ''), style='Caption')
        elif block_type == 'table':
            _append_table(body, block.get('headers') or [], block.get('rows') or [])
            if block.get('caption'):
                _append_paragraph(body, f'Table: {block["caption"]}', style='Caption')
        elif block_type == 'citation':
            _append_paragraph(body, block.get('text') or ', '.join(block.get('keys') or []))
        elif block_type == 'raw_latex':
            _append_paragraph(body, block.get('latex') or '', style='Code')

    sect_pr = ET.SubElement(body, _w('sectPr'))
    page_size = ET.SubElement(sect_pr, _w('pgSz'))
    page_size.attrib[_w('w')] = '12240'
    page_size.attrib[_w('h')] = '15840'
    page_margin = ET.SubElement(sect_pr, _w('pgMar'))
    page_margin.attrib.update(
        {
            _w('top'): '1440',
            _w('right'): '1440',
            _w('bottom'): '1440',
            _w('left'): '1440',
            _w('header'): '720',
            _w('footer'): '720',
            _w('gutter'): '0',
        }
    )

    document_xml = ET.tostring(word_document, encoding='utf-8', xml_declaration=True)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', _content_types_xml())
        archive.writestr('_rels/.rels', _package_rels_xml())
        archive.writestr('word/_rels/document.xml.rels', _document_rels_xml())
        archive.writestr('word/document.xml', document_xml)
        archive.writestr('word/styles.xml', _styles_xml())
    return buffer.getvalue()


def _heading_command(block: dict[str, Any]) -> str:
    level = int(block.get('level') or 1)
    command = {
        1: 'section',
        2: 'subsection',
        3: 'subsubsection',
    }.get(level, 'paragraph')
    label = f'\\label{{{_escape_latex_label(block["label"])}}}' if block.get('label') else ''
    return f'\\{command}{{{_escape_latex(block.get("text") or "")}}}{label}'


def _figure_to_latex(block: dict[str, Any]) -> list[str]:
    src = block.get('src') or ''
    if src.startswith('/api/canvas/assets/'):
        src = block.get('asset_id') or src
    lines = [r'\begin{figure}[htbp]', r'\centering']
    if src:
        lines.append(f'\\includegraphics[width=0.8\\linewidth]{{{_escape_latex_path(src)}}}')
    else:
        lines.append(r'% Figure asset placeholder')
    if block.get('caption'):
        lines.append(f'\\caption{{{_inline_to_latex(block["caption"])}}}')
    if block.get('label'):
        lines.append(f'\\label{{{_escape_latex_label(block["label"])}}}')
    lines.extend([r'\end{figure}', ''])
    return lines


def _table_to_latex(block: dict[str, Any]) -> list[str]:
    rows = block.get('rows') or []
    headers = block.get('headers') or []
    column_count = max([len(headers), *(len(row) for row in rows)] or [1])
    lines = [r'\begin{table}[htbp]', r'\centering']
    if block.get('caption'):
        lines.append(f'\\caption{{{_inline_to_latex(block["caption"])}}}')
    if block.get('label'):
        lines.append(f'\\label{{{_escape_latex_label(block["label"])}}}')
    lines.append('\\begin{tabular}{' + 'l' * max(column_count, 1) + '}')
    lines.append(r'\toprule')
    if headers:
        lines.append(' & '.join(_inline_to_latex(cell) for cell in headers) + r' \\')
        lines.append(r'\midrule')
    for row in rows:
        padded = list(row) + [''] * (column_count - len(row))
        lines.append(' & '.join(_inline_to_latex(str(cell)) for cell in padded) + r' \\')
    lines.extend([r'\bottomrule', r'\end{tabular}', r'\end{table}', ''])
    return lines


def _inline_to_latex(text: str) -> str:
    converted = str(text)
    converted = re.sub(r'\[cite:([^\]]+)\]', lambda match: f'\\cite{{{_escape_latex_label(match.group(1))}}}', converted)
    converted = re.sub(r'\[ref:([^\]]+)\]', lambda match: f'\\ref{{{_escape_latex_label(match.group(1))}}}', converted)
    converted = re.sub(r'\[label:([^\]]+)\]', lambda match: f'\\label{{{_escape_latex_label(match.group(1))}}}', converted)
    converted = re.sub(r'\*\*([^*]+)\*\*', lambda match: f'\\textbf{{{_escape_latex(match.group(1))}}}', converted)
    converted = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', lambda match: f'\\emph{{{_escape_latex(match.group(1))}}}', converted)
    converted = re.sub(r'`([^`]+)`', lambda match: f'\\texttt{{{_escape_latex(match.group(1))}}}', converted)
    return _escape_latex(converted, keep_commands=True)


def _escape_latex(text: str, keep_commands: bool = False) -> str:
    value = str(text)
    placeholders: dict[str, str] = {}
    if keep_commands:
        for index, match in enumerate(re.finditer(r'\\[a-zA-Z]+\{[^{}]*\}', value)):
            key = f'@@CMD{index}@@'
            placeholders[key] = match.group(0)
            value = value.replace(match.group(0), key, 1)
    replacements = {
        '\\': r'\textbackslash{}',
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
    }
    escaped = ''.join(replacements.get(char, char) for char in value)
    for key, command in placeholders.items():
        escaped = escaped.replace(key, command)
    return escaped


def _escape_latex_label(value: str) -> str:
    return re.sub(r'[^a-zA-Z0-9:._/-]+', '-', str(value).strip()).strip('-')


def _escape_latex_path(value: str) -> str:
    return str(value).replace('\\', '/').replace('{', '').replace('}', '')


def _w(tag: str) -> str:
    return f'{{{W_NS}}}{tag}'


def _append_paragraph(parent: ET.Element, text: str, style: str | None = None) -> None:
    paragraph = ET.SubElement(parent, _w('p'))
    if style:
        props = ET.SubElement(paragraph, _w('pPr'))
        p_style = ET.SubElement(props, _w('pStyle'))
        p_style.attrib[_w('val')] = style
    run = ET.SubElement(paragraph, _w('r'))
    text_node = ET.SubElement(run, _w('t'))
    text_node.text = str(text)
    if text_node.text and (text_node.text.startswith(' ') or text_node.text.endswith(' ')):
        text_node.attrib['{http://www.w3.org/XML/1998/namespace}space'] = 'preserve'


def _append_table(parent: ET.Element, headers: list[str], rows: list[list[str]]) -> None:
    table = ET.SubElement(parent, _w('tbl'))
    tbl_pr = ET.SubElement(table, _w('tblPr'))
    borders = ET.SubElement(tbl_pr, _w('tblBorders'))
    for edge in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
        border = ET.SubElement(borders, _w(edge))
        border.attrib.update({_w('val'): 'single', _w('sz'): '4', _w('space'): '0', _w('color'): 'auto'})
    all_rows = [headers] if headers else []
    all_rows.extend(rows)
    for row in all_rows:
        tr = ET.SubElement(table, _w('tr'))
        for cell_text in row:
            tc = ET.SubElement(tr, _w('tc'))
            _append_paragraph(tc, str(cell_text))


def _content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""


def _package_rels_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PKG_REL_NS}">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""


def _document_rels_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PKG_REL_NS}"></Relationships>"""


def _styles_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W_NS}">
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:qFormat/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:qFormat/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:qFormat/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:qFormat/></w:style>
  <w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/></w:style>
  <w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="Caption"/></w:style>
  <w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/></w:style>
  <w:style w:type="paragraph" w:styleId="Equation"><w:name w:val="Equation"/></w:style>
</w:styles>"""

