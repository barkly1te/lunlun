from pathlib import Path

from agentscope.agent import ReActAgent
from agentscope.formatter import OpenAIChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.model import OpenAIChatModel
from agentscope.token import CharTokenCounter, OpenAITokenCounter

from .settings import get_settings
from .tools.registry import build_toolkit

MAX_CONTEXT_TOKENS = 200_000


def load_sys_prompt() -> str:
    """Return the base system prompt before skill prompt injection."""
    sys_prompt_path = Path(__file__).resolve().parent / 'prompts' / 'sys_prompt.md'
    return sys_prompt_path.read_text(encoding='utf-8').strip()


def build_token_counter(model_name: str):
    """Use tiktoken-backed counting when available, otherwise fall back to chars."""
    try:
        import tiktoken  # noqa: F401
    except Exception:
        return CharTokenCounter()
    return OpenAITokenCounter(model_name)


def build_agent() -> ReActAgent:
    settings = get_settings()
    client_kwargs = {'base_url': settings.base_url} if settings.base_url else None
    formatter = OpenAIChatFormatter(
        token_counter=build_token_counter(settings.model_name),
        max_tokens=MAX_CONTEXT_TOKENS,
    )

    return ReActAgent(
        name='lunlun',
        sys_prompt=load_sys_prompt(),
        model=OpenAIChatModel(
            model_name=settings.model_name,
            api_key=settings.api_key,
            stream=True,
            client_kwargs=client_kwargs,
            generate_kwargs={'temperature': 0},
        ),
        formatter=formatter,
        toolkit=build_toolkit(),
        memory=InMemoryMemory(),
    )
