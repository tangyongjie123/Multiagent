"""应用 API 路由汇总。"""

from fastapi import APIRouter

from app.api.routes import analyses, chat, health, repositories

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(repositories.router)
api_router.include_router(analyses.router)
api_router.include_router(chat.router)
