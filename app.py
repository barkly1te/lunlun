import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode, urlparse

import chainlit as cl
from agentscope.message import Msg
from agentscope.pipeline import stream_printing_messages
from chainlit.context import context as chainlit_context
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.server import app as chainlit_app
from chainlit.types import CommandDict, ThreadDict
from fastapi import File, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from agent_app.agent_factory import MAX_CONTEXT_TOKENS, build_agent
from agent_app.canvas.docx import parse_docx_document
from agent_app.canvas.edit import (
    generate_canvas_agent_reply,
    generate_edit_candidate,
    parse_canvas_agent_response,
    prepare_canvas_agent_prompt,
)
from agent_app.canvas.exporters import export_docx, export_latex
from agent_app.canvas.latex import parse_latex_document
from agent_app.canvas.model import create_document, markdown_to_canvas_document, normalize_document
from agent_app.canvas.storage import (
    append_canvas_message,
    create_document_record,
    delete_document_record,
    get_asset,
    get_document_record,
    get_or_create_conversation,
    list_canvas_messages,
    list_documents,
    list_versions,
    restore_previous_version,
    restore_version,
    save_document_record,
    update_canvas_message_response,
)
from agent_app.skills.catalog import get_registered_skill, get_registered_skills
from database import init_sqlite_db, load_agent_state, save_agent_state

IMAGE_HINT_TEMPLATE = (
    '\n\n[系统提示：用户上传了图片。图片会作为原生多模态 image block 提供给你，同时'
    '系统也已缓存本地路径：{paths}。如果你需要调用 generate_image_tool 做改图，请'
    '从这些路径中提取合适的 image_path 参数。]'
)
GEN_IMAGE_PATTERN = re.compile(r'\[GEN_IMAGE:\s*(.*?)\]')
IMAGE_HINT_PATTERN = re.compile(
    r'\n*\[系统提示：用户上传了图片。图片会作为原生多模态 image block 提供给你，同时'
    r'系统也已缓存本地路径：.*?如果你需要调用 generate_image_tool 做改图，请'
    r'从这些路径中提取合适的 image_path 参数。]',
    re.DOTALL,
)
SLASH_COMMAND_PATTERN = re.compile(
    r'^\s*/(?P<name>[a-zA-Z0-9][a-zA-Z0-9-]*)(?P<rest>(?:\s.*)?)\Z',
    re.DOTALL,
)
SLASH_COMMAND_ROUTE_TEMPLATE = (
    '[系统路由：用户在本轮消息开头显式选择了 skill `/{skill_name}`。'
    '你必须优先使用该同名 skill。请先调用 `read_registered_skill` 读取它的完整 SKILL.md，'
    '再严格按照该 skill 的说明完成任务。只有当该 skill 文档明确要求借用其他 skill 时，'
    '你才可以继续读取或使用其他 skill。目标 skill 目录：{skill_dir}。目标 SKILL.md：{skill_md_path}。]'
    '\n\n用户的原始需求如下：\n{user_content}'
)
SKILL_COMMAND_ICON = 'sparkles'
LOGS_DIR = Path(__file__).resolve().parent / 'logs'
CANVAS_HTML_PATH = Path(__file__).resolve().parent / 'public' / 'canvas.html'
ACTIVE_AGENTS_BY_THREAD: dict[str, Any] = {}
AGENT_LOCKS: dict[int, asyncio.Lock] = {}
LAST_ACTIVE_THREAD_ID: Optional[str] = None
CANVAS_FALLBACK_AGENT: Any | None = None

init_sqlite_db()


@cl.data_layer
def get_data_layer():
    return SQLAlchemyDataLayer(conninfo='sqlite+aiosqlite:///lunlun_history.db')


@cl.header_auth_callback
def header_auth_callback(headers) -> Optional[cl.User]:
    return cl.User(identifier='lunlun_internal_user', metadata={'role': 'admin'})


def _current_thread_id() -> Optional[str]:
    return getattr(chainlit_context.session, 'thread_id', None)


def _register_active_agent(agent: Any, thread_id: Optional[str] = None) -> None:
    global LAST_ACTIVE_THREAD_ID
    key = thread_id or getattr(agent, '_lunlun_thread_id', None) or 'default'
    setattr(agent, '_lunlun_thread_id', key)
    ACTIVE_AGENTS_BY_THREAD[key] = agent
    LAST_ACTIVE_THREAD_ID = key


def _agent_lock(agent: Any) -> asyncio.Lock:
    key = id(agent)
    lock = AGENT_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        AGENT_LOCKS[key] = lock
    return lock


def _canvas_thread_from_request(request: Request) -> Optional[str]:
    return (
        request.headers.get('x-lunlun-thread-id')
        or request.query_params.get('thread')
        or request.query_params.get('thread_id')
    )


def _canvas_url(path: str = '/canvas', **params: str) -> str:
    clean_params = {key: value for key, value in params.items() if value}
    if not clean_params:
        return path
    return f'{path}?{urlencode(clean_params)}'


