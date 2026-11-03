# React 可视化控制台

更新时间：2026-11-02

## 环境

- Node.js 24.16.0
- npm 11.13.0
- React 19.3.1
- React DOM 19.3.1
- TypeScript 7.0.2
- Vite 8.3.5
- `@vitejs/plugin-react` 6.2.1

前端代码位于 `frontend/`，依赖版本锁定在 `frontend/package-lock.json`。

## 启动

首次安装依赖后，可以在项目根目录同时启动前后端：

```powershell
cd frontend
npm install
cd ..
python dev.py
```

也可以分别启动。

先启动后端：

```powershell
& 'D:\itwork\itwork2026\app\Miniconda3\envs\multiagent\python.exe' -m scripts.run_api
```

再启动前端：

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173` 或 `http://127.0.0.1:5173`。前端默认连接当前主机的 `8000` 端口；可以用 `VITE_API_BASE_URL` 覆盖。

生产构建：

```powershell
npm run build
```

## 当前页面能力

- 查看 PostgreSQL、checkpoint、Milvus、Neo4j、Chat 和 Embedding 健康状态。
- 创建项目并输入开发需求。
- 查看项目运行历史。
- 启动主 Agent 运行。
- 在运行过程中点击“停止运行”，取消模型请求和 Maven 子进程。
- 通过 SSE 实时展示 Agent 事件。
- 空闲时不轮询运行状态，页面更新完全由 SSE 事件驱动。
- 显示主 Agent、PM、Architect、Coder、Tester、Reviewer 和 Doc 执行状态。
- 实时显示运行已耗时，完成后固定为最终耗时。
- 事件时间线显示相对运行开始的 `+时:分:秒`。
- 查看运行 Token 和当前 Agent。
- 浏览生成工程文件树。
- 查看 Java、Markdown、YAML 等文件内容。
- 查看生成工程初始 Diff。
- 下载完整工程 ZIP。

## CORS

开发环境允许：

```text
http://localhost:5173
http://127.0.0.1:5173
```

部署到其他域名时，需要同步修改 `.env` 中的 `FRONTEND_ORIGIN`。

## 日志

`.env` 默认设置：

```dotenv
UVICORN_ACCESS_LOG=false
```

这会关闭逐请求访问日志，保留应用启动、异常和 Agent 运行日志。如需调试 HTTP 请求，可改为 `true`。

## 当前限制

- 尚未实现代码编辑器和带行号的语法高亮。
- 尚未实现预算确认和人工审批按钮。
- 尚未实现 Milvus 检索结果和 Neo4j 依赖图可视化。
