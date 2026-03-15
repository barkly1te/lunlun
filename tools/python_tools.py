from __future__ import annotations

import ast
import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path
from textwrap import dedent
from typing import Any
from uuid import uuid4

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse

MAX_OUTPUT_CHARS = 20000
MAX_CODE_CHARS = 40000
FORBIDDEN_IMPORTS = {
    "subprocess": "禁止导入 subprocess，不能启动外部 Python 或其他进程。",
    "multiprocessing": "禁止导入 multiprocessing，不能派生额外 Python 进程。",
    "venv": "禁止导入 venv。",
    "ensurepip": "禁止导入 ensurepip。",
    "pip": "禁止导入 pip。",
}
FORBIDDEN_CALLS = {
    "os.system": "禁止调用 os.system。",
    "os.popen": "禁止调用 os.popen。",
    "os.execv": "禁止调用 os.execv。",
    "os.execve": "禁止调用 os.execve。",
    "os.execl": "禁止调用 os.execl。",
    "os.execvp": "禁止调用 os.execvp。",
    "os.execvpe": "禁止调用 os.execvpe。",
    "os.spawnl": "禁止调用 os.spawnl。",
    "os.spawnle": "禁止调用 os.spawnle。",
    "os.spawnlp": "禁止调用 os.spawnlp。",
    "os.spawnlpe": "禁止调用 os.spawnlpe。",
    "os.spawnv": "禁止调用 os.spawnv。",
    "os.spawnve": "禁止调用 os.spawnve。",
    "os.spawnvp": "禁止调用 os.spawnvp。",
    "os.spawnvpe": "禁止调用 os.spawnvpe。",
    "asyncio.create_subprocess_exec": "禁止创建子进程。",
    "asyncio.create_subprocess_shell": "禁止创建子进程。",
    "subprocess.Popen": "禁止启动外部进程。",
    "subprocess.run": "禁止启动外部进程。",
    "subprocess.call": "禁止启动外部进程。",
    "subprocess.check_call": "禁止启动外部进程。",
    "subprocess.check_output": "禁止启动外部进程。",
    "subprocess.getoutput": "禁止启动外部进程。",
    "subprocess.getstatusoutput": "禁止启动外部进程。",
    "__import__": "禁止通过动态导入方式访问外部进程能力。",
    "importlib.import_module": "禁止通过 importlib 动态导入危险模块。",
}


class PythonSafetyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.aliases: dict[str, str] = {}
        self.errors: list[str] = []

    def _resolve_name(self, dotted_name: str) -> str:
        parts = dotted_name.split(".")
        if not parts:
            return dotted_name
        root = self.aliases.get(parts[0], parts[0])
        if "." in root:
            root_parts = root.split(".")
        else:
            root_parts = [root]
        return ".".join(root_parts + parts[1:])

    def _push_error(self, lineno: int, message: str) -> None:
        self.errors.append(f"第 {lineno} 行: {message}")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root_name = alias.name.split(".")[0]
            alias_name = alias.asname or root_name
            self.aliases[alias_name] = root_name
            if root_name in FORBIDDEN_IMPORTS:
                self._push_error(node.lineno, FORBIDDEN_IMPORTS[root_name])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = (node.module or "").split(".")[0]
        if module in FORBIDDEN_IMPORTS:
            self._push_error(node.lineno, FORBIDDEN_IMPORTS[module])
        for alias in node.names:
            imported_name = alias.asname or alias.name
            full_name = f"{module}.{alias.name}" if module else alias.name
            self.aliases[imported_name] = full_name
            if full_name in FORBIDDEN_CALLS:
                self._push_error(node.lineno, FORBIDDEN_CALLS[full_name])
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        dotted_name = get_dotted_name(node.func)
        if dotted_name:
            resolved_name = self._resolve_name(dotted_name)
            if resolved_name in FORBIDDEN_CALLS:
                self._push_error(node.lineno, FORBIDDEN_CALLS[resolved_name])
            if resolved_name == "__import__" and node.args:
                imported_name = get_constant_string(node.args[0])
                if imported_name and imported_name.split(".")[0] in FORBIDDEN_IMPORTS:
                    self._push_error(node.lineno, FORBIDDEN_IMPORTS[imported_name.split(".")[0]])
            if resolved_name == "importlib.import_module" and node.args:
                imported_name = get_constant_string(node.args[0])
                if imported_name and imported_name.split(".")[0] in FORBIDDEN_IMPORTS:
                    self._push_error(node.lineno, FORBIDDEN_IMPORTS[imported_name.split(".")[0]])
        self.generic_visit(node)


def get_constant_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def get_dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = get_dotted_name(node.value)
        if parent:
            return f"{parent}.{node.attr}"
    return None


