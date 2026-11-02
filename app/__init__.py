"""多 Agent 软件开发协作平台后端。"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    # psycopg 异步连接不支持 Windows 默认的 ProactorEventLoop。
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
