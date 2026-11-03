"""RepoGraph 多 Agent Git 仓库静态审查平台。"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    # psycopg 异步连接不支持 Windows 默认的 ProactorEventLoop。
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