def _get_canvas_agent(request: Request) -> Any:
    global CANVAS_FALLBACK_AGENT
    requested_thread_id = _canvas_thread_from_request(request)
    if requested_thread_id and requested_thread_id in ACTIVE_AGENTS_BY_THREAD:
        return ACTIVE_AGENTS_BY_THREAD[requested_thread_id]
    if LAST_ACTIVE_THREAD_ID and LAST_ACTIVE_THREAD_ID in ACTIVE_AGENTS_BY_THREAD:
        return ACTIVE_AGENTS_BY_THREAD[LAST_ACTIVE_THREAD_ID]
    if CANVAS_FALLBACK_AGENT is None:
        CANVAS_FALLBACK_AGENT = build_agent()
        _register_active_agent(CANVAS_FALLBACK_AGENT, 'canvas_fallback')
    return CANVAS_FALLBACK_AGENT


async def _run_canvas_edit_with_shared_agent(
    agent: Any,
    document: dict[str, Any],
    block_id: str | None,
    selected_text: str,
    instruction: str,
    mode: str,
) -> dict[str, str]:
    state_snapshot = agent.state_dict()
    queue_enabled = not getattr(agent, '_disable_msg_queue', True)
    previous_queue = getattr(agent, 'msg_queue', None)
    console_enabled = not getattr(agent, '_disable_console_output', False)
    try:
        agent.set_console_output_enabled(False)
        agent.set_msg_queue_enabled(False)
        candidate = await generate_edit_candidate(
            agent,
            document,
            block_id,
            selected_text,
            instruction,
            mode,
        )
        candidate['agent_shared'] = 'true'
        candidate['agent_thread_id'] = str(getattr(agent, '_lunlun_thread_id', ''))
        return candidate
    finally:
        try:
            agent.load_state_dict(state_snapshot, strict=False)
        finally:
            if queue_enabled:
                agent.set_msg_queue_enabled(True, previous_queue)
            else:
                agent.set_msg_queue_enabled(False)
            agent.set_console_output_enabled(console_enabled)


async def _run_canvas_chat_with_shared_agent(
    agent: Any,
    document: dict[str, Any],
    block_id: str | None,
    selected_text: str,
    user_content: str,
    recent_messages: list[dict[str, Any]],
    selected_block_ids: list[str] | None = None,
) -> dict[str, Any]:
    state_snapshot = agent.state_dict()
    queue_enabled = not getattr(agent, '_disable_msg_queue', True)
    previous_queue = getattr(agent, 'msg_queue', None)
    console_enabled = not getattr(agent, '_disable_console_output', False)
    try:
        agent.set_console_output_enabled(False)
        agent.set_msg_queue_enabled(False)
        result = await generate_canvas_agent_reply(
            agent,
            document,
            block_id,
            selected_text,
            user_content,
            recent_messages,
            selected_block_ids,
        )
        result['agent_shared'] = True
        result['agent_thread_id'] = str(getattr(agent, '_lunlun_thread_id', ''))
        return result
    finally:
        try:
            agent.load_state_dict(state_snapshot, strict=False)
        finally:
            if queue_enabled:
                agent.set_msg_queue_enabled(True, previous_queue)
            else:
                agent.set_msg_queue_enabled(False)
            agent.set_console_output_enabled(console_enabled)


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'


async def _stream_canvas_chat_with_shared_agent(
    agent: Any,
    document: dict[str, Any],
    block_id: str | None,
    selected_text: str,
    user_content: str,
    recent_messages: list[dict[str, Any]],
    selected_block_ids: list[str] | None = None,
):
    prompt, context, target_text = prepare_canvas_agent_prompt(
        document,
        block_id,
        selected_text,
        user_content,
        recent_messages,
        selected_block_ids,
    )
    user_msg = Msg(name='user', content=prompt, role='user')
    response_holder: dict[str, Msg] = {}
    stream_state_by_id: dict[str, dict[str, str]] = {}
    thinking_by_id: dict[str, str] = {}
    state_snapshot = agent.state_dict()
    queue_enabled = not getattr(agent, '_disable_msg_queue', True)
    previous_queue = getattr(agent, 'msg_queue', None)
    console_enabled = not getattr(agent, '_disable_console_output', False)

    async def _invoke_agent() -> None:
        response_holder['response'] = await agent(user_msg)

    try:
        agent.set_console_output_enabled(False)
        async for printed_msg, _ in stream_printing_messages([agent], _invoke_agent()):
            msg_id = getattr(printed_msg, 'id', None) or f'stream-{len(stream_state_by_id)}'
            state = stream_state_by_id.setdefault(msg_id, {'thinking': '', 'text': ''})
            thinking_text, text_text = _extract_response_parts(printed_msg.content)
            if thinking_text:
                thinking_update, replace_thinking = _compute_stream_update(
                    state['thinking'],
                    thinking_text,
                )
                if thinking_update or replace_thinking:
                    yield _sse_event(
                        'thinking',
                        {
                            'delta': thinking_text if replace_thinking else thinking_update,
                            'replace': replace_thinking,
                        },
                    )
                state['thinking'] = thinking_text
                thinking_by_id[msg_id] = thinking_text
            if text_text:
                text_update, replace_text = _compute_stream_update(state['text'], text_text)
                if text_update or replace_text:
                    yield _sse_event(
                        'answer_progress',
                        {
                            'delta': '',
                            'replace': False,
                        },
                    )
                state['text'] = text_text

        response = response_holder.get('response')
        if response is None:
            raise RuntimeError('Agent finished without producing a response.')
        _, final_text = _extract_response_parts(response.content)
        if not final_text:
            final_text = str(response.content or '')
        result = parse_canvas_agent_response(final_text, context, target_text)
        result['thinking_text'] = '\n\n'.join(
            part for part in thinking_by_id.values() if part
        ).strip()
        result['agent_shared'] = True
        result['agent_thread_id'] = str(getattr(agent, '_lunlun_thread_id', ''))
        yield _sse_event('final', result)
    finally:
        try:
            agent.load_state_dict(state_snapshot, strict=False)
        finally:
            if queue_enabled:
                agent.set_msg_queue_enabled(True, previous_queue)
            else:
                agent.set_msg_queue_enabled(False)
            agent.set_console_output_enabled(console_enabled)


