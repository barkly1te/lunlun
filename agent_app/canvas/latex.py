from __future__ import annotations

import re
from typing import Any

from .model import create_document, new_block

SECTION_LEVELS = {
    'section': 1,
    'subsection': 2,
    'subsubsection': 3,
    'paragraph': 4,
}


def parse_latex_document(content: str, source_filename: str | None = None) -> dict[str, Any]:
    text = _strip_latex_comments(content)
    preamble, body, postamble = _split_document_environment(text)
    blocks: list[dict[str, Any]] = []
    title = _extract_first_braced_command(preamble, 'title') or 'Untitled Paper'
    if title:
        blocks.append(new_block('title', text=_clean_inline_latex(title)))

    preamble_without_title = _remove_first_braced_command(preamble, 'title').strip()
    if preamble_without_title:
        blocks.append(new_block('raw_latex', latex=preamble_without_title))

    _parse_latex_body(body, blocks)
    if postamble.strip():
        blocks.append(new_block('raw_latex', latex=postamble.strip()))

    metadata = {'source_type': 'latex'}
    if source_filename:
        metadata['source_filename'] = source_filename
    return create_document(_clean_inline_latex(title), blocks, metadata)


def _split_document_environment(text: str) -> tuple[str, str, str]:
    begin_match = re.search(r'\\begin\{document\}', text)
    if begin_match is None:
        return '', text, ''
    end_match = re.search(r'\\end\{document\}', text[begin_match.end() :])
    body_start = begin_match.end()
    if end_match is None:
        return text[: begin_match.start()], text[body_start:], ''
    body_end = body_start + end_match.start()
    return text[: begin_match.start()], text[body_start:body_end], text[body_end + len(r'\end{document}') :]


def _strip_latex_comments(text: str) -> str:
    cleaned_lines = []
    for line in text.splitlines():
        index = 0
        while True:
            percent_index = line.find('%', index)
            if percent_index < 0:
                cleaned_lines.append(line.rstrip())
                break
            slash_count = 0
            cursor = percent_index - 1
            while cursor >= 0 and line[cursor] == '\\':
                slash_count += 1
                cursor -= 1
            if slash_count % 2 == 1:
                index = percent_index + 1
                continue
            cleaned_lines.append(line[:percent_index].rstrip())
            break
    return '\n'.join(cleaned_lines)


def _extract_first_braced_command(text: str, command: str) -> str | None:
    match = re.search(rf'\\{re.escape(command)}\*?\s*\{{', text)
    if match is None:
        return None
    open_index = text.find('{', match.start())
    close_index = _find_matching_brace(text, open_index)
    if close_index < 0:
        return None
    return text[open_index + 1 : close_index].strip()


def _remove_first_braced_command(text: str, command: str) -> str:
    match = re.search(rf'\\{re.escape(command)}\*?\s*\{{', text)
    if match is None:
        return text
    open_index = text.find('{', match.start())
    close_index = _find_matching_brace(text, open_index)
    if close_index < 0:
        return text
    return text[: match.start()] + text[close_index + 1 :]


