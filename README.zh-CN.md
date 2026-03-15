# 论论 AgentScope 工作区

[English](./README.md)

一个面向本地部署的 AgentScope 助手工作区，包含：

- 基于 Python 的 `ReActAgent` 运行时
- 基于 FastAPI 的流式后端服务
- 独立的 Next.js 前端工作台
- 面向项目目录的本地文件工具
- 由模型持续维护的 `memory/MEMORY.md` 长期记忆文件

这个项目主要用于本地交互场景，适合代码分析、文档润色、论文审美判断、技能驱动工作流和项目内自动化协作。前后端分离，便于后续扩展。

## 功能特性

- 浏览器与本地智能体之间的流式聊天
- 前端按字符渐进渲染回答内容
- 内置本地 Markdown 渲染器，用于安全展示最终回答
- 后端保留多轮会话状态
- 浏览器侧基于 `localStorage` 的会话恢复
- 超长上下文自动压缩
- 面向工作区的目录读取、文件读取、文件写入能力
- 绑定当前解释器的 Python 执行工具
- 项目级 skill 安装能力，不污染全局 Codex skill 目录
- 自动发现 `skills/*/SKILL.md` 并在提示词中暴露给模型
- 面向论文审美、投稿适配、评审判断的研究类 skill 组合
- 通过 AgentScope 接入 DashScope 兼容模型

## 项目结构

```text
.
├─ agent_runtime.py         # 智能体工厂、系统提示词与工具注册
├─ run_server.py            # FastAPI 流式后端入口
├─ run_test.py              # 直接在命令行测试 agent
├─ requirements-server.txt  # 后端依赖
├─ frontend/                # Next.js 前端
├─ memory/                  # 长期记忆目录
├─ skills/                  # 本地 skills
└─ tools/                   # 暴露给 agent 的工具实现
```

## 架构说明

### 后端

- `agent_runtime.py` 负责构建可复用的 `ReActAgent`
- `agent_runtime.py` 会把 `memory/MEMORY.md` 动态注入系统提示词
- `agent_runtime.py` 支持上下文压缩与长期记忆维护
- `run_server.py` 提供健康检查、聊天流和会话清理接口
- 流式响应使用 `application/x-ndjson`

### 前端

- `frontend/` 基于 Next.js App Router
- 聊天页直接消费后端 NDJSON 流
- 回答内容以字符队列方式渐进输出
- thinking 内容以折叠块形式展示
- `sessionId`、消息历史和草稿保存在浏览器 `localStorage`
- 本地上下文过大时，旧消息会被压缩成摘要

## 环境要求

### 运行时

- Python 3.11+
- Node.js 20+
- npm 10+

### Python 依赖

后端最小依赖见 `requirements-server.txt`：

```txt
fastapi>=0.135.0
uvicorn>=0.41.0
python-dotenv>=1.0.0
```

此外还需要安装 `agentscope`。

### 前端依赖

当前前端主要依赖：

- `next@^15.3.0`
- `react@^19.0.0`
- `react-dom@^19.0.0`
- `typescript@^5.8.0`
- `@types/node`
- `@types/react`
- `@types/react-dom`

## 安装步骤

### 1. 克隆项目

```bash
git clone <your-repo-url>
cd agentscope
```

### 2. 创建并激活 Python 虚拟环境

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. 安装后端依赖

```powershell
pip install -r requirements-server.txt
pip install agentscope
```

也可以直接一次性安装：

```powershell
pip install fastapi uvicorn python-dotenv agentscope
```

如果你还想使用某些 skill 附带的辅助脚本，可能还需要额外安装：

```powershell
pip install pyyaml
```

### 4. 安装前端依赖

如果你的 npm 源不稳定，可以先切换镜像：

```powershell
npm config set registry https://registry.npmmirror.com
```

然后安装前端依赖：

```powershell
cd frontend
npm install
cd ..
```

## 环境变量

### 根目录 `.env`

