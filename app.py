import asyncio
import os
import re
from typing import Any, Optional

import chainlit as cl
from agentscope.message import Msg
from chainlit.context import context as chainlit_context
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.types import ThreadDict

from agent_app.agent_factory import MAX_CONTEXT_TOKENS, build_agent
from database import init_sqlite_db, load_agent_state, save_agent_state

IMAGE_HINT_TEMPLATE = (
    '\n\n[系统提示：用户上传了图片，系统已缓存至本地路径：{paths}。'
    '如果用户的需求涉及改图或生图，请提取此路径作为 image_path 参数调用 '
    'generate_image_tool 工具]'
)
GEN_IMAGE_PATTERN = re.compile(r'\[GEN_IMAGE:\s*(.*?)\]')

init_sqlite_db()


@cl.data_layer
def get_data_layer():
    return SQLAlchemyDataLayer(conninfo='sqlite+aiosqlite:///lunlun_history.db')


@cl.header_auth_callback
def header_auth_callback(headers) -> Optional[cl.User]:
    return cl.User(identifier='lunlun_internal_user', metadata={'role': 'admin'})


def _current_thread_id() -> Optional[str]:
    return getattr(chainlit_context.session, 'thread_id', None)


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
            await agent.memory.add(Msg(name='user', content=output, role='user'))
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


def _collect_user_content(message: cl.Message) -> str:
    content = message.content or ''
    image_paths = []

    for element in message.elements or []:
        mime = getattr(element, 'mime', '') or ''
        if 'image' in mime and getattr(element, 'path', None):
            image_paths.append(element.path)

    if image_paths:
        content += IMAGE_HINT_TEMPLATE.format(paths=', '.join(image_paths))

    return content


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


@cl.on_chat_start
async def on_chat_start():
    agent = build_agent()
    cl.user_session.set('agent', agent)
    await _persist_agent_state(agent)
    await cl.Message(content='你好！我是 **论论**，你的智能助手。很高兴为你服务！').send()


@cl.on_chat_resume
async def on_chat_resume(thread: ThreadDict):
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

    user_msg = Msg(name='user', content=_collect_user_content(message), role='user')

    async with cl.Step(name='🤔 论论正在思考中...') as step:
        response = await agent(user_msg)
        thinking_text, final_text = _extract_response_parts(response.content)

        if thinking_text:
            step.name = '🤔 论论的思考过程'
            formatted_think = f'> _{thinking_text}_'
            for index in range(0, len(formatted_think), 6):
                await step.stream_token(formatted_think[index:index + 6])
                await asyncio.sleep(0.01)
        else:
            step.name = '🤔 思考完毕'
            step.content = '_无内部思考过程。_'
            await step.update()

    if not final_text:
        final_text = '（由于某些原因，没有生成正文内容）'

    await _trim_agent_memory(agent)
    await _persist_agent_state(agent)

    image_elements, display_text = _extract_generated_images(final_text)
    reply = cl.Message(content='', elements=image_elements)
    for index in range(0, len(display_text), 6):
        await reply.stream_token(display_text[index:index + 6])
        await asyncio.sleep(0.02)
    await reply.send()
