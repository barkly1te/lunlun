import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import chainlit as cl
from agentscope.message import Msg
from agentscope.pipeline import stream_printing_messages
from chainlit.context import context as chainlit_context
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.types import CommandDict, ThreadDict

from agent_app.agent_factory import MAX_CONTEXT_TOKENS, build_agent
from agent_app.skills.catalog import get_registered_skill, get_registered_skills
from database import init_sqlite_db, load_agent_state, save_agent_state

IMAGE_HINT_TEMPLATE = (
    '\n\n[系统提示：用户上传了图片。图片会作为原生多模态 image block 提供给你，同时'
    '系统也已缓存本地路径：{paths}。如果你需要调用 generate_image_tool 做改图，请'
    '从这些路径中提取合适的 image_path 参数。]'
)
GEN_IMAGE_PATTERN = re.compile(r'\[GEN_IMAGE:\s*(.*?)\]')
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

init_sqlite_db()


@cl.data_layer
def get_data_layer():
    return SQLAlchemyDataLayer(conninfo='sqlite+aiosqlite:///lunlun_history.db')


@cl.header_auth_callback
def header_auth_callback(headers) -> Optional[cl.User]:
    return cl.User(identifier='lunlun_internal_user', metadata={'role': 'admin'})


def _current_thread_id() -> Optional[str]:
    return getattr(chainlit_context.session, 'thread_id', None)


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


def _collect_image_paths(message: cl.Message) -> list[str]:
    image_paths = []
    for element in message.elements or []:
        mime = getattr(element, 'mime', '') or ''
        if 'image' in mime and getattr(element, 'path', None):
            image_paths.append(element.path)
    return image_paths


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

    await _trim_agent_memory(agent)


async def _build_agent_for_thread(thread_id: Optional[str], thread: Optional[ThreadDict] = None):
    agent = build_agent()
    if not thread_id:
        return agent

    state = await asyncio.to_thread(load_agent_state, thread_id)
    if state:
        try:
            agent.load_state_dict(state, strict=False)
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
    await _persist_agent_state(agent)
    await cl.Message(content='你好！我是 **论论**，你的智能助手。很高兴为你服务！').send()


@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):

    await _set_skill_commands()
    thread_id = thread.get('id')
    agent = await _build_agent_for_thread(thread_id, thread)
    cl.user_session.set('agent', agent)
    await _persist_agent_state(agent)


@cl.on_message
async def on_message(message: cl.Message):
    agent = cl.user_session.get('agent')
    if agent is None:
        agent = await _build_agent_for_thread(_current_thread_id())
        cl.user_session.set('agent', agent)

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
    await reply.update()