先复制模板：

```powershell
Copy-Item .env.example .env
```

最少需要配置：

```env
DASHSCOPE_API_KEY=your_api_key_here
```

可选运行参数：

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

说明：

- 当前运行时实际依赖的是 `DASHSCOPE_API_KEY`
- `.env.example` 中还预留了其他模型服务 key 字段，可按后续扩展需要使用

### 前端 `frontend/.env.local`

创建 `frontend/.env.local`：

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## 启动方式

### 启动后端

在项目根目录执行：

```powershell
.\.venv\Scripts\python run_server.py
```

默认地址：

```text
http://127.0.0.1:8000
```

### 启动前端

打开另一个终端：

```powershell
cd frontend
npm run dev
```

默认地址：

```text
http://localhost:3000
```

### 直接测试 agent

如果你只想测试后端 agent，不想启动网页：

```powershell
.\.venv\Scripts\python run_test.py
```

## API 接口

### `GET /api/health`

返回服务状态、工作区路径和当前内存中的会话数量。

### `POST /api/chat/stream`

以 NDJSON 格式流式返回聊天事件。

示例请求：

```json
{
  "message": "帮我检查当前项目结构",
  "session_id": null,
  "reset": false
}
```

### `DELETE /api/sessions/{session_id}`

清理指定的后端会话。

## Agent 可用本地工具

当前默认注册的工具包括：

- `execute_python_code`
- `install_project_skill`
- `list_directory`
- `read_text_file`
- `read_file`
- `write_text_file`

其中：

- 文件工具会限制在当前工作区根目录内
- Python 工具固定使用当前服务进程所对应的解释器
- skill 安装工具会把远程 skill 安装到当前项目的 `skills/` 下

## 长期记忆

长期记忆文件位于：

```text
memory/MEMORY.md
```

行为说明：

- 每轮对话开始时，`MEMORY.md` 会注入到系统提示词中
- 每轮对话结束后，模型会尝试重写这份文件
- 文件只保留跨轮仍然重要的信息
- 适合记录用户偏好、稳定约束、项目事实、长期目标和重要决策
- 不会刻意保留思维链和冗长工具输出

默认结构包括：

- `User Preferences`
- `Project Facts`
- `Active Goals`
- `Constraints`
- `Important Decisions`

## 上下文压缩

项目包含两层上下文控制：

### 后端压缩

- agent 上下文默认超过 `600000` token 时触发压缩
- 会保留最近消息，并将更早内容压成结构化摘要

### 前端本地压缩

- 浏览器把会话状态存进 `localStorage`
- 本地消息过多时，旧消息会被压缩为本地摘要项
- 这个摘要只用于页面恢复与 UI 连续性
- 真正的模型上下文仍以后端 session 和 `memory/MEMORY.md` 为准

## Skills

运行时会自动发现并使用：

```text
skills/*/SKILL.md
```

当前仓库中已经包含多类本地 skill，例如：

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

这些 skill 主要适合：

- 论文审美与投稿适配判断
- 评审视角分析
- 文献综述与引用管理
- 本地文件分析
- Python 辅助工作流

## 关键组件

- `frontend/components/chat-workbench.tsx`：主工作台 UI，包含 Chat、Control、Agent、Settings 四个区域
- `frontend/components/markdown-renderer.tsx`：本地 Markdown 渲染器
- `tools/python_tools.py`：Python 执行工具
- `tools/skill_tools.py`：GitHub skill 安装工具
- `skills/paper-aesthetic-critic/`：论文审美与投稿风格判断 skill
- `skills/project-skill-installer/`：项目级 skill 扩展工作流

## 备注

- 这个项目目前更偏向本地部署和个人工作台场景
- 后端 session 当前只保存在内存中，服务重启后不会保留
- 前端默认强调最终回答，thinking 内容放在折叠块中
- 刷新页面后会尝试从浏览器本地恢复当前会话状态

## License

Apache License Version 2.0, January 2004
