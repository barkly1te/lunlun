from __future__ import annotations

import json
import re
from typing import Any

from agentscope.message import Msg

from .model import block_plain_text, selected_context

EDIT_MODE_LABELS = {
    'polish': '润色选区',
    'academic': '改成学术表达',
    'shorten': '缩短',
    'expand': '扩写',
    'continue': '续写',
    'explain': '解释选区',
    'title': '改标题',
    'abstract': '改摘要式表达',
    'translate_en': '翻译成英文',
    'transition': '补一个过渡句',
}


async def generate_edit_candidate(
    agent: Any,
    document: dict[str, Any],
    block_id: str | None,
    selected_text: str,
    instruction: str,
    mode: str = 'polish',
) -> dict[str, str]:
    context = selected_context(document, block_id, selected_text)
    target_text = selected_text.strip()
    if not target_text and context.get('current_block'):
        target_text = block_plain_text(context['current_block'])
    prompt = _build_prompt(context, target_text, instruction, mode)
    response = await agent(Msg(name='user', content=prompt, role='user'))
    response_text = _extract_text(response.content)
    parsed = _parse_candidate_json(response_text)
    replacement = str(parsed.get('replacement_text') or parsed.get('text') or '').strip()
    explanation = str(parsed.get('explanation') or parsed.get('reason') or '').strip()
    if not replacement:
        replacement = response_text.strip()
    return {
        'replacement_text': replacement,
        'explanation': explanation,
        'raw_response': response_text,
    }


async def generate_canvas_agent_reply(
    agent: Any,
    document: dict[str, Any],
    block_id: str | None,
    selected_text: str,
    user_content: str,
    recent_messages: list[dict[str, Any]] | None = None,
    selected_block_ids: list[str] | None = None,
) -> dict[str, Any]:
    prompt, context, target_text = prepare_canvas_agent_prompt(
        document,
        block_id,
        selected_text,
        user_content,
        recent_messages,
        selected_block_ids,
    )
    response = await agent(Msg(name='user', content=prompt, role='user'))
    response_text = _extract_text(response.content)
    return parse_canvas_agent_response(response_text, context, target_text)


def prepare_canvas_agent_prompt(
    document: dict[str, Any],
    block_id: str | None,
    selected_text: str,
    user_content: str,
    recent_messages: list[dict[str, Any]] | None = None,
    selected_block_ids: list[str] | None = None,
) -> tuple[str, dict[str, Any], str]:
    context = selected_context(document, block_id, selected_text)
    selected_ids = [str(block_id) for block_id in selected_block_ids or [] if block_id]
    selected_blocks = [
        block
        for block in document.get('blocks') or []
        if str(block.get('id') or '') in selected_ids
    ]
    if selected_blocks:
        context['selected_blocks'] = selected_blocks
    target_text = selected_text.strip()
    if not target_text and selected_blocks:
        target_text = '\n\n'.join(
            part for part in (block_plain_text(block) for block in selected_blocks) if part
        )
    if not target_text and context.get('current_block'):
        target_text = block_plain_text(context['current_block'])
    prompt = _build_chat_prompt(context, target_text, user_content, recent_messages or [])
    return prompt, context, target_text


def parse_canvas_agent_response(
    response_text: str,
    context: dict[str, Any],
    target_text: str,
) -> dict[str, Any]:
    parsed = _parse_candidate_json(response_text)
    reply = str(parsed.get('reply') or parsed.get('message') or parsed.get('explanation') or '').strip()
    changes = _normalize_changes(parsed.get('changes'), context, target_text)
    if not reply:
        reply = response_text.strip() if not changes else '已生成 Canvas 修改建议。'
    return {
        'reply': reply,
        'changes': changes,
        'raw_response': response_text,
    }


