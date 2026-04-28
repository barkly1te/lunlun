# 论论（Lunlun）

一个基于 `AgentScope + Chainlit` 的中文智能助手原型。当前版本的主要定位不是通用聊天，而是偏向计算机网络论文写作分析、结构诊断、语言润色与改写建议，同时支持学术风格图示生成与图片改写。

前端由 Chainlit 提供，后端核心运行时是 AgentScope 的 `ReActAgent`。项目当前重点在于：

- 本地可运行的中文 Agent 原型
- 可继续历史会话的 Agent 状态持久化
- 可见的推理过程与最终流式输出
- 基于 skill 的任务路由
- 图片输入、图片生成与本地结果渲染

## 当前能力

- 以“论论”的身份进行中文对话，输出风格偏学术、偏 reviewer / advisor。
- 面向计算机网络相关论文场景给出分析、批评、改写和结构建议。
- 支持工具调用，包括代码执行、天气、时间、论文片段检索、文件读取、生图与改图。
- 支持自动发现并注册 `agent_app/skills/` 下的本地 skills。
- 支持在 Chainlit 输入框中通过 slash command 选择 skill，例如 `/<skill-name>`。
- 支持继续历史线程，并优先恢复完整 `agent.state_dict()`，而不是只恢复表面聊天文本。
- 支持图片上传；图片会同时以原生多模态 block 和本地缓存路径提示的形式注入给模型。
- 如果工具返回 `[GEN_IMAGE: 路径]` 标记，前端会自动解析并把图片直接展示出来。
- 在每轮模型调用前写出格式化后的 prompt 日志，便于调试。
- 如果底层模型返回 `thinking` block，前端会实时展示思考过程；步骤结束后自动折叠，正文单独流式输出。

## 当前已注册工具

- `execute_python_code`：执行 Python 代码
- `get_current_time`：获取当前机器时间
- `get_weather`：查询天气信息
- `read_text_file`：读取本地文本文件
- `list_registered_skills`：列出当前已注册的本地 skills
- `read_registered_skill`：按名称读取某个 skill 的 `SKILL.md`
- `generate_image_tool`：文本生图或基于本地图片路径改图
- `search_paper_rag`：调用远程 Academic Retriever 服务检索论文片段

除了这些显式工具，项目还会把每个本地 skill 目录注册为 AgentScope agent skill。

## 当前本地 skills

- `academic-diagram-generator`
- `top-tier-architecture-diagram-expert`
- `thesis-abstract-and-chapter-opening-editor`
- `vanbever-academic-reasoning-full`
- `vanbever-academic-reasoning-v1`

## 技术栈

- Python 3.12
- AgentScope
- Chainlit
- OpenAI-compatible / DashScope 接口
- requests
- python-dotenv
- SQLite

## 快速开始

### 1. 准备环境

建议使用 Python `3.12`，并使用 `uv` 管理虚拟环境：

```bash
uv venv --python 3.12 --seed --managed-python
source .venv/bin/activate
```

### 2. 安装依赖

当前仓库保留了 `pyproject.toml` 和 `uv.lock`，但实际运行仍依赖 `chainlit` 和第三方 `agentscope` 包。稳妥做法是直接安装运行所需依赖：

```bash
uv pip install fastapi python-dotenv requests uvicorn chainlit agentscope
```

### 3. 配置环境变量

在项目根目录创建 `.env` 文件。最小配置如下：

```env
DASHSCOPE_API_KEY=your_api_key
DASHSCOPE_MODEL=qwen3.6-plus
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
FASTAI_API_KEY=your_fastai_group_api_key
FASTAI_IMAGE_TIMEOUT_SECONDS=600
```

说明：

