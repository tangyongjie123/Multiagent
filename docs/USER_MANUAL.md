# RepoGraph 用户使用手册

更新时间：2026-11-04

本文档面向第一次安装和使用 RepoGraph 的用户，覆盖 Windows 环境安装、依赖配置、数据库准备、环境变量、启动、仓库分析、AI 助手、停止服务、升级和常见故障。

项目当前主要支持 Windows + PowerShell。Linux 和 macOS 可以使用相同的 Python、Node.js、Git 和 PostgreSQL 工具，但路径和命令需要按本机环境调整。

## 1. 功能概览

RepoGraph 提供两类主要能力：

1. **仓库静态分析**
   - 输入 GitHub、GitLab 或 Gitee 的公开 HTTPS Git 地址。
   - 浅克隆指定分支到隔离工作区。
   - 通过主 Agent 调度 Repository、Architecture、Test、Security、Quality 和 Report 六个专业 Agent。
   - 输出架构、测试、安全、质量四类带证据的 Finding。
   - 生成并下载 Markdown 或自包含 HTML 中文报告。

2. **AI 助手**
   - 在分析完成后，基于已有 Finding 回答项目风险、问题证据和修复计划。
   - 由 Intent、Conversation 和 Evidence Verifier 三个聊天 Agent 协作。
   - 回答正文通过 SSE 流式显示。
   - 展示当前 Agent 阶段、Finding 引用和执行状态。
   - 不执行目标仓库中的代码、测试、构建或脚本。

## 2. 最短安装与启动路径

如果本机已经准备好 Python 3.11、Node.js、Git 和 PostgreSQL，可以直接执行：

```powershell
cd E:\Aipracite\py_workspace\Multiagent

if (-not (Test-Path .env)) { Copy-Item .env.example .env }

conda activate multiagent
python -m pip install -r requirements-dev.txt

cd frontend
npm ci
cd ..

python dev.py
```

然后打开：

```text
http://127.0.0.1:5173
```

如果其中任何一步失败，请继续阅读后续章节。

## 3. 推荐环境版本

| 工具 | 推荐版本 | 用途 | 是否必需 |
| --- | --- | --- | --- |
| Windows PowerShell | Windows 10/11 自带 | 执行安装和启动命令 | 必需 |
| Python | 3.11.18 | FastAPI、Agent、数据库和 MCP | 必需 |
| Conda 或 Miniconda | 当前可用版本 | 管理独立 Python 环境 | 推荐 |
| Node.js | 24.16.0 | 运行 React 和 Vite | 必需 |
| npm | 11.13.0 | 安装前端依赖 | 必需 |
| Git | 当前稳定版 | 浅克隆被分析仓库 | 必需 |
| PostgreSQL | 14 或更高版本 | 保存分析、问题、聊天和事件 | 必需 |
| DeepSeek 或其他 OpenAI 兼容 API | 当前可用版本 | Architecture、Quality 和聊天推理 | 必需 |
| Milvus | 当前可用版本 | 后续代码向量检索 | 可选 |
| Neo4j + APOC | 5.x | 后续依赖关系图谱 | 可选 |

JDK 和 Maven 不是运行 RepoGraph 平台本身的必需工具。平台只对 Java 仓库进行只读静态扫描，不执行 Maven 构建、测试或目标程序。

项目绑定的 Python 解释器为：

```text
D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe
```

如果解释器路径不同，请以本机 Conda 环境实际路径为准。

官方下载入口：