def _build_chat_prompt(
    context: dict[str, Any],
    target_text: str,
    user_content: str,
    recent_messages: list[dict[str, Any]],
) -> str:
    compact_context = {
        'document_title': context.get('title') or '',
        'outline': context.get('outline') or [],
        'section_heading': context.get('section_heading') or '',
        'section_excerpt': context.get('section_excerpt') or '',
        'current_block': context.get('current_block') or {},
        'selected_blocks': context.get('selected_blocks') or [],
        'neighbor_blocks': context.get('neighbor_blocks') or [],
    }
    compact_history = [
        {
            'role': message.get('role'),
            'content': str(message.get('content') or '')[:1800],
            'response': message.get('response') or {},
        }
        for message in recent_messages[-12:]
        if message.get('role') in {'user', 'assistant'}
    ]
    return (
        '你仍然是主聊天页的“论论”agent。本轮发生在 Canvas 论文工作台右侧的 Agent Chat 中。'
        '你必须继续遵守同一套系统提示词、tools 和本地 skills；如果用户通过 slash command 选择 skill，'
        '必须按主聊天页同样规则读取并遵循该 SKILL.md。\n'
        'Canvas 左侧是 source of truth，但不要默认改全文。用户说“这段/选中内容/当前块”时，'
        '指的是下面的 CURRENT_SELECTION、selected_blocks 或 current_block。若 selected_blocks 含多个 block，'
        '可以为多个 block 分别生成 changes。\n'
        '如果用户只是提问，请正常回答并让 changes 为空数组。'
        '如果用户要求修改 Canvas，请返回结构化修改建议，不要静默覆盖原文。\n\n'
        '返回格式必须是 JSON，不要 Markdown code fence：\n'
        '{"reply":"给用户看的简短回复", "changes":[{"block_id":"目标 block id", '
        '"before":"被替换的原文。若有选区，必须等于选区文本；若无选区，可为当前 block 主文本", '
        '"after":"修改后的替换文本", "reason":"修改理由"}]}\n\n'
        'Canvas 对话历史（仅用于延续右侧面板上下文）：\n'
        f'{json.dumps(compact_history, ensure_ascii=False, indent=2)}\n\n'
        'Canvas 文档上下文（只用于保持术语、结构和局部连贯性）：\n'
        f'{json.dumps(compact_context, ensure_ascii=False, indent=2)}\n\n'
        'CURRENT_SELECTION：\n'
        '<<<CANVAS_SELECTION\n'
        f'{target_text}\n'
        'CANVAS_SELECTION>>>\n\n'
        '用户本轮输入如下。注意其中可能已经包含主聊天页 slash skill 路由提示：\n'
        '<<<USER_MESSAGE\n'
        f'{user_content}\n'
        'USER_MESSAGE>>>'
    )


def _normalize_changes(
    raw_changes: Any,
    context: dict[str, Any],
    target_text: str,
) -> list[dict[str, str]]:
    if raw_changes is None:
        return []
    if isinstance(raw_changes, dict):
        raw_changes = [raw_changes]
    if not isinstance(raw_changes, list):
        return []

    current_block = context.get('current_block') or {}
    fallback_block_id = str(current_block.get('id') or '')
    fallback_before = target_text or block_plain_text(current_block)
    changes: list[dict[str, str]] = []
    for raw_change in raw_changes:
        if not isinstance(raw_change, dict):
            continue
        block_id = str(raw_change.get('block_id') or raw_change.get('id') or fallback_block_id).strip()
        before = str(raw_change.get('before') or raw_change.get('old_text') or fallback_before).strip()
        after = str(raw_change.get('after') or raw_change.get('new_text') or raw_change.get('replacement_text') or '').strip()
        reason = str(raw_change.get('reason') or raw_change.get('explanation') or '').strip()
        if not block_id or not after:
            continue
        changes.append(
            {
                'id': str(raw_change.get('id') or f'chg_{len(changes) + 1}'),
                'block_id': block_id,
                'before': before,
                'after': after,
                'reason': reason,
                'status': 'pending',
            }
        )
    return changes


def _build_prompt(
    context: dict[str, Any],
    target_text: str,
    instruction: str,
    mode: str,
) -> str:
    mode_label = EDIT_MODE_LABELS.get(mode, mode or '局部编辑')
    compact_context = {
        'document_title': context.get('title') or '',
        'outline': context.get('outline') or [],
        'section_heading': context.get('section_heading') or '',
        'section_excerpt': context.get('section_excerpt') or '',
        'neighbor_blocks': context.get('neighbor_blocks') or [],
    }
    return (
        '你仍然是主聊天页的“论论”agent，本轮是在 Canvas 论文工作台中处理局部编辑请求。'
        '继续遵守你的系统提示词、已注册 tools 和本地 skills；如确实需要，可以使用同一套工具/skill。'
        '只处理用户选中的内容或当前 block，不要改写全文，不要把未提供的上下文编造成事实。\n\n'
        f'编辑模式：{mode_label}\n'
        f'用户指令：{instruction or mode_label}\n\n'
        '可用上下文如下。它只用于保持术语、语气和局部连贯性：\n'
        f'{json.dumps(compact_context, ensure_ascii=False, indent=2)}\n\n'
        '待修改文本：\n'
        '<<<CANVAS_SELECTION\n'
        f'{target_text}\n'
        'CANVAS_SELECTION>>>\n\n'
        '请只返回 JSON，不要 Markdown code fence。格式：\n'
        '{"replacement_text": "候选修改文本", "explanation": "一句话说明修改意图"}'
    )


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    parts.append(str(item.get('text') or ''))
                elif 'content' in item:
                    parts.append(str(item.get('content') or ''))
        return ''.join(parts)
    return str(content or '')


def _parse_candidate_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith('```'):
        stripped = re.sub(r'^```(?:json)?\s*', '', stripped)
        stripped = re.sub(r'\s*```$', '', stripped)
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{.*\}', stripped, flags=re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}

