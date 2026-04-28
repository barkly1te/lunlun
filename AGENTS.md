# Repository Guidelines

## Project Structure & Module Organization
The app entrypoint is `app.py`, which wires Chainlit to the AgentScope-based assistant and persists thread state in `lunlun_history.db`. Core application code lives in `agent_app/`: `agent_factory.py` builds the agent, `settings.py` loads `.env`, `tools/` contains callable tools, `skills/` contains skill directories with `SKILL.md`, and `prompts/` holds the base system prompt. Static UI assets live in `public/`. `database.py`, `entry.py`, and `test.py` are root-level support scripts. Research/reference material is stored in `article/`, and runtime logs may appear in `logs/`.

## Build, Test, and Development Commands
Use Python 3.12 and `uv`.

```bash
uv venv --python 3.12 --seed --managed-python
source .venv/bin/activate
uv pip install fastapi python-dotenv requests uvicorn chainlit agentscope
chainlit run app.py -h --host 0.0.0.0 --port 8000
python entry.py
python test.py
```

`chainlit run ...` starts the local web app. `python entry.py` and `python test.py` are smoke tests for model/tool wiring; there is no full automated test suite yet.

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, type hints on new functions, small focused helpers, and clear module-level constants. Use `snake_case` for files, functions, and variables, and `PascalCase` for dataclasses like `Settings`. Keep prompt and skill names descriptive, for example `academic-diagram-generator`. No formatter or linter is configured in-repo, so match the surrounding file’s quote style and import ordering.

## Testing Guidelines
Add lightweight verification for every change. For backend logic, prefer small reproducible scripts or extend the current smoke-test pattern. Name future test files `test_*.py` if you introduce `pytest`. When changing Chainlit flows, verify new chat, resumed chat, tool execution, and any affected UI assets in `public/`.

## Commit & Pull Request Guidelines
Recent history favors short imperative subjects, often with a conventional prefix such as `feat:` (`feat: publish current application state`). Keep commits narrowly scoped and mention the changed subsystem when useful. PRs should include: what changed, why it changed, required `.env` or config updates, manual verification steps, and screenshots for visible Chainlit UI changes.

## Configuration & Runtime Notes
Keep secrets in `.env`, not in code. Document any new environment variables in `README.md` and `pyproject.toml` when dependencies change. Avoid committing generated state such as `.venv/`, runtime logs, or local databases unless the change explicitly targets them.
