from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

GITHUB_ZIP_TIMEOUT = 60


def _safe_extract_zip(zip_file: zipfile.ZipFile, dest_dir: Path) -> None:
    dest_root = dest_dir.resolve()
    for info in zip_file.infolist():
        extracted_path = (dest_dir / info.filename).resolve()
        if extracted_path == dest_root or str(extracted_path).startswith(f"{dest_root}{os.sep}"):
            continue
        raise ValueError("压缩包包含目标目录外的路径，已拒绝安装。")
    zip_file.extractall(dest_dir)


def _download_repo_zip(owner: str, repo: str, ref: str, temp_dir: Path) -> Path:
    zip_url = f"https://codeload.github.com/{owner}/{repo}/zip/{ref}"
    req = urllib.request.Request(
        zip_url,
        headers={"User-Agent": "agentscope-project-skill-installer"},
    )
    zip_path = temp_dir / "repo.zip"
    with urllib.request.urlopen(req, timeout=GITHUB_ZIP_TIMEOUT) as response:
        zip_path.write_bytes(response.read())

    with zipfile.ZipFile(zip_path, "r") as zip_file:
        _safe_extract_zip(zip_file, temp_dir)
        top_levels = {name.split("/")[0] for name in zip_file.namelist() if name}

    if len(top_levels) != 1:
        raise ValueError("下载的 GitHub 压缩包结构异常。")

    return temp_dir / next(iter(top_levels))


def _validate_repo(repo: str) -> tuple[str, str]:
    parts = [part for part in repo.split("/") if part]
    if len(parts) != 2:
        raise ValueError("repo 必须是 owner/repo 形式，例如 openai/skills。")
    return parts[0], parts[1]


def _validate_relative_repo_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip("/")
    if not normalized:
        raise ValueError("skill_path 不能为空。")
    if normalized.startswith("../") or "/../" in normalized:
        raise ValueError("skill_path 必须是仓库内的相对路径。")
    return normalized


def _install_project_skill_sync(
    repo: str,
    skill_path: str,
    ref: str,
    replace_existing: bool,
    workspace_root: str,
) -> tuple[str, Path]:
    owner, repo_name = _validate_repo(repo)
    normalized_path = _validate_relative_repo_path(skill_path)
    workspace = Path(workspace_root).resolve()
    dest_root = workspace / "skills"
    dest_root.mkdir(parents=True, exist_ok=True)

    skill_name = Path(normalized_path).name
    dest_dir = dest_root / skill_name
    if dest_dir.exists():
        if not replace_existing:
            raise FileExistsError(f"技能已存在：{dest_dir}")
        shutil.rmtree(dest_dir)

    with tempfile.TemporaryDirectory(prefix="skill-install-") as temp_dir_raw:
        temp_dir = Path(temp_dir_raw)
        repo_root = _download_repo_zip(owner, repo_name, ref, temp_dir)
        skill_source = (repo_root / normalized_path).resolve()
        skill_md = skill_source / "SKILL.md"

        if not skill_source.is_dir() or not skill_md.is_file():
            raise FileNotFoundError(
                f"在 {repo}@{ref} 的 {normalized_path} 下未找到有效的 SKILL.md"
            )

        shutil.copytree(skill_source, dest_dir)

    return skill_name, dest_dir


async def install_project_skill(
    repo: str,
    skill_path: str,
    ref: str = "main",
    replace_existing: bool = False,
    workspace_root: str = ".",
) -> ToolResponse:
    """从 GitHub 安装一个技能到当前项目的 `skills/` 目录。

    该工具只安装到当前项目，不会写入全局 `~/.codex/skills`。

    Args:
        repo (str):
            GitHub 仓库，格式为 `owner/repo`。
        skill_path (str):
            技能在仓库中的相对路径，例如 `skills/.curated/pdf`。
        ref (str):
            Git 引用，默认 `main`。
        replace_existing (bool):
            若本地已存在同名技能，是否覆盖。
        workspace_root (str):
            当前项目根目录，由运行时预置。
    """

    try:
        skill_name, dest_dir = await asyncio.to_thread(
            _install_project_skill_sync,
            repo,
            skill_path,
            ref,
            replace_existing,
            workspace_root,
        )
        message = f"已安装技能 {skill_name} 到 {dest_dir}"
        metadata = {
            "installed": True,
            "skill_name": skill_name,
            "destination": str(dest_dir),
            "repo": repo,
            "skill_path": skill_path,
            "ref": ref,
        }
    except (ValueError, FileNotFoundError, FileExistsError, urllib.error.URLError) as exc:
        message = f"安装失败：{exc}"
        metadata = {
            "installed": False,
            "error": str(exc),
            "repo": repo,
            "skill_path": skill_path,
            "ref": ref,
        }

    return ToolResponse(
        content=[TextBlock(type="text", text=message)],
        metadata=metadata,
    )