def _build_skill_commands() -> list[CommandDict]:
    return [
        {
            'id': skill.name,
            'description': skill.description,
            'icon': SKILL_COMMAND_ICON,
        }
        for skill in get_registered_skills()
    ]


async def _set_skill_commands() -> None:
    await chainlit_context.emitter.set_commands(_build_skill_commands())


def _format_available_skill_commands() -> str:
    skills = get_registered_skills()
    if not skills:
        return '当前没有可用的 skill 命令。'

    return '\n'.join(f'- /{skill.name}: {skill.description}' for skill in skills)



def _canvas_skill_payload() -> list[dict[str, str]]:
    return [
        {
            'name': skill.name,
            'description': skill.description,
            'icon': SKILL_COMMAND_ICON,
        }
        for skill in get_registered_skills()
    ]


def _collect_image_paths(message: cl.Message) -> list[str]:
    image_paths = []
    for element in message.elements or []:
        mime = getattr(element, 'mime', '') or ''
        path = getattr(element, 'path', None)
        if 'image' in mime and path and os.path.exists(path):
            image_paths.append(path)
    return image_paths


def _strip_image_hint(content: str) -> str:
    stripped_content = IMAGE_HINT_PATTERN.sub('', content)
    if stripped_content == content:
        return content
    return stripped_content.strip()


def _append_image_hint(content: str, image_paths: list[str]) -> str:
    if image_paths:
        return content + IMAGE_HINT_TEMPLATE.format(paths=', '.join(image_paths))
    return content


def _build_user_msg_content(
    text_content: str,
    image_paths: list[str],
) -> str | list[dict[str, Any]]:
    if not image_paths:
        return text_content

    content_blocks: list[dict[str, Any]] = []
    if text_content:
        content_blocks.append({'type': 'text', 'text': text_content})

    for image_path in image_paths:
        content_blocks.append(
            {
                'type': 'image',
                'source': {
                    'type': 'url',
                    'url': image_path,
                },
            }
        )

    return content_blocks


def _parse_slash_command(content: str) -> tuple[Optional[str], str, bool]:
    stripped_content = content.lstrip()
    match = SLASH_COMMAND_PATTERN.match(stripped_content)
    if match is None:
        return None, content, False

    skill_name = match.group('name')
    remaining_content = (match.group('rest') or '').lstrip()
    return skill_name, remaining_content, True


def _resolve_skill_selection(
    raw_content: str,
    selected_command: Optional[str] = None,
) -> tuple[Optional[str], str, bool]:
    if selected_command:
        return selected_command, raw_content, True
    return _parse_slash_command(raw_content)


