# 论论（Lunlun）

一个基于 `AgentScope + Chainlit` 的中文智能助手项目。当前版本的核心定位不是通用聊天，而是更偏向计算机网络论文的写作分析、结构诊断、语言润色和改写建议，同时支持学术风格架构图生成与图片改写。

它的前端交互由 Chainlit 提供，后端使用 AgentScope 的 `ReActAgent` 组织模型调用、工具调用和会话记忆。

## 项目现在能做什么

- 以“论论”的身份和用户对话，默认风格偏学术、偏 reviewer / advisor。
- 根据系统提示词，对计算机网络领域论文内容做审美分析和写作优化建议。
- 在对话过程中调用工具。
- 支持通过 Chainlit 侧边栏继续历史对话，并恢复 Agent 的完整运行状态（包含工具调用上下文）。
- 当累计上下文超过约 `20w tokens` 时，自动裁剪最旧轮次，避免长对话无限增长。
- 支持用户在 Chainlit 中上传图片，并将本地缓存路径注入给 Agent 使用。
- 支持调用生图工具生成学术风格图片，并在前端直接预览生成结果。
- 通过 Chainlit 展示“思考中”步骤和最终流式输出。
- 支持在前端渲染 LaTeX 数学公式。

当前已经注册的工具包括：

- `execute_python_code`：执行 Python 代码
- `read_text_file`：读取本地文本文件或技能说明
- `get_current_time`：获取当前机器时间
- `get_weather`：查询天气信息
- `generate_image_tool`：根据文本提示词生成图片，或基于上传图片进行改写
- `search_paper_rag`：调用远程 Academic Retriever 服务，检索顶会论文片段供写作对标与润色参考

## 技术栈

- Python 3.12
- AgentScope
- Chainlit
- DashScope 兼容接口
- requests / python-dotenv

## 快速开始

### 1. 准备环境

建议使用 Python `3.12` ,推荐使用 `uv` 进行环境管理

如果你是第一次在新环境中启动这个项目，可以先创建虚拟环境：

```bash
uv venv --python 3.12 --seed --managed-python
source .venv/bin/activate
```

### 2. 安装依赖

这个仓库当前保留了 `pyproject.toml` 和 `uv.lock`，但实际运行代码还依赖 `chainlit` 与第三方 `agentscope` 包。也就是说，新环境里如果只按最小声明安装，可能会缺包。

稳妥做法是直接安装运行所需依赖：

```bash
uv pip install fastapi python-dotenv requests uvicorn chainlit agentscope
```

如果你已经有可用的 `.venv`，直接激活后继续即可。

### 3. 配置环境变量

在项目根目录创建 `.env` 文件，至少包含：

```env
DASHSCOPE_API_KEY=your_api_key
DASHSCOPE_MODEL=qwen3.5-plus
DASHSCOPE_BASE_URL=
FASTAI_API_KEY=your_fastai_group_api_key
FASTAI_IMAGE_TIMEOUT_SECONDS=600
```

说明：

- `DASHSCOPE_API_KEY`：必填
- `DASHSCOPE_MODEL`：可选，默认是 `qwen3.5-plus`
- `DASHSCOPE_BASE_URL`：可选，用于兼容 OpenAI 风格的自定义接口地址
- `FASTAI_API_KEY`：图片生成能力必填，用于调用 `fastai.group` 提供的 Gemini 图片接口
- `FASTAI_IMAGE_TIMEOUT_SECONDS`：可选，默认 `600`，用于控制图片生成请求超时时间

说明补充：
- `search_paper_rag` 当前作为内部工具使用，服务地址固定写在 `agent_app/tools/search_paper_rag.py` 中。

### 4. 启动项目

当前真正的前端入口是 `app.py`，推荐用 Chainlit 启动：

```bash
chainlit run app.py -h --host 0.0.0.0 --port 8000
```

启动后你会看到一个 Chainlit Web 界面，默认欢迎语是“你好！我是论论，你的智能助手”。

### 5. 会话恢复与上下文裁剪

当前版本已经接入了本地 SQLite 持久化的继续对话能力。需要知道的点如下：

