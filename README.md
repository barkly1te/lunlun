# 论论（Lunlun）

一个基于 `AgentScope + Chainlit` 的中文智能助手项目。当前版本的核心定位不是通用聊天，而是更偏向计算机网络论文的写作分析、结构诊断、语言润色和改写建议。

它的前端交互由 Chainlit 提供，后端使用 AgentScope 的 `ReActAgent` 组织模型调用、工具调用和会话记忆。

## 项目现在能做什么

- 以“论论”的身份和用户对话，默认风格偏学术、偏 reviewer / advisor。
- 根据系统提示词，对计算机网络领域论文内容做审美分析和写作优化建议。
- 在对话过程中调用工具。
- 通过 Chainlit 展示“思考中”步骤和最终流式输出。

当前已经注册的工具包括：

- `execute_python_code`：执行 Python 代码
- `get_current_time`：获取当前机器时间
- `get_weather`：查询天气信息

## 技术栈

- Python 3.12
- AgentScope
- Chainlit
- DashScope 兼容接口
- requests / python-dotenv

## 快速开始

### 1. 准备环境

建议使用 Python `3.12`。

如果你是第一次在新环境中启动这个项目，可以先创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. 安装依赖

这个仓库当前保留了 `pyproject.toml` 和 `uv.lock`，但实际运行代码还依赖 `chainlit` 与第三方 `agentscope` 包。也就是说，新环境里如果只按最小声明安装，可能会缺包。

稳妥做法是直接安装运行所需依赖：

```powershell
pip install fastapi python-dotenv requests uvicorn chainlit agentscope
```

如果你已经有可用的 `.venv`，直接激活后继续即可。

### 3. 配置环境变量

在项目根目录创建 `.env` 文件，至少包含：

```env
DASHSCOPE_API_KEY=your_api_key
DASHSCOPE_MODEL=qwen3.5-plus
DASHSCOPE_BASE_URL=
```

说明：

- `DASHSCOPE_API_KEY`：必填
- `DASHSCOPE_MODEL`：可选，默认是 `qwen3.5-plus`
- `DASHSCOPE_BASE_URL`：可选，用于兼容 OpenAI 风格的自定义接口地址

### 4. 启动项目

当前真正的前端入口是 `app.py`，推荐用 Chainlit 启动：

```powershell
chainlit run app.py -w
```

如果你的终端没有直接识别 `chainlit` 命令，可以使用虚拟环境里的可执行文件：

```powershell
.\.venv\Scripts\chainlit.exe run app.py -w
```

启动后你会看到一个 Chainlit Web 界面，默认欢迎语是“你好！我是论论，你的智能助手”。

## 目录说明

下面按“目录”来说明当前仓库里每个文件夹的作用。

### 核心目录

| 目录 | 作用 |
| --- | --- |
| `.chainlit/` | Chainlit 的本地配置目录，控制 UI 行为、功能开关和前端配置。 |
| `.chainlit/translations/` | Chainlit 自带的多语言翻译文件。 |
| `agent_app/` | 项目的核心 Python 代码目录，Agent 的构建、配置、提示词、技能和工具都放在这里。 |
| `agent_app/agents/` | 预留给多智能体或 agent 相关实验的目录。当前只放了一个说明性占位文件。 |
| `agent_app/memory/` | 预留给记忆或持久化能力扩展的目录。当前目录存在，但还没有正式接入到运行链路。 |
| `agent_app/prompts/` | 存放系统提示词。当前 `sys_prompt.md` 定义了“论论”的角色、边界和输出格式。 |
| `agent_app/skills/` | 存放技能定义。这里更适合放可复用的能力模块或任务型说明。 |
| `agent_app/skills/generate_illustration/` | 一个具体技能目录，当前内容是面向顶会/顶刊架构图设计的技能说明。 |
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
| `app.py` | 当前主入口。负责接入 Chainlit，处理对话开始、接收消息、展示思考步骤和流式返回正文。 |
| `agent_app/agent_factory.py` | 负责构建 `ReActAgent`，把模型、提示词、工具和内存组装起来。 |
| `agent_app/settings.py` | 负责读取 `.env` 并生成运行配置。 |
| `agent_app/tools/registry.py` | 统一注册所有工具。 |
| `agent_app/tools/code_tools.py` | 注册 Python 执行工具。 |
| `agent_app/tools/get_current_time.py` | 提供当前时间工具。 |
| `agent_app/tools/get_weather_tools.py` | 提供天气查询工具，当前通过 `wttr.in` 获取天气。 |
| `agent_app/prompts/sys_prompt.md` | 定义“论论”的角色设定和输出要求。 |
| `chainlit.md` | Chainlit 的欢迎页文案。当前已被忽略，后续如果不想展示欢迎页，可以清空它。 |
| `entry.py` | 一个很轻量的本地测试入口，用来确认模型是否能正常响应。 |
| `test.py` | 另一个早期测试脚本，直接构造 AgentScope Agent 做最小调用。 |
| `main.py` | 一个占位式入口文件，目前不承担实际业务启动职责。 |
| `architecture.txt` | 项目结构与拆分思路的文字说明。 |
| `pyproject.toml` | Python 项目基础元数据。 |
| `uv.lock` | `uv` 生成的锁文件。 |

## 当前运行链路

项目的主流程大致如下：

1. 用户在 Chainlit 页面发送消息
2. `app.py` 从会话中取出已经创建好的 agent
3. agent 根据 `sys_prompt.md` 和用户输入生成响应
4. 如有需要，agent 会通过 `toolkit` 调用工具
5. Chainlit 先展示“思考中”步骤，再把最终文本流式输出到页面

## 当前项目状态

这份仓库现在更像一个可运行的原型，而不是一个已经完全产品化的框架。

几个需要提前知道的点：

- 当前默认角色强烈偏向“计算机网络论文写作优化助手”，不是完全通用的智能体。
- 当前真正使用的前端入口是 `app.py`，不是 `main.py`。
- `agent_app/memory/` 和 `agent_app/agents/` 还属于预留空间，后续可以继续扩展。
- `diagram_tool.py` 目前还是空文件，占位多于实际功能。

## 适合谁

如果你想做下面这些事情，这个仓库是一个不错的起点：

- 做一个带网页对话界面的中文 Agent 原型
- 基于 AgentScope 自定义系统提示词和工具
- 快速验证某个学术写作或垂直领域助手
- 在 Chainlit 里展示更有“过程感”的交互

## 后续可以继续补的方向

- 把依赖声明补完整，避免新环境安装歧义
- 为工具增加更严格的错误处理
- 给 `agent_app/memory/` 接入真正的持久化记忆
- 把占位目录逐步替换成实际功能模块

---

如果你只是想快速跑起来，请记住最关键的一句：

```powershell
.\.venv\Scripts\chainlit.exe run app.py -w
```

如果你想继续扩展功能，优先看这几个位置：

- `app.py`
- `agent_app/agent_factory.py`
- `agent_app/prompts/sys_prompt.md`
- `agent_app/tools/`
