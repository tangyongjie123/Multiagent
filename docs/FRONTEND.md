# 前端控制台

更新时间：2026-11-03

## 1. 设计方向

前端采用偏编辑设计和技术工作台的视觉语言：

- 浅灰网格背景与高对比黑色排版。
- 荧光绿作为运行中和关键数字的强调色。
- 等宽字体显示 URL、Commit、事件类型和文件位置。
- 左右分栏：左侧创建与仓库历史，右侧展示当前分析。
- 问题卡片按严重级别使用颜色边界，强调证据和修复建议。
- 无大型 UI 框架，减少体积并保持视觉一致。

界面默认中文，代码字段、事件类型和环境变量保留英文。

## 2. 技术栈

| 项目 | 版本 |
| --- | --- |
| Node.js | 24.16.0 |
| npm | 11.13.0 |
| React | 19.3.1 |
| React DOM | 19.3.1 |
| TypeScript | 7.0.2 |
| Vite | 8.3.5 |
| `@vitejs/plugin-react` | 6.2.1 |

依赖锁定在 `frontend/package-lock.json`。

## 3. 启动

同时启动前后端：

```powershell
cd E:\Aipracite\py_workspace\Multiagent
python dev.py
```

打开 `http://127.0.0.1:5173`。按 `Ctrl+C` 会同时停止 Vite 和 FastAPI。

`dev.py` 会在控制台用中文依次显示 Python/Node 环境检查、FastAPI、MCP、React、健康检查和最终访问地址，并在退出时显示服务关闭过程。前端固定使用 5173 端口，端口被占用时会给出明确错误。

单独启动：

```powershell
cd frontend
npm run dev
```

生产构建：

```powershell
cd frontend
npm run build
```

构建产物写入 `frontend/dist/`，该目录不提交 Git。

## 4. 页面能力

### 新建分析

- 输入公开 Git URL。
- 可选指定分支。
- 校验失败时展示后端返回的中文错误。
- 创建成功后立即开始分析并进入实时视图。

### 仓库与历史

- 左侧显示提交过的仓库。
- 选择仓库后加载分析历史。
- 点击历史运行恢复状态、事件、问题和报告。
- 支持对同一仓库重新分析。

### 状态概览

- 分析状态。
- 当前 Agent。
- 实时运行耗时。
- 问题数量。
- Commit 和分支。
- PostgreSQL、checkpoint、Milvus、Neo4j、LLM 和 Embedding 状态。

### Agent 进度

展示主 Agent、Repository、Architecture、Test、Security、Quality 和 Report。事件完成后更新节点状态。

### 问题列表

- 按 critical、major、minor、info 统计和筛选。
- 展示分类、文件与行号、标题、证据、影响和建议。

### 时间线

- 按事件序号展示真实运行事件。
- 显示相对开始时间、Agent、事件类型和中文消息。
- 展示 `tool.started`、`tool.completed` 和 `tool.failed` MCP 工具事件。
- 使用 SSE 增量更新，不进行高频状态轮询。

### 报告

- 在线查看 Markdown 原文。
- 分析完成后，页面顶部和报告页都提供“下载报告”按钮。
- 下载接口返回 `Content-Disposition: attachment`，文件名为 `仓库名-分析ID-report.md`。
- 文件名只保留安全字符，报告文件必须位于对应分析工作区。
- 分析失败或取消时不提供成功报告。

## 5. API 连接

开发模式默认请求当前主机的 `8000` 端口。可以通过 Vite 环境变量覆盖：

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

后端允许的来源由 `FRONTEND_ORIGIN` 控制：

```dotenv
FRONTEND_ORIGIN=http://localhost:5173,http://127.0.0.1:5173
```

## 6. 日志与停止

`.env` 默认关闭逐请求访问日志：

```dotenv
UVICORN_ACCESS_LOG=false
```

应用启动、异常和关键服务状态仍会输出；`httpx` 和 `httpcore` 的逐请求信息被降到警告级别。页面上的“停止”按钮只取消当前分析，不会退出服务。

## 7. 当前限制

- Markdown 报告以 `<pre>` 展示，尚未接入 Markdown 渲染和代码高亮。
- 尚未实现 Neo4j 依赖图可视化和 Milvus 相似片段面板。
- 尚未实现登录、多用户和仓库权限隔离。
- 当前轮询间隔由后端 SSE 实现控制，前端不使用 WebSocket。
