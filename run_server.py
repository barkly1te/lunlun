from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncGenerator
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agentscope.message import Msg
from agentscope.pipeline import stream_printing_messages

from agent_runtime import create_agent


WORKSPACE_ROOT = str(Path(__file__).resolve().parent)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    session_id: str | None = None
    reset: bool = False


@dataclass
class AgentSession:
    agent: object
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _cors_origins() -> list[str]:
    configured = os.getenv("FRONTEND_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]

    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


app = FastAPI(title="AgentScope Streaming Server", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_sessions: dict[str, AgentSession] = {}
_sessions_guard = asyncio.Lock()


def _ndjson(payload: dict) -> bytes:
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


def _collect_text(msg: Msg, block_type: str) -> str:
    chunks: list[str] = []
    for block in msg.get_content_blocks():
        if block["type"] == "text" and block_type == "text":
            chunks.append(block["text"])
        elif block["type"] == "thinking" and block_type == "thinking":
            chunks.append(block["thinking"])
    return "".join(chunks)


def _delta_from_prefix(current: str, previous: str) -> str:
    if not current:
        return ""
    if current.startswith(previous):
        return current[len(previous):]
    return current


async def _get_or_create_session(
    session_id: str | None,
    reset: bool,
) -> tuple[str, AgentSession]:
    async with _sessions_guard:
        if session_id and not reset and session_id in _sessions:
            return session_id, _sessions[session_id]

        resolved_id = uuid4().hex
        session = AgentSession(agent=create_agent(workspace_root=WORKSPACE_ROOT))
        _sessions[resolved_id] = session
        return resolved_id, session


async def _stream_chat_events(
    request: ChatRequest,
) -> AsyncGenerator[bytes, None]:
    try:
        session_id, session = await _get_or_create_session(
            session_id=request.session_id,
            reset=request.reset,
        )
    except Exception as exc:
        yield _ndjson({"type": "error", "message": str(exc)})
        yield _ndjson({"type": "done"})
        return

    yield _ndjson({"type": "session", "session_id": session_id})

    async with session.lock:
        text_prefix: dict[str, str] = {}
        thinking_prefix: dict[str, str] = {}
        result_holder: dict[str, Msg] = {}

        async def run_agent() -> Msg:
            result_holder["reply"] = await session.agent(
                Msg(name="user", content=request.message, role="user"),
            )
            return result_holder["reply"]

        try:
            yield _ndjson(
                {
                    "type": "status",
                    "phase": "accepted",
                    "message": "请求已接收，正在调用智能体。",
                },
            )

            async for printed_msg, _ in stream_printing_messages(
                [session.agent],
                run_agent(),
            ):
                if printed_msg.role == "assistant":
                    thinking = _collect_text(printed_msg, "thinking")
                    thinking_delta = _delta_from_prefix(
                        thinking,
                        thinking_prefix.get(printed_msg.id, ""),
                    )
                    thinking_prefix[printed_msg.id] = thinking
                    if thinking_delta:
                        yield _ndjson(
                            {
                                "type": "thinking_delta",
                                "delta": thinking_delta,
                            },
                        )

                    text = _collect_text(printed_msg, "text")
                    text_delta = _delta_from_prefix(
                        text,
                        text_prefix.get(printed_msg.id, ""),
                    )
                    text_prefix[printed_msg.id] = text
                    if text_delta:
                        yield _ndjson(
                            {
                                "type": "assistant_delta",
                                "delta": text_delta,
                            },
                        )

                elif printed_msg.role == "system":
                    for block in printed_msg.get_content_blocks("tool_result"):
                        yield _ndjson(
                            {
                                "type": "status",
                                "phase": "tool",
                                "message": f"工具已执行: {block['name']}",
                            },
                        )

            reply = result_holder.get("reply")
            final_text = reply.get_text_content() if reply else ""
            yield _ndjson(
                {
                    "type": "final",
                    "message": final_text or "",
                },
            )
        except Exception as exc:
            yield _ndjson({"type": "error", "message": str(exc)})
        finally:
            session.agent.set_msg_queue_enabled(False)
            yield _ndjson({"type": "done"})


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "workspace_root": WORKSPACE_ROOT,
            "sessions": len(_sessions),
        },
    )


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_chat_events(request),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/api/sessions/{session_id}")
async def clear_session(session_id: str) -> JSONResponse:
    async with _sessions_guard:
        removed = _sessions.pop(session_id, None)

    return JSONResponse(
        {
            "removed": removed is not None,
            "session_id": session_id,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "run_server:app",
        host=os.getenv("SERVER_HOST", "127.0.0.1"),
        port=int(os.getenv("SERVER_PORT", "8000")),
        reload=False,
    )