def _find_matching_brace(text: str, open_index: int) -> int:
    if open_index < 0 or open_index >= len(text) or text[open_index] != '{':
        return -1
    depth = 0
    index = open_index
    while index < len(text):
        char = text[index]
        if char == '\\':
            index += 2
            continue
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def _parse_latex_body(text: str, blocks: list[dict[str, Any]]) -> None:
    token_pattern = re.compile(
        r'\\(?:title|section|subsection|subsubsection|paragraph)\*?\s*\{'
        r'|\\begin\{[^}]+\}'
        r'|\\bibliography\s*\{'
        r'|\\bibliographystyle\s*\{',
        re.DOTALL,
    )
    position = 0
    while position < len(text):
        match = token_pattern.search(text, position)
        if match is None:
            _append_text_blocks(text[position:], blocks)
            break

        _append_text_blocks(text[position : match.start()], blocks)
        token = match.group(0)
        if token.startswith('\\begin'):
            env_match = re.match(r'\\begin\{([^}]+)\}', token)
            env = env_match.group(1) if env_match else ''
            raw, content, end_position = _read_environment(text, match.start(), env)
            if not raw:
                blocks.append(new_block('raw_latex', latex=text[match.start() :].strip()))
                break
            _append_environment_block(env, raw, content, blocks)
            position = end_position
            continue

        command_match = re.match(r'\\([a-zA-Z]+)', token)
        command = command_match.group(1) if command_match else ''
        command_text, end_position = _read_command_argument(text, match.start())
        if command_text is None:
            blocks.append(new_block('raw_latex', latex=token.strip()))
            position = match.end()
            continue
        if command == 'title':
            blocks.append(new_block('title', text=_clean_inline_latex(command_text)))
        elif command in SECTION_LEVELS:
            label = _extract_first_braced_command(command_text, 'label')
            heading_text = _clean_inline_latex(_remove_first_braced_command(command_text, 'label'))
            block = new_block('heading', level=SECTION_LEVELS[command], text=heading_text)
            if label:
                block['label'] = label
            blocks.append(block)
        elif command in {'bibliography', 'bibliographystyle'}:
            blocks.append(
                new_block(
                    'citation',
                    keys=[key.strip() for key in command_text.split(',') if key.strip()]
                    if command == 'bibliography'
                    else [],
                    text=f'\\{command}{{{command_text}}}',
                )
            )
        else:
            blocks.append(new_block('raw_latex', latex=text[match.start() : end_position]))
        position = end_position


def _read_command_argument(text: str, command_start: int) -> tuple[str | None, int]:
    open_index = text.find('{', command_start)
    if open_index < 0:
        return None, command_start
    close_index = _find_matching_brace(text, open_index)
    if close_index < 0:
        return None, command_start
    return text[open_index + 1 : close_index].strip(), close_index + 1


def _read_environment(text: str, begin_start: int, env: str) -> tuple[str, str, int]:
    begin_match = re.match(r'\\begin\{[^}]+\}', text[begin_start:])
    if begin_match is None:
        return '', '', begin_start
    content_start = begin_start + begin_match.end()
    end_token = f'\\end{{{env}}}'
    end_index = text.find(end_token, content_start)
    if end_index < 0:
        return '', '', begin_start
    raw_end = end_index + len(end_token)
    return text[begin_start:raw_end], text[content_start:end_index].strip(), raw_end