def trim_output(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return (
        f"{text[:MAX_OUTPUT_CHARS]}\n\n"
        f"[输出已截断，仅保留前 {MAX_OUTPUT_CHARS} 个字符，原始长度 {len(text)}]"
    )


def build_tool_response(
    *,
    returncode: int,
    stdout: str,
    stderr: str,
    interpreter: str,
) -> ToolResponse:
    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text=(
                    f"<python>{interpreter}</python>"
                    f"<returncode>{returncode}</returncode>"
                    f"<stdout>{trim_output(stdout)}</stdout>"
                    f"<stderr>{trim_output(stderr)}</stderr>"
                ),
            ),
        ],
        metadata={
            "python": interpreter,
            "returncode": returncode,
            "stdout": trim_output(stdout),
            "stderr": trim_output(stderr),
        },
    )


def validate_python_code(code: str) -> list[str]:
    if len(code) > MAX_CODE_CHARS:
        return [f"代码长度超过限制：最多允许 {MAX_CODE_CHARS} 个字符。"]

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"Python 语法错误，第 {exc.lineno} 行附近: {exc.msg}"]

    visitor = PythonSafetyVisitor()
    visitor.visit(tree)
    return visitor.errors


async def execute_python_code(
    code: str,
    timeout: float = 120,
    workspace_root: str = ".",
    **_: Any,
) -> ToolResponse:
    """在当前 Python 环境中安全执行代码。

    该工具只会使用当前服务进程对应的 Python 解释器，不允许通过
    `subprocess`、`os.system`、`multiprocessing` 等方式派生外部 Python
    或其它进程。代码在工作区目录下运行，并自动把工作区加入 `sys.path`。

    Args:
        code (str):
            要执行的 Python 代码。必须通过 `print` 输出结果。
        timeout (float):
            最大执行时长，单位秒。
        workspace_root (str):
            当前项目工作区路径，由运行时预置，不会暴露给 agent。
    """

    errors = validate_python_code(code)
    if errors:
        return build_tool_response(
            returncode=-1,
            stdout="",
            stderr="\n".join(errors),
            interpreter=sys.executable,
        )

    workspace = Path(workspace_root).resolve()
    temp_root = workspace / ".agent_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)

    runner_prefix = dedent(
        f"""
        import asyncio
        import os
        import subprocess
        import sys

        def _blocked(*args, **kwargs):
            raise RuntimeError("禁止启动外部进程，agent 只能使用当前 Python 环境。")

        async def _blocked_async(*args, **kwargs):
            raise RuntimeError("禁止启动外部进程，agent 只能使用当前 Python 环境。")

        subprocess.Popen = _blocked
        subprocess.run = _blocked
        subprocess.call = _blocked
        subprocess.check_call = _blocked
        subprocess.check_output = _blocked
        subprocess.getoutput = _blocked
        subprocess.getstatusoutput = _blocked
        asyncio.create_subprocess_exec = _blocked_async
        asyncio.create_subprocess_shell = _blocked_async
        os.system = _blocked
        os.popen = _blocked
        for _name in (
            "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp",
            "execvpe", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv",
            "spawnve", "spawnvp", "spawnvpe"
        ):
            if hasattr(os, _name):
                setattr(os, _name, _blocked)
        if hasattr(os, "startfile"):
            os.startfile = _blocked

        _workspace_root = {str(workspace)!r}
        os.chdir(_workspace_root)
        if _workspace_root not in sys.path:
            sys.path.insert(0, _workspace_root)
        """
    ).strip()

    runner_script = f"{runner_prefix}\n\n{code}\n"

    env = {
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONNOUSERSITE": "1",
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "WINDIR": os.environ.get("WINDIR", ""),
        "VIRTUAL_ENV": os.environ.get("VIRTUAL_ENV", ""),
        "PATH": str(Path(sys.executable).resolve().parent),
    }

    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-u",
        "-c",
        runner_script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(workspace),
        env=env,
    )

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
        stdout, stderr = await proc.communicate()
    except asyncio.TimeoutError:
        try:
            proc.kill()
            stdout, stderr = await proc.communicate()
        except ProcessLookupError:
            stdout, stderr = b"", b""
        timeout_message = (
            f"TimeoutError: 代码执行超过 {timeout} 秒，已被终止。"
        )
        stderr_text = stderr.decode("utf-8", errors="replace")
        stderr_text = f"{stderr_text}\n{timeout_message}" if stderr_text else timeout_message
        return build_tool_response(
            returncode=-1,
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr_text,
            interpreter=sys.executable,
        )

    return build_tool_response(
        returncode=proc.returncode,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
        interpreter=sys.executable,
    )






