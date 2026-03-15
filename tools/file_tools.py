from __future__ import annotations

from pathlib import Path

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse


def _resolve_workspace_path(path: str, workspace_root: str) -> Path:
    root = Path(workspace_root).resolve()
    candidate = Path(path)
    target = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()

    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"路径 {path} 不在工作区 {root} 内。") from exc

    return target


def _visible_entries(directory: Path, include_hidden: bool) -> list[Path]:
    entries = []
    for entry in sorted(directory.iterdir(), key=lambda item: (item.is_file(), item.name.lower())):
        if not include_hidden and entry.name.startswith("."):
            continue
        entries.append(entry)
    return entries


async def list_directory(
    path: str = ".",
    recursive: bool = False,
    max_depth: int = 2,
    include_hidden: bool = False,
    max_entries: int = 200,
    workspace_root: str = ".",
) -> ToolResponse:
    """列出工作区内的目录结构。

    Args:
        path (str):
            相对工作区的目录路径，默认是当前工作区根目录。
        recursive (bool):
            是否递归列出子目录。
        max_depth (int):
            递归展开的最大深度。仅在 recursive=True 时生效。
        include_hidden (bool):
            是否包含以 "." 开头的隐藏文件和目录。
        max_entries (int):
            最多返回多少个条目，防止上下文过长。
    """
    target = _resolve_workspace_path(path, workspace_root)

    if not target.exists():
        raise FileNotFoundError(f"路径不存在: {target}")
    if not target.is_dir():
        raise NotADirectoryError(f"路径不是目录: {target}")
    if max_depth < 1:
        raise ValueError("max_depth 必须大于等于 1。")
    if max_entries < 1:
        raise ValueError("max_entries 必须大于等于 1。")

    root = Path(workspace_root).resolve()
    depth_limit = max_depth if recursive else 1
    lines = [f"Workspace: {root}", f"Directory: {target}"]
    emitted = 0
    truncated = False

    def walk(current: Path, depth: int) -> None:
        nonlocal emitted, truncated

        for entry in _visible_entries(current, include_hidden):
            if emitted >= max_entries:
                truncated = True
                return

            indent = "  " * depth
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{indent}- {entry.name}{suffix}")
            emitted += 1

            if entry.is_dir() and recursive and depth + 1 < depth_limit:
                walk(entry, depth + 1)
                if truncated:
                    return

    walk(target, depth=0)

    if truncated:
        lines.append("... output truncated ...")

    return ToolResponse(content=[TextBlock(type="text", text="\n".join(lines))])


async def read_text_file(
    path: str,
    max_chars: int = 12000,
    workspace_root: str = ".",
) -> ToolResponse:
    """读取工作区内的文本文件内容。

    Args:
        path (str):
            相对工作区的文件路径。
        max_chars (int):
            最多返回多少字符，避免上下文过长。
    """
    target = _resolve_workspace_path(path, workspace_root)

    if not target.exists():
        raise FileNotFoundError(f"文件不存在: {target}")
    if not target.is_file():
        raise FileNotFoundError(f"路径不是文件: {target}")
    if max_chars < 1:
        raise ValueError("max_chars 必须大于等于 1。")

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"文件不是 UTF-8 文本文件: {target}") from exc

    if len(content) > max_chars:
        content = (
            f"{content[:max_chars]}\n\n"
            f"[文件内容已截断，原始长度 {len(content)} 字符，仅返回前 {max_chars} 字符]"
        )

    return ToolResponse(content=[TextBlock(type="text", text=content)])


async def read_file(
    path: str,
    max_chars: int = 12000,
    workspace_root: str = ".",
) -> ToolResponse:
    """读取工作区内的文本文件内容。

    Args:
        path (str):
            相对工作区的文件路径。
        max_chars (int):
            最多返回多少字符，避免上下文过长。
    """
    return await read_text_file(
        path=path,
        max_chars=max_chars,
        workspace_root=workspace_root,
    )


async def write_text_file(
    path: str,
    content: str,
    workspace_root: str = ".",
) -> ToolResponse:
    """写入工作区内的文本文件。

    Args:
        path (str):
            相对工作区的文件路径。
        content (str):
            要写入的文本内容。
    """
    target = _resolve_workspace_path(path, workspace_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    return ToolResponse(content=[TextBlock(type="text", text=f"已写入 {target}")])