def _build_user_content(
    raw_content: str,
    image_paths: list[str],
    selected_command: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    skill_name, remaining_content, has_slash_command = _resolve_skill_selection(
        raw_content,
        selected_command,
    )
    if not has_slash_command:
        return None, _append_image_hint(raw_content, image_paths)

    skill = get_registered_skill(skill_name or '')
    if skill is None:
        return (
            f'未找到 skill `/{skill_name}`。\n\n可用命令：\n{_format_available_skill_commands()}',
            None,
        )

    if not remaining_content.strip() and not image_paths:
        return (
            f'已选择 `/{skill.name}`。\n\n{skill.description}\n\n请继续输入具体需求。',
            None,
        )

    user_content = _append_image_hint(remaining_content, image_paths).strip()
    if not user_content:
        user_content = '（用户未提供额外文本，仅通过 slash command 选择了该 skill。）'

    return (
        None,
        SLASH_COMMAND_ROUTE_TEMPLATE.format(
            skill_name=skill.name,
            skill_dir=skill.skill_dir,
            skill_md_path=skill.skill_md_path,
            user_content=user_content,
        ),
    )


def _restore_user_content(raw_content: str, selected_command: Optional[str] = None) -> str:
    _, prepared_content = _build_user_content(raw_content, [], selected_command)
    return prepared_content or raw_content


def _is_remote_or_data_url(url: str) -> bool:
    scheme = urlparse(url).scheme.lower()
    return scheme in {'http', 'https', 'data'}


def _local_image_path_exists(url: str) -> bool:
    raw_url = url.removeprefix('file://')
    return os.path.exists(raw_url) and os.path.isfile(raw_url)


def _should_replace_image_url(url: str, drop_local_images: bool) -> bool:
    if _is_remote_or_data_url(url):
        return False
    if drop_local_images:
        return True
    return not _local_image_path_exists(url)


def _sanitize_msg_content(msg: Msg, drop_local_images: bool = False) -> int:
    sanitized_count = 0

    if isinstance(msg.content, str):
        stripped_content = _strip_image_hint(msg.content)
        if stripped_content != msg.content:
            msg.content = (
                stripped_content
                or '[历史上传图片已过期，图片内容不再作为本轮上下文提供。]'
            )
            sanitized_count += 1
        return sanitized_count

    if not isinstance(msg.content, list):
        return sanitized_count

    sanitized_blocks: list[dict[str, Any]] = []
    for block in msg.content:
        if not isinstance(block, dict):
            sanitized_blocks.append(block)
            continue

        if block.get('type') == 'text':
            text = block.get('text', '')
            stripped_text = _strip_image_hint(text)
            if stripped_text != text:
                sanitized_count += 1
            if stripped_text:
                sanitized_blocks.append({**block, 'text': stripped_text})
            continue

        if block.get('type') == 'image':
            source = block.get('source') or {}
            image_url = source.get('url') if source.get('type') == 'url' else None
            if image_url and _should_replace_image_url(image_url, drop_local_images):
                sanitized_blocks.append(
                    {
                        'type': 'text',
                        'text': '[历史上传图片已过期，图片内容不再作为本轮上下文提供。]',
                    }
                )
                sanitized_count += 1
                continue

        sanitized_blocks.append(block)

    msg.content = sanitized_blocks
    return sanitized_count


def _sanitize_agent_memory(agent, drop_local_images: bool = False) -> int:
    memory = getattr(agent, 'memory', None)
    if memory is None or not hasattr(memory, 'content'):
        return 0

    sanitized_count = 0
    for item in memory.content:
        msg = item[0] if isinstance(item, (list, tuple)) and item else item
        if isinstance(msg, Msg):
            sanitized_count += _sanitize_msg_content(msg, drop_local_images)

    if sanitized_count:
        print(
            '[Memory Sanitize] sanitized '
            f'{sanitized_count} stale or local image reference(s)'
        )

    return sanitized_count


async def _count_prompt_tokens(agent) -> int:
    token_counter = getattr(agent.formatter, 'token_counter', None)
    if token_counter is None:
        return 0

    prompt = await agent.formatter._format(
        [
            Msg('system', agent.sys_prompt, 'system'),
            *await agent.memory.get_memory(),
        ],
    )
    return await token_counter.count(prompt, tools=agent.toolkit.get_json_schemas())


def _sanitize_log_filename(value: str) -> str:
    normalized = re.sub(r'[^a-zA-Z0-9._-]+', '-', value).strip('-')
    return normalized or 'unknown'


async def _write_formatted_prompt_log(agent, user_msg: Msg) -> None:
    _sanitize_agent_memory(agent, drop_local_images=True)
    formatted_messages = await agent.formatter._format(
        [
            Msg('system', agent.sys_prompt, 'system'),
            *await agent.memory.get_memory(),
            user_msg,
        ],
    )
    formatted_prompt = {
        'messages': formatted_messages,
        'tools': agent.toolkit.get_json_schemas(),
    }

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    thread_id = _sanitize_log_filename(_current_thread_id() or 'no-thread')
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    log_path = LOGS_DIR / f'prompt-{thread_id}-{timestamp}.json'
    log_path.write_text(
        json.dumps(formatted_prompt, ensure_ascii=False, indent=2, default=str),
        encoding='utf-8',
    )
    print(f'[Prompt Log] wrote formatted prompt to {log_path}')


def _find_trim_boundary(memory_items) -> int:
    pending_tool_calls = set()
    fallback_boundary = 0

    for index, (msg, _) in enumerate(memory_items):
        for block in msg.get_content_blocks('tool_use'):
            pending_tool_calls.add(block['id'])
        for block in msg.get_content_blocks('tool_result'):
            pending_tool_calls.discard(block['id'])

        if pending_tool_calls:
            continue

        fallback_boundary = index + 1
        next_msg = memory_items[index + 1][0] if index + 1 < len(memory_items) else None
        if msg.role == 'assistant':
            return index + 1
        if next_msg is not None and next_msg.role == 'user':
            return index + 1

    return fallback_boundary or len(memory_items)


async def _trim_agent_memory(agent) -> None:
    memory = getattr(agent, 'memory', None)
    if memory is None or not hasattr(memory, 'content'):
        return

    _sanitize_agent_memory(agent, drop_local_images=True)

    while memory.content:
        token_count = await _count_prompt_tokens(agent)
        if token_count <= MAX_CONTEXT_TOKENS:
            return

        boundary = _find_trim_boundary(memory.content)
        if boundary <= 0:
            return
        memory.content = memory.content[boundary:]


async def _persist_agent_state(agent) -> None:
    thread_id = _current_thread_id()
    if not thread_id:
        return

    _sanitize_agent_memory(agent, drop_local_images=True)
    await _trim_agent_memory(agent)
    await asyncio.to_thread(save_agent_state, thread_id, agent.state_dict())


async def _restore_agent_from_steps(agent, thread: ThreadDict) -> None:
    steps = [step for step in thread.get('steps', []) if step.get('createdAt')]
    steps.sort(key=lambda step: step.get('createdAt', ''))

    for step in steps:
        output = step.get('output') or ''
        if not output:
            continue

        if step.get('type') == 'user_message':
            await agent.memory.add(
                Msg(
                    name='user',
                    content=_restore_user_content(output, step.get('command')),
                    role='user',
                )
            )
        elif step.get('type') == 'assistant_message':
            await agent.memory.add(
                Msg(name='assistant', content=output, role='assistant')
            )

    _sanitize_agent_memory(agent, drop_local_images=True)
    await _trim_agent_memory(agent)


async def _build_agent_for_thread(thread_id: Optional[str], thread: Optional[ThreadDict] = None):
    agent = build_agent()
    if not thread_id:
        return agent

    state = await asyncio.to_thread(load_agent_state, thread_id)
    if state:
        try:
            agent.load_state_dict(state, strict=False)
            _sanitize_agent_memory(agent, drop_local_images=True)
            await _trim_agent_memory(agent)
            return agent
        except Exception as exc:
            print(f'Failed to restore serialized agent state for {thread_id}: {exc}')

    if thread is not None:
        await _restore_agent_from_steps(agent, thread)

    return agent


def _extract_response_parts(content_data: Any) -> tuple[str, str]:
    thinking_parts: list[str] = []
    text_parts: list[str] = []

    if isinstance(content_data, list):
        for block in content_data:
            if not isinstance(block, dict):
                continue
            if block.get('type') == 'thinking':
                thinking_parts.append(block.get('thinking', ''))
            elif block.get('type') == 'text':
                text_parts.append(block.get('text', ''))
    elif isinstance(content_data, str):
        text_parts.append(content_data)
    elif content_data is not None:
        text_parts.append(str(content_data))

    thinking_text = '\n'.join(part for part in thinking_parts if part).strip()
    final_text = ''.join(part for part in text_parts if part).strip()
    return thinking_text, final_text


def _has_tool_use_blocks(content_data: Any) -> bool:
    if not isinstance(content_data, list):
        return False

    return any(
        isinstance(block, dict) and block.get('type') == 'tool_use'
        for block in content_data
    )


def _compute_stream_update(previous_text: str, current_text: str) -> tuple[str, bool]:
    if current_text == previous_text:
        return '', False

    if current_text.startswith(previous_text):
        return current_text[len(previous_text) :], False

    return current_text, True


def _extract_generated_images(final_text: str) -> tuple[list[cl.Image], str]:
    image_elements = []
    for image_path in GEN_IMAGE_PATTERN.findall(final_text):
        if os.path.exists(image_path):
            image_elements.append(
                cl.Image(path=image_path, name='生成的图片', display='inline')
            )

    display_text = GEN_IMAGE_PATTERN.sub('', final_text).strip()
    if not display_text and image_elements:
        display_text = '图片已生成，请查看下方结果：'

    return image_elements, display_text


def _is_canvas_route_path(path: str) -> bool:
    return path == '/canvas' or path.startswith('/api/canvas')


chainlit_app.router.routes = [
    route
    for route in chainlit_app.router.routes
    if not _is_canvas_route_path(getattr(route, 'path', ''))
]


@chainlit_app.get('/canvas')
async def canvas_page():
    if not CANVAS_HTML_PATH.exists():
        raise HTTPException(status_code=404, detail='Canvas page is not available.')
    content = CANVAS_HTML_PATH.read_bytes()
    return Response(
        content=content,
        media_type='text/html; charset=utf-8',
        headers={
            'Content-Length': str(len(content)),
            'Connection': 'close',
        },
    )



@chainlit_app.get('/api/canvas/skills')
async def canvas_list_skills():
    return {'skills': _canvas_skill_payload()}


@chainlit_app.get('/api/canvas/documents')
async def canvas_list_documents():
    return {'documents': list_documents()}


@chainlit_app.post('/api/canvas/documents')
async def canvas_create_document(request: Request):
    body = await _read_json_body(request)
    title = str(body.get('title') or 'Untitled Paper')
    if isinstance(body.get('document'), dict):
        document = normalize_document(body['document'])
    elif body.get('content'):
        document = markdown_to_canvas_document(str(body['content']), title)
    else:
        document = create_document(title)
    return create_document_record(document, source_type='manual')


@chainlit_app.post('/api/canvas/import')
async def canvas_import_document(file: UploadFile = File(...)):
    filename = file.filename or 'document'
    suffix = Path(filename).suffix.casefold()
    payload = await file.read()
    try:
        if suffix == '.tex':
            document = parse_latex_document(_decode_text_upload(payload), filename)
            return create_document_record(document, source_type='latex', source_filename=filename)
        if suffix == '.docx':
            document, assets = parse_docx_document(payload, filename)
            return create_document_record(
                document,
                source_type='docx',
                source_filename=filename,
                assets=assets,
            )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f'导入失败：{exc}') from exc
    raise HTTPException(status_code=400, detail='仅支持 .tex 和 .docx 文件。')