- `.chainlit/config.toml` 已开启 `persistence`，历史线程会显示在 Chainlit 侧边栏中
- 每次对话结束后，运行中的 `AgentScope` 状态会序列化写入本地 `lunlun_history.db` 的 `agent_states` 表
- 当你点击历史线程继续对话时，系统会优先恢复完整 `agent.state_dict()`，因此工具调用上下文也会被带回，而不只是表面文字
- 如果某个线程创建于这套状态持久化逻辑接入之前，系统会回退为按 `user_message / assistant_message` 文本恢复
- 当累计上下文超过约 `200000` tokens 时，系统会从最旧轮次开始裁剪，并尽量保证 `tool_use / tool_result` 配对不被截断

### 6. 图片与图示能力说明

如果你希望让智能体生成架构图、示意图，或者基于上传图片继续编辑，需要注意以下几点：

- 用户上传到 Chainlit 的图片会被缓存到本地，Agent 会拿到该本地路径并传给 `generate_image_tool`
- 生成后的图片会保存到项目根目录的 `output/` 下，该目录默认已加入 `.gitignore`
- 前端会自动识别回复中的 `[GEN_IMAGE: 路径]` 标记，并把对应图片直接渲染出来
- `agent_app/skills/top-tier-architecture-diagram-expert/` 负责生成蓝图，`agent_app/skills/academic-diagram-generator/` 负责将蓝图转换为英文提示词并调用生图工具

## 目录说明

下面按“目录”来说明当前仓库里每个文件夹的作用。

### 核心目录

| 目录 | 作用 |
| --- | --- |
| `.chainlit/` | Chainlit 的本地配置目录，控制 UI 行为、功能开关和前端配置。 |
| `.chainlit/translations/` | Chainlit 自带的多语言翻译文件。 |
| `public/` | Chainlit 可直接提供的静态资源目录。当前放了一个浏览器复制功能的降级脚本。 |
| `agent_app/` | 项目的核心 Python 代码目录，Agent 的构建、配置、提示词、技能和工具都放在这里。 |
| `agent_app/agents/` | 预留给多智能体或 agent 相关实验的目录。当前只放了一个说明性占位文件。 |
| `agent_app/memory/` | 预留给记忆或持久化能力扩展的目录。当前目录存在，但还没有正式接入到运行链路。 |
| `agent_app/prompts/` | 存放系统提示词。当前 `sys_prompt.md` 定义了“论论”的角色、边界和输出格式。 |
| `agent_app/skills/` | 存放技能定义。这里更适合放可复用的能力模块或任务型说明。 |
| `agent_app/skills/top-tier-architecture-diagram-expert/` | 用于先生成学术架构图蓝图与视觉设计方案。 |
| `agent_app/skills/academic-diagram-generator/` | 根据蓝图或用户描述组织英文提示词，并强制调用生图工具完成出图。 |
| `agent_app/tools/` | 工具实现目录，包含工具函数和统一注册逻辑。 |

### 本地运行时常见目录

这些目录通常不是业务核心，但你在本地开发时大概率会看到：

| 目录 | 作用 |
| --- | --- |
| `.venv/` | 本地虚拟环境目录，用来隔离 Python 依赖。默认不应该提交。 |
| `__pycache__/` | Python 运行后生成的缓存目录。 |
| `agent_app/__pycache__/` | `agent_app` 下的 Python 缓存目录。 |
| `agent_app/tools/__pycache__/` | `tools` 子目录下的 Python 缓存目录。 |

## 关键文件说明

