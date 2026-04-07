import os

from agentscope.tool import Toolkit, ToolResponse

from agent_app.skills.catalog import get_registered_skill, get_registered_skills


def _text_response(text: str) -> ToolResponse:
    return ToolResponse(content=[{'type': 'text', 'text': text}])


def _read_utf8_text_file(file_path: str) -> str:
    with open(file_path, 'r', encoding='utf-8') as file:
        return file.read()


def read_text_file(file_path: str) -> ToolResponse:
    """
    读取指定文本文件的内容。智能体可以使用此工具阅读 SKILL.md 等长文本文件。

    Args:
        file_path: 要读取的文本文件的绝对或相对路径。
    """
    if not os.path.exists(file_path):
        return _text_response(f'Error: 文件 {file_path} 不存在。')

    try:
        return _text_response(_read_utf8_text_file(file_path))
    except Exception as exc:
        return _text_response(f'Error: 读取文件失败 - {exc}')


def list_registered_skills() -> ToolResponse:
    """列出当前 Agent 已注册的本地 skills。"""
    skills = get_registered_skills()
    if not skills:
        return _text_response('当前没有已注册的 skill。')

    lines = ['当前已注册的 skills：']
    for skill in skills:
        lines.append(f'- {skill.name}: {skill.description}')
    return _text_response('\n'.join(lines))


def read_registered_skill(skill_name: str) -> ToolResponse:
    """
    按 skill 名称读取对应的 SKILL.md 内容，避免模型自行拼接本地路径。

    Args:
        skill_name: SKILL.md frontmatter 中的 name。
    """
    skill = get_registered_skill(skill_name)
    if skill is None:
        available = ', '.join(f'/{item.name}' for item in get_registered_skills()) or '无'
        return _text_response(
            f'Error: 未找到名为 {skill_name} 的已注册 skill。可用命令: {available}'
        )

    try:
        skill_text = _read_utf8_text_file(skill.skill_md_path)
    except Exception as exc:
        return _text_response(f'Error: 读取 skill 失败 - {exc}')

    return _text_response(
        '\n'.join(
            [
                f'# Skill Name: {skill.name}',
                f'# Skill Directory: {skill.skill_dir}',
                f'# SKILL.md Path: {skill.skill_md_path}',
                '',
                skill_text,
            ]
        )
    )


def register_file_tools(toolkit: Toolkit) -> None:
    """将文件相关工具注册到 Toolkit 中。"""
    toolkit.register_tool_function(read_text_file)
    toolkit.register_tool_function(list_registered_skills)
    toolkit.register_tool_function(read_registered_skill)