@chainlit_app.get('/api/canvas/documents/{document_id}')
async def canvas_get_document(document_id: str):
    try:
        return get_document_record(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@chainlit_app.put('/api/canvas/documents/{document_id}')
async def canvas_save_document(document_id: str, request: Request):
    body = await _read_json_body(request)
    if not isinstance(body.get('document'), dict):
        raise HTTPException(status_code=400, detail='Missing Canvas document payload.')
    try:
        return save_document_record(
            document_id,
            body['document'],
            source=str(body.get('source') or 'manual_save'),
            instruction=body.get('instruction'),
            block_id=body.get('block_id'),
            before_json=body.get('before_json'),
            after_json=body.get('after_json'),
            metadata=body.get('metadata') if isinstance(body.get('metadata'), dict) else None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc



@chainlit_app.delete('/api/canvas/documents/{document_id}')
async def canvas_delete_document(document_id: str):
    try:
        return delete_document_record(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@chainlit_app.get('/api/canvas/documents/{document_id}/versions')
async def canvas_get_versions(document_id: str):
    return {'versions': list_versions(document_id)}


@chainlit_app.post('/api/canvas/documents/{document_id}/restore-previous')
async def canvas_restore_previous(document_id: str):
    try:
        return restore_previous_version(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@chainlit_app.post('/api/canvas/documents/{document_id}/versions/{version_id}/restore')
async def canvas_restore_version(document_id: str, version_id: str):
    try:
        return restore_version(document_id, version_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc



@chainlit_app.get('/api/canvas/documents/{document_id}/chat')
async def canvas_get_chat(document_id: str, request: Request):
    try:
        thread_id = _canvas_thread_from_request(request)
        conversation = get_or_create_conversation(document_id, thread_id)
        return {
            'conversation': conversation,
            'messages': list_canvas_messages(document_id, thread_id),
            'skills': _canvas_skill_payload(),
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc



@chainlit_app.post('/api/canvas/documents/{document_id}/chat/stream')
async def canvas_stream_chat(document_id: str, request: Request):
    body = await _read_json_body(request)
    raw_message = str(body.get('message') or '').strip()
    command = str(body.get('command') or '').strip() or None
    block_id = body.get('block_id')
    selected_text = str(body.get('selected_text') or '')
    selected_block_ids = [
        str(item)
        for item in body.get('selected_block_ids') or []
        if item
    ]
    if not raw_message and not command:
        raise HTTPException(status_code=400, detail='请输入要发送给 Canvas Agent 的内容。')

    thread_id = _canvas_thread_from_request(request)
    selection = {
        'block_id': block_id,
        'selected_block_ids': selected_block_ids,
        'selected_text': selected_text,
    }
    try:
        record = get_document_record(document_id)
        conversation = get_or_create_conversation(document_id, thread_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    user_message = append_canvas_message(
        document_id,
        'user',
        raw_message or f'/{command}',
        conversation_id=conversation['id'],
        command=command,
        selection=selection,
    )
    error_message, prepared_content = _build_user_content(raw_message, [], command)

    async def event_stream():
        yield _sse_event(
            'start',
            {
                'conversation': conversation,
                'user_message': user_message,
            },
        )
        if error_message:
            result = {'reply': error_message, 'changes': [], 'raw_response': error_message}
            assistant_message = append_canvas_message(
                document_id,
                'assistant',
                error_message,
                conversation_id=conversation['id'],
                response=result,
            )
            yield _sse_event(
                'final',
                {
                    'conversation': conversation,
                    'user_message': user_message,
                    'assistant_message': assistant_message,
                    'messages': list_canvas_messages(document_id, thread_id),
                    **result,
                },
            )
            yield _sse_event('done', {})
            return

        recent_messages = list_canvas_messages(document_id, thread_id)
        agent = _get_canvas_agent(request)
        try:
            async with _agent_lock(agent):
                async for event_text in _stream_canvas_chat_with_shared_agent(
                    agent,
                    record['document'],
                    str(block_id) if block_id else None,
                    selected_text,
                    prepared_content or raw_message,
                    recent_messages,
                    selected_block_ids,
                ):
                    if event_text.startswith('event: final\n'):
                        payload_text = event_text.split('data: ', 1)[1].strip()
                        result = json.loads(payload_text)
                        assistant_message = append_canvas_message(
                            document_id,
                            'assistant',
                            str(result.get('reply') or ''),
                            conversation_id=conversation['id'],
                            response=result,
                        )
                        yield _sse_event(
                            'final',
                            {
                                'conversation': conversation,
                                'user_message': user_message,
                                'assistant_message': assistant_message,
                                'messages': list_canvas_messages(document_id, thread_id),
                                **result,
                            },
                        )
                    else:
                        yield event_text
            yield _sse_event('done', {})
        except Exception as exc:
            error_text = f'Canvas Agent 调用失败：{exc}'
            result = {'reply': error_text, 'changes': [], 'raw_response': error_text}
            assistant_message = append_canvas_message(
                document_id,
                'assistant',
                error_text,
                conversation_id=conversation['id'],
                response=result,
            )
            yield _sse_event(
                'error',
                {
                    'message': error_text,
                    'assistant_message': assistant_message,
                    'messages': list_canvas_messages(document_id, thread_id),
                },
            )

    return StreamingResponse(
        event_stream(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        },
    )


@chainlit_app.post('/api/canvas/documents/{document_id}/chat')
async def canvas_post_chat(document_id: str, request: Request):
    body = await _read_json_body(request)
    raw_message = str(body.get('message') or '').strip()
    command = str(body.get('command') or '').strip() or None
    block_id = body.get('block_id')
    selected_text = str(body.get('selected_text') or '')
    selected_block_ids = [
        str(item)
        for item in body.get('selected_block_ids') or []
        if item
    ]
    if not raw_message and not command:
        raise HTTPException(status_code=400, detail='请输入要发送给 Canvas Agent 的内容。')

    thread_id = _canvas_thread_from_request(request)
    selection = {
        'block_id': block_id,
        'selected_block_ids': selected_block_ids,
        'selected_text': selected_text,
    }
    try:
        record = get_document_record(document_id)
        conversation = get_or_create_conversation(document_id, thread_id)
        user_message = append_canvas_message(
            document_id,
            'user',
            raw_message or f'/{command}',
            conversation_id=conversation['id'],
            command=command,
            selection=selection,
        )
        error_message, prepared_content = _build_user_content(raw_message, [], command)
        if error_message:
            result = {'reply': error_message, 'changes': [], 'raw_response': error_message}
            assistant_message = append_canvas_message(
                document_id,
                'assistant',
                error_message,
                conversation_id=conversation['id'],
                response=result,
            )
            return {
                'conversation': conversation,
                'user_message': user_message,
                'assistant_message': assistant_message,
                'messages': list_canvas_messages(document_id, thread_id),
                **result,
            }

        recent_messages = list_canvas_messages(document_id, thread_id)
        agent = _get_canvas_agent(request)
        async with _agent_lock(agent):
            result = await _run_canvas_chat_with_shared_agent(
                agent,
                record['document'],
                str(block_id) if block_id else None,
                selected_text,
                prepared_content or raw_message,
                recent_messages,
                selected_block_ids,
            )
        assistant_message = append_canvas_message(
            document_id,
            'assistant',
            str(result.get('reply') or ''),
            conversation_id=conversation['id'],
            response=result,
        )
        return {
            'conversation': conversation,
            'user_message': user_message,
            'assistant_message': assistant_message,
            'messages': list_canvas_messages(document_id, thread_id),
            **result,
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'Canvas Agent 调用失败：{exc}') from exc



@chainlit_app.put('/api/canvas/documents/{document_id}/chat/messages/{message_id}/response')
async def canvas_update_chat_message_response(document_id: str, message_id: str, request: Request):
    body = await _read_json_body(request)
    response = body.get('response')
    if not isinstance(response, dict):
        raise HTTPException(status_code=400, detail='Missing response payload.')
    try:
        return update_canvas_message_response(document_id, message_id, response)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@chainlit_app.post('/api/canvas/documents/{document_id}/ai-edit')
async def canvas_ai_edit(document_id: str, request: Request):
    body = await _read_json_body(request)
    try:
        record = get_document_record(document_id)
        agent = _get_canvas_agent(request)
        async with _agent_lock(agent):
            return await _run_canvas_edit_with_shared_agent(
                agent,
                record['document'],
                body.get('block_id'),
                str(body.get('selected_text') or ''),
                str(body.get('instruction') or ''),
                str(body.get('mode') or 'polish'),
            )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f'AI 修改失败：{exc}') from exc


@chainlit_app.get('/api/canvas/assets/{asset_id}')
async def canvas_get_asset(asset_id: str):
    try:
        asset = get_asset(asset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    headers = {'Content-Disposition': f'inline; filename="{asset["filename"]}"'}
    return Response(content=asset['content'], media_type=asset['mime_type'], headers=headers)


@chainlit_app.get('/api/canvas/documents/{document_id}/export/{export_type}')
async def canvas_export_document(document_id: str, export_type: str):
    try:
        record = get_document_record(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    safe_title = _safe_download_name(record['title'])
    if export_type == 'tex':
        content = export_latex(record['document']).encode('utf-8')
        headers = {'Content-Disposition': f'attachment; filename="{safe_title}.tex"'}
        return Response(content=content, media_type='application/x-tex', headers=headers)
    if export_type == 'docx':
        content = export_docx(record['document'])
        headers = {'Content-Disposition': f'attachment; filename="{safe_title}.docx"'}
        return Response(
            content=content,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers=headers,
        )
    raise HTTPException(status_code=400, detail='导出格式仅支持 tex 或 docx。')


async def _read_json_body(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _decode_text_upload(payload: bytes) -> str:
    for encoding in ('utf-8-sig', 'utf-8', 'gb18030', 'latin-1'):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode('utf-8', errors='replace')


def _safe_download_name(title: str) -> str:
    normalized = re.sub(r'[^a-zA-Z0-9._-]+', '-', title).strip('-')
    return normalized[:80] or 'canvas-document'


def _prioritize_canvas_routes() -> None:
    canvas_routes = []
    other_routes = []
    for route in chainlit_app.router.routes:
        path = getattr(route, 'path', '')
        if _is_canvas_route_path(path):
            canvas_routes.append(route)
        else:
            other_routes.append(route)
    chainlit_app.router.routes = canvas_routes + other_routes


_prioritize_canvas_routes()


@cl.action_callback('open_canvas')
async def open_canvas_action(action: cl.Action):
    thread_id = _current_thread_id() or LAST_ACTIVE_THREAD_ID or ''
    await cl.Message(content=f'[打开 Canvas]({_canvas_url(thread=thread_id)})').send()


@cl.action_callback('send_to_canvas')
async def send_to_canvas_action(action: cl.Action):
    payload = action.payload or {}
    content = str(payload.get('content') or '').strip()
    if not content:
        await cl.Message(content='没有可发送到 Canvas 的正文内容。').send()
        return
    document = markdown_to_canvas_document(content)
    record = create_document_record(document, source_type='chat_message')
    thread_id = _current_thread_id() or LAST_ACTIVE_THREAD_ID or ''
    await cl.Message(
        content=f'已发送到 Canvas：[{record["title"]}]({_canvas_url(doc=record["id"], thread=thread_id)})'
    ).send()


async def _stream_agent_reply(agent, user_msg: Msg) -> tuple[Msg, Optional[cl.Message]]:
    response_holder: dict[str, Msg] = {}
    stream_state_by_id: dict[str, dict[str, Any]] = {}
    draft_replies: dict[str, cl.Message] = {}
    saw_thinking = False

    queue_enabled = not getattr(agent, '_disable_msg_queue', True)
    previous_queue = getattr(agent, 'msg_queue', None)
    console_enabled = not getattr(agent, '_disable_console_output', False)

    async def _invoke_agent() -> None:
        response_holder['response'] = await agent(user_msg)

    step = cl.Step(
        name='🤔 思考过程',
        type='llm',
        default_open=True,
        auto_collapse=True,
    )

    agent.set_console_output_enabled(False)
    try:
        async with step:
            async for printed_msg, _ in stream_printing_messages(
                [agent],
                _invoke_agent(),
            ):
                msg_id = getattr(printed_msg, 'id', None) or f'stream-{len(stream_state_by_id)}'
                state = stream_state_by_id.setdefault(
                    msg_id,
                    {
                        'thinking': '',
                        'text': '',
                        'tool_use_seen': False,
                    },
                )

                thinking_text, text_text = _extract_response_parts(printed_msg.content)

                if thinking_text:
                    thinking_update, replace_thinking = _compute_stream_update(
                        state['thinking'],
                        thinking_text,
                    )
                    if thinking_update or replace_thinking:
                        await step.stream_token(
                            thinking_text if replace_thinking else thinking_update,
                            is_sequence=replace_thinking,
                        )
                    state['thinking'] = thinking_text
                    saw_thinking = True

                has_tool_use = _has_tool_use_blocks(printed_msg.content)
                if has_tool_use:
                    state['tool_use_seen'] = True
                    draft_reply = draft_replies.pop(msg_id, None)
                    if draft_reply is not None:
                        await draft_reply.remove()

                if text_text and not state['tool_use_seen']:
                    draft_reply = draft_replies.get(msg_id)
                    if draft_reply is None:
                        draft_reply = await cl.Message(content='').send()
                        draft_replies[msg_id] = draft_reply

                    text_update, replace_text = _compute_stream_update(
                        state['text'],
                        text_text,
                    )
                    if text_update or replace_text:
                        await draft_reply.stream_token(
                            text_text if replace_text else text_update,
                            is_sequence=replace_text,
                        )
                    state['text'] = text_text
    finally:
        if queue_enabled:
            agent.set_msg_queue_enabled(True, previous_queue)
        else:
            agent.set_msg_queue_enabled(False)
        agent.set_console_output_enabled(console_enabled)

    if not saw_thinking:
        await step.remove()

    response = response_holder.get('response')
    if response is None:
        raise RuntimeError('Agent finished without producing a response.')

    final_reply = None
    final_reply_id = getattr(response, 'id', None)
    if final_reply_id:
        final_reply = draft_replies.pop(final_reply_id, None)

    for stale_reply in draft_replies.values():
        await stale_reply.remove()

    return response, final_reply


@cl.on_chat_start
async def on_chat_start():
    await _set_skill_commands()
    agent = build_agent()
    cl.user_session.set('agent', agent)
    _register_active_agent(agent, _current_thread_id())
    await _persist_agent_state(agent)
    await cl.Message(
        content='你好！我是 **论论**，你的智能助手。很高兴为你服务！',
        actions=[
            cl.Action(
                name='open_canvas',
                payload={},
                label='打开 Canvas',
                icon='file-text',
            )
        ],
    ).send()


@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):

    await _set_skill_commands()
    thread_id = thread.get('id')
    agent = await _build_agent_for_thread(thread_id, thread)
    cl.user_session.set('agent', agent)
    _register_active_agent(agent, thread_id)
    await _persist_agent_state(agent)


@cl.on_message
async def on_message(message: cl.Message):
    agent = cl.user_session.get('agent')
    if agent is None:
        agent = await _build_agent_for_thread(_current_thread_id())
        cl.user_session.set('agent', agent)

    _register_active_agent(agent, _current_thread_id())
    _sanitize_agent_memory(agent, drop_local_images=True)
    await _trim_agent_memory(agent)

    image_paths = _collect_image_paths(message)
    error_message, user_content = _build_user_content(
        message.content or '',
        image_paths,
        getattr(message, 'command', None),
    )
    if error_message:
        await cl.Message(content=error_message).send()
        return

    user_msg = Msg(
        name='user',
        content=_build_user_msg_content(user_content or '', image_paths),
        role='user',
    )

    async with _agent_lock(agent):
        await _write_formatted_prompt_log(agent, user_msg)
        response, streamed_reply = await _stream_agent_reply(agent, user_msg)
        _, final_text = _extract_response_parts(response.content)

        if not final_text:
            final_text = '（由于某些原因，没有生成正文内容）'

        await _trim_agent_memory(agent)
        await _persist_agent_state(agent)

    image_elements, display_text = _extract_generated_images(final_text)
    reply = streamed_reply or await cl.Message(content='').send()
    if streamed_reply is None:
        for index in range(0, len(display_text), 6):
            await reply.stream_token(display_text[index:index + 6])
            await asyncio.sleep(0.02)
    reply.content = display_text
    reply.elements = image_elements
    reply.actions = [
        cl.Action(
            name='send_to_canvas',
            payload={'content': display_text},
            label='发送到 Canvas',
            icon='panel-top-open',
        ),
        cl.Action(
            name='open_canvas',
            payload={},
            label='打开 Canvas',
            icon='file-text',
        ),
    ]
    await reply.update()