- `DASHSCOPE_API_KEY`：必填
- `DASHSCOPE_MODEL`：可选，默认 `qwen3.6-plus`
- `DASHSCOPE_BASE_URL`：可选，默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`
- `FASTAI_API_KEY`：图片生成 / 改图所需；不配置时 `generate_image_tool` 不可用
- `FASTAI_IMAGE_TIMEOUT_SECONDS`：可选，默认 `600`

补充：

- `search_paper_rag` 当前使用固定远程服务地址，配置写在 `agent_app/tools/search_paper_rag.py`

### 4. 启动项目

真正的 Web 入口是 `app.py`：

```bash
chainlit run app.py -h --host 0.0.0.0 --port 8000
```

启动后你会看到 Chainlit 页面。欢迎语由 `app.py` 中的 `on_chat_start()` 发送，而不是依赖 `chainlit.md`。

### 5. 本地测试脚本

仓库里保留了两个轻量测试入口：

```bash
python entry.py
python test.py
```

它们更适合做模型 / 工具链路的 smoke test，不是完整自动化测试。

## 运行机制

### 1. 会话与持久化

- `app.py` 在导入时会初始化 `lunlun_history.db`
- Chainlit 官方 SQLAlchemy data layer 与项目自定义的 `agent_states` 表共用同一个 SQLite 文件
- `@cl.header_auth_callback` 当前返回固定内部用户 `lunlun_internal_user`
- 新会话会立即构建 agent 并写入初始状态
- 恢复历史线程时，系统优先读取 `agent_states` 中的完整序列化状态
- 如果找不到完整状态，才退回为根据 `user_message / assistant_message` 重建基础 memory

### 2. 上下文裁剪

- 当前上下文上限是约 `200000` tokens
- 裁剪会尽量避开未闭合的 `tool_use / tool_result` 配对，避免把工具调用链切坏

### 3. 技能路由与 slash command

- 启动会话时，系统会把所有本地 skills 注册为 Chainlit commands
- 用户既可以在输入框里直接输入 `/<skill-name>`，也可以通过命令选择器选择 skill
- 一旦显式选择了某个 skill，本轮用户输入会被包装成一段系统路由提示，强制 agent 优先读取对应 `SKILL.md`
- 如果只输入了 `/<skill-name>` 而没有具体需求，前端会先提示继续补充任务描述

### 4. 图片输入与图片输出

- 上传到 Chainlit 的图片会被收集成本地路径
- 用户消息会被构造成原生多模态 block：文本 + `image`
- 同时系统还会附加一段本地路径提示，方便 `generate_image_tool` 读取 `image_path`
- 图片生成结果默认保存到项目根目录下的 `output/`
- 回复中的 `[GEN_IMAGE: 路径]` 会在 `app.py` 中被解析为 `cl.Image`

### 5. 推理展示与流式输出

- 当前实现使用 AgentScope 的 `stream_printing_messages(...)` 捕获 agent 的实时输出
- 如果模型输出 `thinking` block，前端会实时写入一个 Chainlit `Step`
- 这个 `Step` 当前配置为：
  - `default_open=True`
  - `auto_collapse=True`
- 也就是：思考开始时默认展开，步骤结束后自动折叠，用户仍可手动再次展开
- 最终正文使用单独的 `cl.Message` 流式输出，不与思考内容混在一起

### 6. Prompt 日志

- 每次模型调用前，系统会把“格式化后的 messages + tool schemas”写入 `logs/`
- 文件名格式类似：

```text
logs/prompt-<thread-id>-<timestamp>.json
```

- 这份日志非常适合排查 prompt 拼接、tool schema 注入和多模态输入是否符合预期

## Chainlit 前端配置

当前 `.chainlit/config.toml` 的几个关键点：

- 开启了 `persistence`
- 开启了 `cot = "full"`
- 开启了自发文件上传
- `custom_js = "/public/clipboard_compat.js"`
- `custom_css = "/public/chainlit-overrides.css"`

其中：

- `public/clipboard_compat.js` 是当前实际启用的复制兼容脚本
- `public/chainlit-overrides.css` 目前主要用于调整 command popover 的响应式显示
- `public/clipboard_fallback.js` 仍在仓库中，但当前不是活跃配置入口

## 目录说明

### 核心目录

| 目录 | 作用 |
| --- | --- |
| `.chainlit/` | Chainlit 本地配置与翻译文件 |
| `agent_app/` | 核心应用代码：agent、settings、prompts、skills、tools |
| `agent_app/prompts/` | 系统提示词 |
| `agent_app/skills/` | 本地 skills 目录 |
| `agent_app/tools/` | 工具实现与注册逻辑 |
| `public/` | Chainlit 静态资源 |
| `logs/` | 运行时 prompt 日志输出目录 |
| `output/` | 图片工具输出目录 |

### 关键文件

| 文件 | 作用 |
| --- | --- |
| `app.py` | 主入口；负责 Chainlit 生命周期、slash command、图片输入、思考流展示、正文流、图片渲染、prompt 日志与 agent 状态持久化 |
| `database.py` | SQLite 初始化与 `agent_states` 持久化 |
| `agent_app/agent_factory.py` | 构建 `ReActAgent`，配置模型、formatter、toolkit、memory 与 token 上限 |
| `agent_app/settings.py` | 读取 `.env` 并生成运行配置 |
| `agent_app/tools/registry.py` | 聚合并注册工具与本地 skills |
| `agent_app/tools/file_tools.py` | 文件读取、列出 skills、读取 skill 文档 |
| `agent_app/tools/image_gen_tool.py` | 图片生成 / 改图，并将结果落盘到 `output/` |
| `.chainlit/config.toml` | Chainlit UI 与持久化配置 |
| `public/clipboard_compat.js` | 当前启用的复制兼容脚本 |
| `public/chainlit-overrides.css` | 当前启用的 Chainlit 自定义样式 |

## 当前项目状态

这份仓库仍然更像一个可运行的原型，而不是完整产品。

当前需要提前知道的点：

- 默认角色和提示词明显偏向“计算机网络论文写作优化助手”
- 当前实际 Web 启动入口就是 `app.py`
- 当前已经具备工程化会话恢复，但这不等于完善的长期记忆系统
- `agent_app/agents/` 目前仍然主要是预留空间
- `agent_app/tools/diagram_tool.py` 目前仍是占位文件
- 图片链路依赖外部接口；如果外部服务不可用，对应能力会直接失效

## 适合谁

如果你想做下面这些事情，这个仓库是一个合适的起点：

- 做一个带网页界面的中文 Agent 原型
- 基于 AgentScope 自定义 prompts、skills 和 tools
- 快速验证学术写作或垂直领域助手
- 在 Chainlit 中展示可感知的过程型交互

## 后续可以继续补的方向

- 补齐依赖声明，减少新环境安装歧义
- 为工具增加更严格的错误处理与重试
- 给 `search_paper_rag` 和图片服务增加更清晰的配置说明
- 引入更系统的长期记忆 / 摘要记忆机制
- 为 Chainlit 前端补充更细粒度的自定义样式与工具步骤展示

---

如果你要继续扩展，优先看这几个位置：

- `app.py`
- `agent_app/agent_factory.py`
- `agent_app/prompts/sys_prompt.md`
- `agent_app/tools/`
- `agent_app/skills/`