- [Python](https://www.python.org/downloads/)
- [Miniconda](https://docs.conda.io/projects/miniconda/en/latest/)
- [Node.js](https://nodejs.org/)
- [Git for Windows](https://git-scm.com/download/win)
- [PostgreSQL](https://www.postgresql.org/download/windows/)

## 4. 获取项目

已有项目目录：

```powershell
cd E:\Aipracite\py_workspace\Multiagent
```

从 GitHub 首次下载：

```powershell
git clone https://github.com/tangyongjie123/Multiagent.git
cd Multiagent
```

确认当前分支和 Git 状态：

```powershell
git branch --show-current
git status --short
```

## 5. 准备 Python 环境

### 5.1 创建 Conda 环境

首次使用：

```powershell
conda create -n multiagent python=3.11 -y
conda activate multiagent
```

如果项目已经绑定 `multiagent` 环境，直接激活：

```powershell
conda activate multiagent
```

确认版本：

```powershell
python --version
```

应看到：

```text
Python 3.11.18
```

### 5.2 安装 Python 依赖

开发环境推荐安装：

```powershell
cd E:\Aipracite\py_workspace\Multiagent
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pip check
```

只运行生产服务时可以安装：

```powershell
python -m pip install -r requirements.txt
```

不要同时维护 `.venv` 和 Conda 两套 Python 环境，避免解释器混用。

## 6. 准备 Node.js 和前端依赖

确认 Node.js 和 npm：

```powershell
node --version
npm --version
```

推荐版本：

```text
Node.js v24.16.0
npm 11.13.0
```

安装前端锁定依赖：

```powershell
cd E:\Aipracite\py_workspace\Multiagent\frontend
npm ci
```

如果本地没有 `package-lock.json`，才使用：

```powershell
npm install
```

前端依赖包括：

- React 19
- TypeScript
- Vite
- react-markdown
- remark-gfm

## 7. 安装和检查 Git

确认 Git 可用：

```powershell
git --version
```

如果 PowerShell 找不到 Git：

1. 安装 Git for Windows。
2. 确认 `C:\Program Files\Git\cmd\git.exe` 存在。
3. 在 `.env` 中设置：

```dotenv
GIT_EXECUTABLE=C:\Program Files\Git\cmd\git.exe
```

RepoGraph 只会对白名单中的公开仓库执行浅克隆：

```text
github.com
gitee.com
gitlab.com
```

Git URL 中不能包含用户名或密码。

## 8. 准备 PostgreSQL

PostgreSQL 是必需服务。平台使用它保存：

- 仓库和分析运行
- Agent 事件和工具事件
- Finding
- 报告元数据
- 聊天会话、消息和引用
- LangGraph checkpoint

### 8.1 启动数据库

确认 PostgreSQL 服务已经启动，并检查端口：

```powershell
Test-NetConnection 127.0.0.1 -Port 5432
```

也可以使用：

```powershell
pg_isready -h 127.0.0.1 -p 5432
```

### 8.2 创建数据库和用户

生产或长期开发环境建议使用独立数据库和用户，不要长期使用 PostgreSQL 超级用户。

以管理员身份进入 `psql` 后，可以参考：

```sql
CREATE USER multiagent WITH PASSWORD '请替换为强密码';
CREATE DATABASE multiagent OWNER multiagent;
```

如果数据库已经存在，不要重复创建。

### 8.3 配置变量

在 `.env` 中设置：

```dotenv
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=multiagent
POSTGRES_USER=multiagent
POSTGRES_PASSWORD=请替换为强密码
AUTO_CREATE_TABLES=true
```

开发模式下 `AUTO_CREATE_TABLES=true` 会自动创建应用表和 LangGraph checkpoint 表。数据库本身必须先创建。

## 9. 配置大模型 API

Architecture、Quality 和 AI 助手需要调用 OpenAI 兼容的 Chat API。

### 9.1 DeepSeek

```dotenv
CHAT_PROVIDER=deepseek
DEEPSEEK_API_KEY=请替换为有效密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_PRO_MODEL=deepseek-reasoner
```

### 9.2 DashScope 兼容接口

```dotenv
CHAT_PROVIDER=dashscope
DASHSCOPE_API_KEY=请替换为有效密钥
DASHSCOPE_BASE_URL=请替换为兼容接口地址
DASHSCOPE_CHAT_MODEL=qwen3.8-flash
```

只配置当前使用的一种模型供应商即可。

不要把真实 API Key 写入代码、文档、Git 提交或截图。

## 10. 配置 `.env`

从模板创建本地配置：

```powershell
cd E:\Aipracite\py_workspace\Multiagent
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

如果 `.env` 已经存在，不要覆盖；先备份并合并新增变量。

至少修改：

```dotenv
DEEPSEEK_API_KEY=请替换为有效密钥
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_DB=multiagent
POSTGRES_USER=multiagent
POSTGRES_PASSWORD=请替换为强密码
```

常用可选配置：

```dotenv
APP_PORT=8000
FRONTEND_ORIGIN=http://localhost:5173,http://127.0.0.1:5173
MCP_TOOL_URL=http://127.0.0.1:8000/mcp/
CHAT_HISTORY_MESSAGES=12
CHAT_TOKEN_BUDGET=60000
ANALYSIS_TOKEN_BUDGET=120000
GIT_CLONE_TIMEOUT_SECONDS=180
GIT_MAX_REPOSITORY_MB=200
GIT_MAX_FILES=10000
```

修改 `APP_PORT` 时，必须同步修改 `MCP_TOOL_URL` 中的端口。

`.env` 已被 `.gitignore` 排除，不能提交到 Git。

可选的本地覆盖配置写入 `.env.local`。它只用于本机覆盖，优先级高于 `.env`，且同样不能提交 Git。

完整说明见：

```text
docs/ENVIRONMENT_VARIABLES.md
```

## 11. Milvus 与 Neo4j 是否必须

当前版本中 Milvus 和 Neo4j 不是基础分析和聊天主链路的必需服务。

### Milvus

当前只进行连接健康检查，不会在分析或聊天时自动写入向量，也不会执行向量检索。

如已启动虚拟机中的 Milvus，可以配置：

```dotenv
MILVUS_URI=http://192.168.74.180:19530
MILVUS_USER=请替换
MILVUS_PASSWORD=请替换
MILVUS_DATABASE=default
MILVUS_TOP_K=8
```

### Neo4j

当前会检查连接并创建基础约束，但不会在每次分析时自动写入代码图谱。

```dotenv
NEO4J_URI=bolt://192.168.74.180:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=请替换
```

Milvus 或 Neo4j 未配置时，基础分析和 Finding 聊天仍可使用，健康状态可能显示为降级。

只要 PostgreSQL、Git 和 Chat API 正常，`/health` 中 Milvus/Neo4j 的异常不会阻止基础分析。

## 12. 启动项目

推荐在项目根目录执行：

```powershell
cd E:\Aipracite\py_workspace\Multiagent
conda activate multiagent
python dev.py
```

如果使用已绑定的完整解释器路径：

```powershell
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' dev.py
```

`dev.py` 会同时启动：

- FastAPI 后端
- MCP Streamable HTTP 工具服务
- React/Vite 前端

正常启动后会显示：

```text
[RepoGraph] 启动完成，开发环境已可用
[RepoGraph] 可视化界面：http://127.0.0.1:5173
[RepoGraph] 接口文档：http://127.0.0.1:8000/docs
[RepoGraph] MCP 工具端点：http://127.0.0.1:8000/mcp/
```

## 13. 访问地址

| 地址 | 用途 |
| --- | --- |
| `http://127.0.0.1:5173` | RepoGraph 可视化界面 |
| `http://127.0.0.1:8000/docs` | FastAPI Swagger 接口文档 |
| `http://127.0.0.1:8000/health/live` | 后端存活检查 |
| `http://127.0.0.1:8000/health` | 数据库、模型、Milvus、Neo4j 等健康检查 |
| `http://127.0.0.1:8000/mcp/` | MCP 工具服务端点 |

## 14. 使用仓库分析

1. 在左侧 `Git repository` 输入公开仓库 URL。
2. 可选填写分支；留空时使用仓库默认分支。
3. 点击“开始分析”。
4. 在右侧查看克隆、扫描和 Agent 执行进度。
5. 等待分析状态变为 `completed`。
6. 在 `Findings` 中查看问题分类、严重级别、证据、影响和修复建议。
7. 在 `Timeline` 中查看 Agent、MCP 工具和执行耗时。
8. 在 `Report` 中查看图文 HTML 报告，或下载 HTML/Markdown。

分析失败时不能把结果当作成功报告。失败原因会显示在页面和时间线中。

## 15. 使用 AI 助手

1. 完成一次仓库分析。
2. 点击顶栏的“AI 助手”。
3. 选择快捷问题，或直接输入自己的问题。
4. 查看 Agent 阶段和流式回答。
5. 展开“引用证据”查看回答使用的 Finding。
6. 点击“开启新对话”开始新的分析内会话。

AI 助手当前只能基于已有 Finding 回答。它不会直接读取完整仓库，也不会执行目标仓库代码。

适合的问题示例：

```text
总结这个项目最严重的三个问题
解释第一条安全问题的证据
按优先级生成修复计划
```

如果问题需要未写入 Finding 的具体函数实现，当前回答会提示证据不足。

## 16. 停止和重新启动

在运行 `dev.py` 的终端按：

```text
Ctrl+C
```

它会依次停止 React、FastAPI 和 MCP 服务。

如果端口被占用，先关闭之前的开发服务：

```powershell
netstat -ano | findstr :8000
netstat -ano | findstr :5173
```

然后根据 PID 关闭对应进程，或修改 `.env` 中的 `APP_PORT`。

仅前后端分开启动：

```powershell
python main.py
```

```powershell
cd frontend
npm run dev
```

## 17. 验证安装

后端检查：

```powershell
cd E:\Aipracite\py_workspace\Multiagent
python -m ruff check main.py dev.py app tests scripts
python -m mypy app tests dev.py
python -m pytest -q
```

前端检查：

```powershell
cd frontend
npm run build
```

服务健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/live
Invoke-RestMethod http://127.0.0.1:8000/health
```

## 18. 更新项目

更新前先提交或保存本地改动，并确认不需要保留正在运行的任务。

```powershell
cd E:\Aipracite\py_workspace\Multiagent
git status
git pull
```

如果依赖文件发生变化：

```powershell
conda activate multiagent
python -m pip install -r requirements-dev.txt
python -m pip check

cd frontend
npm ci
cd ..
```

数据库结构发生变化时，应先备份 PostgreSQL，再启动新版本。

## 19. 常见故障

### 19.1 未找到 Node.js

现象：

```text
未找到 Node.js，请先安装 Node.js
```

处理：

1. 安装 Node.js。
2. 重新打开终端。
3. 执行 `node --version` 和 `npm --version`。

### 19.2 `conda` 命令不可用

处理：

1. 从开始菜单打开 Anaconda Prompt 或 Miniconda Prompt。
2. 或先执行 `conda init powershell`，然后重新打开 PowerShell。
3. 也可以直接使用完整解释器路径启动项目。

### 19.3 前端依赖未安装

现象：

```text
前端依赖未安装，请先进入 frontend 执行 npm install
```

处理：

```powershell
cd frontend
npm ci
```

### 19.4 后端或前端端口被占用

现象：

```text
后端端口 8000 已被占用
前端端口 5173 已被占用
```

处理：

1. 停止之前的 `dev.py`。
2. 检查 `netstat` 中的占用进程。
3. 或修改 `.env` 中的 `APP_PORT` 和后端相关地址。

### 19.5 Git 克隆失败

检查：

```powershell
git --version
```

如果 Git 不在 `PATH` 中：

```dotenv
GIT_EXECUTABLE=C:\Program Files\Git\cmd\git.exe
```

同时确认：

- URL 是公开 HTTPS 地址。
- 主机在 `GIT_ALLOWED_HOSTS` 中。
- URL 没有包含用户名或密码。
- 网络可以访问 GitHub、GitLab 或 Gitee。

### 19.6 数据库连接失败

检查：

```powershell
Test-NetConnection 127.0.0.1 -Port 5432
```

确认 `.env` 中的数据库名、用户名和密码正确，并确认 `/health` 的 `database` 组件为 `ok`。

### 19.7 模型请求返回 401 或 403

常见原因：

- API Key 无效或已撤销。
- 免费额度耗尽。
- 模型名称与供应商不匹配。
- `.env.local` 覆盖了 `.env` 中的配置。

处理：

1. 检查当前 shell 和 `.env.local`。
2. 更新有效 API Key。
3. 重启后端。
4. 重新检查 `/health`。

### 19.8 Milvus 或 Neo4j 显示异常

它们目前不是基础分析和 Finding 聊天的必需依赖。

确认：

- 虚拟机可以访问。
- 19530 或 7687 端口已开放。
- Docker 容器正在运行。
- `.env` 中的主机、用户和密码正确。

### 19.9 聊天提示证据不足

当前 AI 助手只读取分析 Finding。若问题涉及未出现在 Finding 中的函数或文件，需要在后续版本接入按需 Milvus 代码索引。

## 20. 数据和工作区

主要数据位置：

| 数据 | 位置 |
| --- | --- |
| 业务数据 | PostgreSQL |
| Agent 图状态 | LangGraph checkpoint 表 |
| 克隆仓库 | `workspaces/repositories/{analysis_id}` |
| 报告和中间产物 | 对应分析工作区 |
| 前端依赖 | `frontend/node_modules` |

不要在分析运行期间手工修改 `workspaces` 中的文件。

## 21. 安全注意事项

- 不要把 `.env` 提交到 Git。
- 不要在聊天、截图或文档中公开真实 API Key。
- 不要将被审查仓库的凭据写入 Finding 或报告。
- 不执行目标仓库中的代码、脚本、测试或构建命令。
- 只允许公开的 HTTP/HTTPS Git 地址。
- 不要将本机开发用的 MCP 端点直接暴露到不可信网络。

## 22. 用户手册维护规则

以后更新项目时，如果发生以下变化，必须同步更新本手册：

- Python、Node.js、npm、Git 或数据库版本变化。
- Python 或前端依赖变化。
- `.env` 变量增加、删除或改名。
- 启动、停止或健康检查方式变化。
- 仓库分析或 AI 助手操作流程变化。
- 必需的第三方服务变化。
- 端口、访问地址或运行命令变化。
- 常见错误和处理方式变化。

维护者提交前应检查：

```text
1. USER_MANUAL.md 是否仍能按步骤完成全新安装。
2. README 的快速启动是否与手册一致。
3. 依赖和环境变量文档是否同步。
4. 示例中是否包含真实密钥。
5. 新功能是否补充了用户操作步骤。
```
