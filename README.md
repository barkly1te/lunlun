# AgentScope Workspace

A local AgentScope-based assistant workspace with:

- a Python `ReActAgent` runtime
- a FastAPI streaming backend
- a separated Next.js frontend
- local file-system tools for project-aware agent workflows
- a `memory/MEMORY.md` long-term memory file maintained by the model

The project is designed for coding, document polishing, and skill-guided local agent interaction. The frontend and backend are intentionally separated to keep the system modular and extensible.

## Features

- Streaming chat between browser and local agent
- Character-by-character rendering in the frontend
- Safe Markdown rendering for final chat messages via a built-in local renderer
- Persistent multi-turn sessions on the backend
- Browser-side session recovery via `localStorage`
- Automatic long-context compression when the agent context exceeds `600000` tokens
- Workspace-aware tools for listing directories, reading files, and writing files
- Hardened Python execution bound to the current interpreter, with subprocess escapes blocked
- Project-scoped skill installation so the agent can evolve without touching global Codex skills
- Skill-oriented system prompt with local `skills/*/SKILL.md` discovery
- Academic paper aesthetics, venue-fit evaluation, and peer-review oriented skills for research writing workflows
- DashScope-compatible LLM access through `AgentScope`

## Project Structure

```text
.
├─ agent_runtime.py         # Shared agent factory and toolkit configuration
├─ run_server.py            # FastAPI backend with streaming chat endpoint
├─ run_test.py              # Minimal local script for direct agent invocation
├─ requirements-server.txt  # Backend service dependencies
├─ frontend/                # Independent Next.js frontend
├─ memory/                  # Long-term memory file maintained across turns
├─ skills/                  # Local skill definitions
└─ tools/                   # File access tools exposed to the agent
```

## Architecture

### Backend

- `agent_runtime.py` builds a reusable `ReActAgent`
- `agent_runtime.py` injects live `memory/MEMORY.md` content into the system prompt
- `agent_runtime.py` enables automatic memory compression at the configured token threshold
- `run_server.py` exposes HTTP APIs for health checks, streaming chat, and session reset
- Streaming responses are sent as `application/x-ndjson`

### Frontend

- `frontend/` uses Next.js App Router
- The chat page consumes the backend stream directly with `fetch(...).body.getReader()`
- Assistant output is rendered incrementally, one character at a time
- Thinking content is displayed in a low-emphasis collapsible section under each assistant message
- `sessionId`, messages, and the input draft are stored in `localStorage`
- When locally persisted context exceeds the configured threshold, older browser history is compacted

## Requirements

### Runtime

- Python 3.11+
- Node.js 20+
- npm 10+

### Python Dependencies

This project uses:

- `agentscope`
- `fastapi`
- `uvicorn`
- `python-dotenv`

At minimum, the backend service dependency file contains:

```txt
fastapi>=0.135.0
uvicorn>=0.41.0
python-dotenv>=1.0.0
```

If your environment does not already include `agentscope`, install it as well.

### Frontend Dependencies

The frontend uses:

- `next`
- `react`
- `react-dom`
- `typescript`
- `@types/node`
- `@types/react`
- `@types/react-dom`

No extra markdown npm dependency is required right now because the renderer is implemented locally in `frontend/components/markdown-renderer.tsx`.

## Installation

### 1. Clone the project

```bash
git clone <your-repo-url>
cd agentscope
```

### 2. Create and activate a Python virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Python dependencies

```powershell
pip install -r requirements-server.txt
pip install agentscope
```

If you want to keep everything in one command:

```powershell
pip install fastapi uvicorn python-dotenv agentscope
```

Optional, only if you want to run the bundled skill validation helper from `skill-creator`:

```powershell
pip install pyyaml
```

### 4. Install frontend dependencies

If you are in mainland China or your default npm registry is unstable, switch to the mirror first:

```powershell
npm config set registry https://registry.npmmirror.com
```

Then install frontend dependencies:

```powershell
cd frontend
npm install
cd ..
```

## Environment Variables

### Root `.env`

Copy `.env.example` to `.env`, then fill in your real keys:

```powershell
Copy-Item .env.example .env
```

Or create a `.env` file in the project root manually:

```env
DASHSCOPE_API_KEY=your_api_key_here
```