| 文件 | 作用 |
| --- | --- |
| `app.py` | 当前主入口。负责接入 Chainlit，处理新建对话、继续对话、上下文裁剪、图片附件注入、思考步骤展示和最终流式返回。 |
| `database.py` | 本地 SQLite 初始化与 `agent_states` 持久化逻辑，负责保存和恢复完整 Agent 状态。 |
| `agent_app/agent_factory.py` | 负责构建 `ReActAgent`，并配置上下文 token 计数与 `20w` 上限截断。 |
| `agent_app/settings.py` | 负责读取 `.env` 并生成运行配置。 |
| `agent_app/tools/registry.py` | 统一注册所有工具。 |
| `agent_app/tools/code_tools.py` | 注册 Python 执行工具。 |
| `agent_app/tools/file_tools.py` | 提供本地文本文件读取工具，便于 Agent 读取技能说明等内容。 |
| `agent_app/tools/get_current_time.py` | 提供当前时间工具。 |
| `agent_app/tools/get_weather_tools.py` | 提供天气查询工具，当前通过 `wttr.in` 获取天气。 |
| `agent_app/tools/image_gen_tool.py` | 提供图片生成与图片改写工具，调用外部图片接口并将结果落盘到 `output/`。 |
| `agent_app/tools/search_paper_rag.py` | 提供论文片段检索工具，调用远程 Academic Retriever 服务返回顶会参考片段。 |
| `agent_app/prompts/sys_prompt.md` | 定义“论论”的角色设定和输出要求。 |
| `.chainlit/config.toml` | Chainlit 前端配置文件，当前已开启 LaTeX 渲染与线程持久化。 |
| `public/clipboard_fallback.js` | 给 HTTP 或受限浏览器环境下的复制操作提供降级支持。 |
| `chainlit.md` | Chainlit 的欢迎页文案。当前已被忽略，后续如果不想展示欢迎页，可以清空它。 |
| `entry.py` | 一个很轻量的本地测试入口，用来确认模型是否能正常响应。 |
| `test.py` | 另一个早期测试脚本，直接构造 AgentScope Agent 做最小调用。 |
| `main.py` | 一个占位式入口文件，目前不承担实际业务启动职责。 |
| `architecture.txt` | 项目结构与拆分思路的文字说明。 |
| `pyproject.toml` | Python 项目基础元数据。 |
| `uv.lock` | `uv` 生成的锁文件。 |

## 当前运行链路

项目的主流程大致如下：

1. 用户在 Chainlit 页面新建对话，或从侧边栏恢复历史线程
2. `app.py` 为新线程构建 agent；如果是继续对话，则优先从本地 SQLite 的 `agent_states` 表恢复完整 `agent.state_dict()`
3. 如果旧线程还没有完整状态快照，系统会回退为按 `user_message / assistant_message` 文本重建基础上下文
4. 如果消息里带有图片附件，`app.py` 会提取本地缓存路径并作为系统提示附加到用户输入
5. 在每轮请求前后，系统会估算当前上下文长度；超过约 `200000` tokens 时，会从最旧轮次开始裁剪，并尽量保留完整的工具调用配对
6. agent 根据 `sys_prompt.md` 和用户输入生成响应
7. 如有需要，agent 会通过 `toolkit` 调用工具，包括读取文件、生图、改图或检索顶会论文片段
8. 对话结束后，当前 agent 的完整运行状态会再次写回本地 SQLite，供下次继续对话恢复
9. 如果最终回复里包含 `[GEN_IMAGE: 路径]` 标记，前端会将对应图片解析并渲染出来
10. Chainlit 先展示“思考中”步骤，再把最终文本流式输出到页面

## 当前项目状态

这份仓库现在更像一个可运行的原型，而不是一个已经完全产品化的框架。

几个需要提前知道的点：

- 当前默认角色强烈偏向“计算机网络论文写作优化助手”，不是完全通用的智能体。
- 当前真正使用的前端入口是 `app.py`，不是 `main.py`。
- 当前已经具备基于本地 SQLite 的会话继续能力，但这仍然属于工程化持久化状态，不等同于完善的长期记忆系统。
- `agent_app/memory/` 和 `agent_app/agents/` 还属于预留空间，后续可以继续扩展。
- `diagram_tool.py` 目前还是空文件，占位多于实际功能；实际图片链路已经转移到 `image_gen_tool.py` 与两个图示技能目录中。

## 适合谁

如果你想做下面这些事情，这个仓库是一个不错的起点：

- 做一个带网页对话界面的中文 Agent 原型
- 基于 AgentScope 自定义系统提示词和工具
- 快速验证某个学术写作或垂直领域助手
- 在 Chainlit 里展示更有“过程感”的交互

## 后续可以继续补的方向

- 把依赖声明补完整，避免新环境安装歧义
- 为工具增加更严格的错误处理
- 把当前基于 `agent_states` 的会话恢复升级为更系统的长期记忆/摘要记忆机制
- 把占位目录逐步替换成实际功能模块
- 为图片生成链路补充更完整的异常处理、重试和结果缓存策略

---

如果你想继续扩展功能，优先看这几个位置：

- `app.py`
- `agent_app/agent_factory.py`
- `agent_app/prompts/sys_prompt.md`
- `agent_app/tools/`
