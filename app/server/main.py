"""FastAPI 应用入口 — 创建应用实例、生命周期管理。

含 GPU 预热和 VLM/Embedding 客户端管理。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import load_config, init_config
from app.storage import get_storage, close_storage

logger = logging.getLogger(__name__)

# 全局采集任务句柄
_capture_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    config = load_config()
    storage = get_storage()
    storage.init_db()

    # GPU 预热（VLM 优先 → Embedding 后加载）
    vlm_ready = False
    emb_ready = False

    if config.models.vlm.enabled:
        from app.processing.vlm import warmup_vlm
        logger.info("预热 VLM 模型: %s ...", config.models.vlm.model)
        vlm_ready = await warmup_vlm(config)
        if vlm_ready:
            logger.info("VLM 预热成功")
        else:
            logger.warning("VLM 预热失败，将在 fallback 模式下运行")

    if config.models.embedding.enabled:
        from app.processing.embedding import warmup_embedding
        logger.info("预热 Embedding 模型: %s ...", config.models.embedding.model)
        emb_ready = await warmup_embedding(config)
        if emb_ready:
            logger.info("Embedding 预热成功")
        else:
            logger.warning("Embedding 预热失败，将使用 FTS5 检索")

    # 启动采集循环
    if config.capture.enabled:
        import asyncio
        from app.server.routes import capture_loop
        _capture_task = asyncio.create_task(capture_loop(config))
        logger.info("截图采集已启动，基准间隔 %ds", config.capture.interval_seconds)

    yield

    # 关闭时清理
    if _capture_task and not _capture_task.done():
        _capture_task.cancel()

    # 关闭 HTTP 客户端
    from app.processing.vlm import close_vlm_client
    from app.processing.embedding import close_embedding_client
    await close_vlm_client()
    await close_embedding_client()

    close_storage()


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    app = FastAPI(
        title="Hermes Context Memory",
        description="本地上下文记忆服务",
        version="0.2.0",
        lifespan=lifespan,
    )

    from app.server.routes import router
    app.include_router(router)

    # CORS：允许浏览器扩展和本地开发访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 本地服务，允许所有来源
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app


# ASGI 入口
app = create_app()
