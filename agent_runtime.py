from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from agentscope._logging import logger
from agentscope.agent import ReActAgent
from agentscope.formatter import DashScopeChatFormatter
from agentscope.memory import InMemoryMemory, MemoryBase
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel
from agentscope.token import OpenAITokenCounter
from agentscope.tool import Toolkit

from tools.file_tools import list_directory, read_file, read_text_file, write_text_file
from tools.python_tools import execute_python_code
from tools.skill_tools import install_project_skill

load_dotenv()

MEMORY_DIR_NAME = "memory"
MEMORY_FILE_NAME = "MEMORY.md"
DEFAULT_CONTEXT_COMPRESSION_TOKENS = 600_000
DEFAULT_KEEP_RECENT_MESSAGES = 12
DEFAULT_MEMORY_TEMPLATE = """# MEMORY

## User Preferences
- 暂无

## Project Facts
- 暂无

## Active Goals
- 暂无

## Constraints
- 暂无

## Important Decisions
- 暂无
"""


class MemoryFileSchema(BaseModel):
    """Structured schema used to maintain memory/MEMORY.md."""

    user_preferences: list[str] = Field(
        default_factory=list,
        description="Stable user preferences or writing style preferences.",
    )
    project_facts: list[str] = Field(
        default_factory=list,
        description="Durable project facts, architecture facts, or key files.",
    )
    active_goals: list[str] = Field(
        default_factory=list,
        description="Current long-running goals that may continue in future turns.",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Persistent constraints, environment limitations, or rules.",
    )
    important_decisions: list[str] = Field(
        default_factory=list,
        description="Important decisions already made that future turns should remember.",
    )


def _dedupe_points(items: list[str], limit: int = 6) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for raw in items:
        point = " ".join(raw.split()).strip(" -")
        if not point:
            continue

        lowered = point.lower()
        if lowered in seen:
            continue

        seen.add(lowered)
        cleaned.append(point[:160])
        if len(cleaned) >= limit:
            break

    return cleaned


def _render_memory_section(title: str, items: list[str]) -> str:
    points = _dedupe_points(items)
    rendered_points = points or ["暂无"]
    return "\n".join([f"## {title}", *[f"- {point}" for point in rendered_points]])


def render_memory_markdown(schema: MemoryFileSchema) -> str:
    """Render structured memory into the canonical MEMORY.md format."""
    sections = [
        "# MEMORY",
        "",
        _render_memory_section("User Preferences", schema.user_preferences),
        "",
        _render_memory_section("Project Facts", schema.project_facts),
        "",
        _render_memory_section("Active Goals", schema.active_goals),
        "",
        _render_memory_section("Constraints", schema.constraints),
        "",
        _render_memory_section("Important Decisions", schema.important_decisions),
        "",
    ]
    return "\n".join(sections).strip() + "\n"


def ensure_memory_file(workspace_root: str) -> Path:
    """Ensure the long-term memory file exists and has a usable template."""
    memory_dir = Path(workspace_root).resolve() / MEMORY_DIR_NAME
    memory_dir.mkdir(parents=True, exist_ok=True)
    memory_file = memory_dir / MEMORY_FILE_NAME

    if not memory_file.exists() or not memory_file.read_text(encoding="utf-8").strip():
        memory_file.write_text(DEFAULT_MEMORY_TEMPLATE, encoding="utf-8")

    return memory_file


def load_memory_markdown(memory_file: Path) -> str:
    """Read the long-term memory file as markdown."""
    content = memory_file.read_text(encoding="utf-8").strip()
    return content or DEFAULT_MEMORY_TEMPLATE


def _clean_skill_value(raw: str) -> str:
    return raw.strip().strip('"').strip("'")


