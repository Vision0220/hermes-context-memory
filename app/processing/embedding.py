"""Embedding 模块 — 使用 OpenAI-compatible API 生成文本向量。

不可用时提供文本 fallback（返回空向量，退化为纯 FTS 检索）。
"""

from __future__ import annotations

import logging
from typing import List, Optional

import httpx

from app.config import AppConfig

logger = logging.getLogger(__name__)


async def get_embedding(text: str, config: AppConfig) -> Optional[List[float]]:
    """使用 Embedding API 获取文本的向量表示。

    如果 API 不可用，返回 None（调用方退化为 FTS 检索）。
    """
    emb_config = config.models.embedding

    if not emb_config.enabled:
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{emb_config.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {emb_config.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": emb_config.model,
                    "input": text[:8000],  # 截断超长文本
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]

    except Exception as e:
        logger.warning(f"Embedding API 不可用: {e}")
        return None


def get_embedding_sync(text: str, config: AppConfig) -> Optional[List[float]]:
    """同步版本的 embedding 获取，用于 CLI。"""
    emb_config = config.models.embedding
    if not emb_config.enabled:
        return None
    try:
        import asyncio
        return asyncio.run(get_embedding(text, config))
    except Exception as e:
        logger.warning(f"Embedding 同步调用失败: {e}")
        return None
