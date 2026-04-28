import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

DEFAULT_DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


@dataclass(frozen=True)
class Settings:
    api_key: str
    model_name: str
    base_url: str | None


def get_settings() -> Settings:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("Missing DASHSCOPE_API_KEY")

    return Settings(
        api_key=api_key,
        model_name=os.getenv("DASHSCOPE_MODEL", "qwen3.6-plus"),
        base_url=os.getenv("DASHSCOPE_BASE_URL") or DEFAULT_DASHSCOPE_BASE_URL,
    )