def read_skill_summary(skill_file: Path) -> tuple[str, str]:
    """Read a local skill name and a short description for prompt routing."""
    skill_name = skill_file.parent.name
    description = ""

    try:
        lines = skill_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return skill_name, ""

    body_start = 0
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], start=1):
            stripped = line.strip()
            if stripped == "---":
                body_start = index + 1
                break
            if stripped.startswith("name:"):
                value = _clean_skill_value(stripped.split(":", 1)[1])
                if value:
                    skill_name = value
            elif stripped.startswith("description:"):
                value = _clean_skill_value(stripped.split(":", 1)[1])
                if value:
                    description = value

    if not description:
        for line in lines[body_start:]:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            description = stripped
            break

    description = " ".join(description.split())
    return skill_name, description[:180]


def build_workspace_overview(workspace_root: str) -> str:
    """构建一个简短的工作区摘要，提前告诉模型有哪些目录和 skills。"""
    root = Path(workspace_root).resolve()
    top_level_entries = []
    for entry in sorted(root.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
        if entry.name.startswith("."):
            continue
        suffix = "/" if entry.is_dir() else ""
        top_level_entries.append(f"- {entry.name}{suffix}")

    skill_entries = []
    skills_dir = root / "skills"
    if skills_dir.exists():
        for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
            skill_name, description = read_skill_summary(skill_file)
            if description:
                skill_entries.append(f"- {skill_name}: {description}")
            else:
                skill_entries.append(f"- {skill_name}")

    lines = ["当前工作区摘要：", f"根目录: {root}", "顶层目录和文件："]
    lines.extend(top_level_entries or ["- （空）"])
    lines.append(f"可用 skills（{len(skill_entries)}）：")
    lines.extend(skill_entries or ["- （未发现）"])

    preferred_skills = [
        "paper-aesthetic-critic",
        "paper_review",
        "peer-review",
        "scientific-critical-thinking",
        "venue-templates",
        "literature-review",
        "citation-management",
        "scientific-writing",
    ]
    lines.append(
        "论文审美与投稿判断优先 skills: " + ", ".join(preferred_skills)
    )
    return "\n".join(lines)


def build_toolkit(workspace_root: str) -> Toolkit:
    """构建带工作区文件访问能力的工具集。"""
    toolkit = Toolkit()
    toolkit.register_tool_function(execute_python_code)
    toolkit.register_tool_function(
        list_directory,
        preset_kwargs={"workspace_root": workspace_root},
    )
    toolkit.register_tool_function(
        read_text_file,
        preset_kwargs={"workspace_root": workspace_root},
    )
    toolkit.register_tool_function(
        read_file,
        preset_kwargs={"workspace_root": workspace_root},
    )
    toolkit.register_tool_function(
        write_text_file,
        preset_kwargs={"workspace_root": workspace_root},
    )
    toolkit.register_tool_function(
        install_project_skill,
        preset_kwargs={"workspace_root": workspace_root},
    )
    return toolkit


def build_system_prompt(workspace_root: str) -> str:
    workspace_overview = build_workspace_overview(workspace_root)
    return f"""
你是一个名为 论论 的助手，你可以使用 skills 来完成复杂任务。
你拥有一组 agent skills 和一组 tools。
规则如下：
1. 先根据用户任务判断是否匹配某个 skill。
2. 当任务明显匹配某个 skill 时，先根据 skill 提示定位对应目录。
3. 使用 skill 前，必须认真阅读对应 skill 目录中的 SKILL.md。
4. skill 只负责指导流程，真正执行动作时调用 tools。
5. 如果没有合适的 skill，再直接使用通用推理和 tools。
6. 遇到本地代码、目录、文件类任务时，先调用 list_directory 查看目录结构，再调用 read_file 或 read_text_file 读取必要文件。
7. 不要臆测尚未读取的本地文件内容。
8. 输出时要明确说明你做了什么、调用了哪些工具、得到什么结果。
9. `memory/MEMORY.md` 是长期记忆文件。它只保留跨轮仍然重要的信息，例如用户偏好、稳定约束、项目事实、长期任务状态和重要决策。
10. 每次对话开始时，你都会看到 `memory/MEMORY.md` 的当前内容，应把它视为长期上下文的一部分。
11. 每次对话结束后，都要维护 `memory/MEMORY.md`：只保留最关键的信息，合并和去重已有内容，不记录思维链、不记录冗长工具输出、不记录短期噪声。
12. 更新 `memory/MEMORY.md` 时，优先重写为简洁的结构化摘要，而不是无限追加。
13. 多个 skill 同时适合时，先选一个主 skill，再按需组合其他 skills。
14. 当任务涉及论文审美、期刊或顶会风格、research taste、方案优劣判断、审稿、改写、图表叙事或投稿适配时，优先考虑 `paper-aesthetic-critic`、`paper_review`、`peer-review`、`scientific-critical-thinking`、`venue-templates`、`literature-review`、`citation-management`、`scientific-writing` 等 skills，并明确使用了哪些判断维度。
15. 如果 skill 中提到脚本、模板或参考文档，优先读取对应 skill 目录中的 `references/` 与 `scripts/`；必要时再使用 `execute_python_code` 调用本地 Python 脚本。
16. 当任务是为当前项目安装、更新或扩展 skill 时，优先使用 `project-skill-installer` skill 和 `install_project_skill` 工具，不要写入全局 `~/.codex/skills`。

{workspace_overview}
""".strip()


def build_memory_context(memory_file: Path) -> str:
    """Build the live memory section appended to the system prompt."""
    return (
        "当前长期记忆文件 `memory/MEMORY.md` 的内容如下：\n"
        "```md\n"
        f"{load_memory_markdown(memory_file)}\n"
        "```"
    )


def format_exchange_for_memory_update(
    msg: Msg | list[Msg] | None,
    reply_msg: Msg,
) -> str:
    """Format the latest exchange for MEMORY.md maintenance."""
    turns: list[Msg] = []
    if isinstance(msg, list):
        turns.extend(msg)
    elif isinstance(msg, Msg):
        turns.append(msg)

    turns.append(reply_msg)

    lines: list[str] = []
    for item in turns[-4:]:
        text = item.get_text_content() or ""
        text = text.strip()
        if not text:
            continue

        role_name = "用户" if item.role == "user" else "助手"
        lines.append(f"{role_name}: {text[:4000]}")

    return "\n\n".join(lines)


class WorkspaceReActAgent(ReActAgent):
    """ReActAgent with live MEMORY.md context and automatic memory maintenance."""

    def __init__(
        self,
        *,
        workspace_root: str,
        memory_file: Path,
        **kwargs: Any,
    ) -> None:
        self.workspace_root = str(Path(workspace_root).resolve())
        self.memory_file = memory_file.resolve()
        super().__init__(**kwargs)

    @property
    def sys_prompt(self) -> str:
        sections = [self._sys_prompt, build_memory_context(self.memory_file)]
        agent_skill_prompt = self.toolkit.get_agent_skill_prompt()
        if agent_skill_prompt:
            sections.append(agent_skill_prompt)
        return "\n\n".join(section for section in sections if section)

    async def reply(
        self,
        msg: Msg | list[Msg] | None = None,
        structured_model: type[BaseModel] | None = None,
    ) -> Msg:
        reply_msg = await super().reply(msg=msg, structured_model=structured_model)
        await self._maintain_memory_file(msg=msg, reply_msg=reply_msg)
        return reply_msg

    async def _maintain_memory_file(
        self,
        msg: Msg | list[Msg] | None,
        reply_msg: Msg,
    ) -> None:
        """Use the model to keep memory/MEMORY.md concise and durable."""
        try:
            current_memory = load_memory_markdown(self.memory_file)
            latest_exchange = format_exchange_for_memory_update(msg, reply_msg)

            if not latest_exchange.strip():
                return

            memory_prompt = await self.formatter.format(
                [
                    Msg(
                        "system",
                        (
                            "你负责维护 memory/MEMORY.md 这个长期记忆文件。\n"
                            "目标：把已有长期记忆与本轮新增对话合并，输出新的完整 MEMORY.md 结构化内容。\n"
                            "原则：\n"
                            "1. 只保留跨轮仍有价值的信息；\n"
                            "2. 忽略思维链、临时推理、完整日志和冗长工具输出；\n"
                            "3. 合并、去重、压缩已有信息；\n"
                            "4. 只有非常关键的信息才写入长期记忆；\n"
                            "5. 尽量简洁，每个要点一句话；\n"
                            "6. 返回结构化结果，不要附加解释。"
                        ),
                        "system",
                    ),
                    Msg(
                        "user",
                        (
                            "当前 MEMORY.md 内容如下：\n"
                            "```md\n"
                            f"{current_memory}\n"
                            "```\n\n"
                            "本轮新增对话如下：\n"
                            f"{latest_exchange}\n\n"
                            "请生成更新后的长期记忆。"
                        ),
                        "user",
                    ),
                ],
            )

            res = await self.model(
                memory_prompt,
                structured_model=MemoryFileSchema,
            )

            last_chunk = None
            if self.model.stream:
                async for chunk in res:
                    last_chunk = chunk
            else:
                last_chunk = res

            if not last_chunk or not last_chunk.metadata:
                logger.warning("Failed to update %s: model returned no metadata.", self.memory_file)
                return

            updated_memory = render_memory_markdown(
                MemoryFileSchema(**last_chunk.metadata),
            )
            if updated_memory != current_memory and updated_memory.strip():
                self.memory_file.write_text(updated_memory, encoding="utf-8")
        except Exception as exc:  # pragma: no cover - fallback path
            logger.warning("Failed to maintain %s: %s", self.memory_file, exc)


def create_agent(
    workspace_root: str | None = None,
    memory: MemoryBase | None = None,
) -> WorkspaceReActAgent:
    """创建一个带本地文件工具、长期记忆和上下文压缩的 ReActAgent。"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 DASHSCOPE_API_KEY，请先在 .env 中配置。")

    resolved_root = str(Path(workspace_root or os.getcwd()).resolve())
    memory_file = ensure_memory_file(resolved_root)

    model_name = os.getenv("DASHSCOPE_MODEL", "qwen3.5-plus")
    model = OpenAIChatModel(
        model_name=model_name,
        api_key=api_key,
        stream=True,
        client_kwargs={
            "base_url": os.getenv(
                "DASHSCOPE_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
        },
        generate_kwargs={
            "temperature": 0.1,
            "extra_body": {
                "enable_thinking": True,
            },
        },
    )

    formatter = DashScopeChatFormatter()
    compression_threshold = int(
        os.getenv(
            "CONTEXT_COMPRESSION_TOKENS",
            str(DEFAULT_CONTEXT_COMPRESSION_TOKENS),
        ),
    )
    keep_recent = int(
        os.getenv(
            "CONTEXT_COMPRESSION_KEEP_RECENT",
            str(DEFAULT_KEEP_RECENT_MESSAGES),
        ),
    )
    token_counter_model = os.getenv(
        "TOKEN_COUNTER_MODEL",
        model_name,
    )

    compression_config = ReActAgent.CompressionConfig(
        enable=True,
        agent_token_counter=OpenAITokenCounter(token_counter_model),
        trigger_threshold=compression_threshold,
        keep_recent=keep_recent,
        compression_prompt=(
            "<system-hint>"
            "请把较早的对话压缩成可持续工作的结构化摘要。"
            "保留用户目标、已完成工作、关键文件、稳定约束、重要结论和未完成事项。"
            "忽略思维链、冗长逐字输出和短期噪声。"
            "</system-hint>"
        ),
    )

    return WorkspaceReActAgent(
        workspace_root=resolved_root,
        memory_file=memory_file,
        name="论论",
        sys_prompt=build_system_prompt(resolved_root),
        model=model,
        formatter=formatter,
        toolkit=build_toolkit(resolved_root),
        memory=memory or InMemoryMemory(),
        compression_config=compression_config,
    )