Optional backend/runtime settings:

```env
DASHSCOPE_MODEL=qwen3.5-plus
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
SERVER_HOST=127.0.0.1
SERVER_PORT=8000
FRONTEND_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
CONTEXT_COMPRESSION_TOKENS=600000
CONTEXT_COMPRESSION_KEEP_RECENT=12
TOKEN_COUNTER_MODEL=qwen3.5-plus
```

### Frontend `.env.local`

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## Usage

### Start the backend

From the project root:

```powershell
.\.venv\Scripts\python run_server.py
```

Backend default address:

```text
http://127.0.0.1:8000
```

### Start the frontend

In another terminal:

```powershell
cd frontend
npm run dev
```

Frontend default address:

```text
http://localhost:3000
```

### Direct agent test

If you only want to test the agent without the web UI:

```powershell
.\.venv\Scripts\python run_test.py
```

## API Endpoints

### `GET /api/health`

Returns service status and current in-memory session count.

### `POST /api/chat/stream`

Streams chat events in NDJSON format.

Example request:

```json
{
  "message": "帮我检查当前项目结构",
  "session_id": null,
  "reset": false
}
```

### `DELETE /api/sessions/{session_id}`

Clears a backend conversation session.

## Local Tools Exposed to the Agent

The agent can access these local tools:

- `execute_python_code` - runs code only with the current server interpreter and blocks subprocess-based escapes to other Python environments
- `install_project_skill` - installs a remote GitHub skill into the current project `skills/` directory
- `list_directory`
- `read_text_file`
- `read_file`
- `write_text_file`

All file operations are restricted to the configured workspace root. The Python execution tool is additionally hardened so it cannot spawn external Python interpreters or shell processes.

## Long-Term Memory

The project keeps a durable markdown memory file at:

```text
memory/MEMORY.md
```

Behavior:

- The file is treated as long-term memory and injected into the agent prompt each turn
- The model rewrites the file after each reply, keeping only durable, high-value information
- The file is intended for stable facts, constraints, preferences, and long-running goals
- Chain-of-thought and noisy intermediate outputs are intentionally excluded

Default sections:

- `User Preferences`
- `Project Facts`
- `Active Goals`
- `Constraints`
- `Important Decisions`

## Context Compression

Two layers of context control are enabled:

### Backend agent compression

- The in-memory agent context is automatically compressed when it exceeds `600000` tokens by default
- Compression keeps recent messages and summarizes older context into a structured continuation summary

### Frontend local compression

- Browser-side session state is stored in `localStorage`
- When the locally stored chat history grows too large, older messages are compacted into a local summary entry
- This local summary is only for browser recovery and UI continuity
- The authoritative model context remains on the backend agent plus `memory/MEMORY.md`

## Skills

The agent prompt is designed to discover and use local skills from:

```text
skills/*/SKILL.md
```

Current examples include:

- `paper-aesthetic-critic`
- `project-skill-installer`
- `paper_review`
- `peer-review`
- `scientific-critical-thinking`
- `venue-templates`
- `literature-review`
- `citation-management`
- `scientific-writing`
- `pdf`
- `pdf_analysis`
- `jupyter-notebook`
- `spreadsheet`

Some imported research skills assume richer external APIs or CLI tooling than this project exposes by default. The local runtime is still most reliable for skill guidance, rubric-based judgment, local file analysis, and Python-backed workflows.

## Key Components
- `frontend/components/chat-workbench.tsx` - main console UI with chat, control, agent, and settings panels
- `frontend/components/markdown-renderer.tsx` - built-in safe Markdown renderer for final chat messages
- `tools/python_tools.py` - hardened Python execution tool bound to the current interpreter
- `tools/skill_tools.py` - GitHub-to-project skill installer tool
- `skills/paper-aesthetic-critic/` - top-tier paper taste and venue-fit evaluation skill
- `skills/project-skill-installer/` - workflow skill for adding more project-local skills over time

## Notes

- The frontend and backend are intentionally separated to support future expansion.
- Backend sessions are currently stored in memory.
- The UI emphasizes the final answer, while the thinking process is tucked into a subtle collapsible block.
- Refreshing the page restores the current session reference and chat history from `localStorage`.

## License

Add a license here if you plan to publish the repository.