def _append_environment_block(
    env: str,
    raw_latex: str,
    content: str,
    blocks: list[dict[str, Any]],
) -> None:
    clean_env = env.rstrip('*')
    if clean_env in {'equation', 'align', 'gather', 'multline'}:
        label = _extract_first_braced_command(content, 'label')
        equation = _remove_first_braced_command(content, 'label').strip()
        block = new_block('equation', latex=equation, numbered=not env.endswith('*'))
        if label:
            block['label'] = label
        blocks.append(block)
        return
    if clean_env in {'verbatim', 'lstlisting', 'minted'}:
        blocks.append(new_block('code_block', language='', code=content))
        return
    if clean_env in {'itemize', 'enumerate'}:
        items = [{'text': _clean_inline_latex(item)} for item in _split_latex_items(content)]
        blocks.append(new_block('ordered_list' if clean_env == 'enumerate' else 'unordered_list', items=items))
        return
    if clean_env in {'quote', 'quotation'}:
        blocks.append(new_block('blockquote', text=_clean_inline_latex(content)))
        return
    if clean_env == 'figure':
        caption = _extract_first_braced_command(content, 'caption') or ''
        label = _extract_first_braced_command(content, 'label')
        include_match = re.search(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', content)
        block = new_block(
            'figure',
            caption=_clean_inline_latex(caption),
            src=include_match.group(1).strip() if include_match else '',
            raw_latex=raw_latex,
        )
        if label:
            block['label'] = label
        blocks.append(block)
        return
    if clean_env == 'table':
        caption = _extract_first_braced_command(content, 'caption') or ''
        label = _extract_first_braced_command(content, 'label')
        rows = _parse_tabular_rows(content)
        block = new_block('table', caption=_clean_inline_latex(caption), headers=[], rows=rows, raw_latex=raw_latex)
        if label:
            block['label'] = label
        blocks.append(block)
        return
    if clean_env == 'abstract':
        blocks.append(new_block('heading', level=1, text='Abstract'))
        _append_text_blocks(content, blocks)
        return
    if clean_env in {'thebibliography'}:
        blocks.append(new_block('citation', keys=[], text=raw_latex))
        return
    blocks.append(new_block('raw_latex', latex=raw_latex))


def _split_latex_items(content: str) -> list[str]:
    parts = re.split(r'(?<!\\)\\item(?:\[[^\]]*\])?', content)
    return [part.strip() for part in parts if part.strip()]


def _parse_tabular_rows(content: str) -> list[list[str]]:
    tabular_match = re.search(
        r'\\begin\{tabular\}\{[^}]*\}(.*?)\\end\{tabular\}',
        content,
        flags=re.DOTALL,
    )
    if tabular_match is None:
        return []
    body = tabular_match.group(1)
    body = re.sub(r'\\(?:toprule|midrule|bottomrule|hline|cline\{[^}]+\})', '', body)
    rows = []
    for raw_row in re.split(r'\\\\', body):
        cells = [_clean_inline_latex(cell.strip()) for cell in raw_row.split('&')]
        cells = [cell for cell in cells if cell]
        if cells:
            rows.append(cells)
    return rows


def _append_text_blocks(chunk: str, blocks: list[dict[str, Any]]) -> None:
    for paragraph in re.split(r'\n\s*\n', chunk):
        stripped = paragraph.strip()
        if not stripped:
            continue
        if stripped.startswith('\\') and not re.match(r'\\(?:cite|ref|textbf|emph|textit|texttt)\b', stripped):
            blocks.append(new_block('raw_latex', latex=stripped))
            continue
        cleaned = _clean_inline_latex(stripped)
        citations = _extract_inline_keys(stripped, 'cite')
        refs = _extract_inline_keys(stripped, 'ref')
        blocks.append(new_block('paragraph', text=cleaned, citations=citations, refs=refs))


def _extract_inline_keys(text: str, command: str) -> list[str]:
    keys: list[str] = []
    for match in re.finditer(rf'\\{command}\w*\{{([^}}]+)\}}', text):
        keys.extend(key.strip() for key in match.group(1).split(',') if key.strip())
    return keys


def _clean_inline_latex(text: str) -> str:
    cleaned = text.replace('~', ' ')
    cleaned = re.sub(r'\\cite\w*\{([^}]+)\}', lambda match: f'[cite:{match.group(1)}]', cleaned)
    cleaned = re.sub(r'\\ref\{([^}]+)\}', lambda match: f'[ref:{match.group(1)}]', cleaned)
    cleaned = re.sub(r'\\label\{([^}]+)\}', lambda match: f'[label:{match.group(1)}]', cleaned)
    replacements = [
        (r'\\textbf\{([^{}]*)\}', r'**\1**'),
        (r'\\emph\{([^{}]*)\}', r'*\1*'),
        (r'\\textit\{([^{}]*)\}', r'*\1*'),
        (r'\\texttt\{([^{}]*)\}', r'`\1`'),
    ]
    previous = None
    while previous != cleaned:
        previous = cleaned
        for pattern, replacement in replacements:
            cleaned = re.sub(pattern, replacement, cleaned)
    cleaned = re.sub(r'\\[a-zA-Z]+\*?(?:\[[^\]]*\])?', '', cleaned)
    cleaned = cleaned.replace(r'\%', '%').replace(r'\&', '&').replace(r'\_', '_')
    cleaned = cleaned.replace(r'\#', '#').replace(r'\$', '$').replace(r'\{', '{').replace(r'\}', '}')
    return re.sub(r'[ \t]+', ' ', cleaned).strip()

