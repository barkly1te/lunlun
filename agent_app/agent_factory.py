import asyncio
import os
from pathlib import Path

from agentscope.agent import ReActAgent
from agentscope.formatter import OpenAIChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel
from agentscope.tool import Toolkit, execute_python_code
from dotenv import load_dotenv
from .settings import get_settings
from .tools.registry import build_toolkit

def load_sys_prompt() -> str:
    """
    读取并返回最基础的系统提示词。
    注意：ReActAgent 会自动将 toolkit 中的 skill 提示词追加到此返回值之后。
    """
    sys_prompt_path = Path(__file__).resolve().parent / "prompts" / "sys_prompt.md"
    return sys_prompt_path.read_text(encoding="utf-8").strip()

def build_agent() -> ReActAgent:
    settings = get_settings()
    client_kwargs = {"base_url":settings.base_url} if settings.base_url else None
    
    return ReActAgent(
        name = "lunlun",
        sys_prompt= load_sys_prompt(),
        model = OpenAIChatModel(
            model_name = settings.model_name,
            api_key = settings.api_key,
            stream = True,
            client_kwargs=client_kwargs,
            generate_kwargs={"temperature": 0},
        ),
        formatter=OpenAIChatFormatter(),
        toolkit=build_toolkit(),
        memory=InMemoryMemory(),
    )
