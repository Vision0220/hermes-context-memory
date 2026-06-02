"""FastAPI 应用入口 — 创建应用实例、生命周期管理。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import load_config, init_config
from app.storage import get_storage, close_storage

logger = logging.getLogger(__name__)

# 全局采集任务句柄
_capture_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 — 启动时初始化数据库，关闭时清理资源。"""
    config = load_config()
    storage = get_storage()
    storage.init_db()

    # 如果配置了采集，启动后台采集循环
    if config.capture.enabled:
        import asyncio
        from app.server.routes import capture_loop
        _capture_task = asyncio.create_task(capture_loop(config))
        logger.info("截图采集已启动，间隔 %d 秒", config.capture.interval_seconds)

    yield

    # 关闭时清理
    if _capture_task and not _capture_task.done():
        _capture_task.cancel()
    close_storage()


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    app = FastAPI(
        title="Hermes Context Memory",
        description="本地上下文记忆服务 — 让 Hermes Agent 记住你看过什么",
        version="0.1.0",
        lifespan=lifespan,
    )

    from app.server.routes import router
    app.include_router(router)

    return app


# ASGI 入口
app = create_app()
