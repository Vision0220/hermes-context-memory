"""Embedding 模块 — 使用 OpenAI-compatible API 生成文本向量。

含连接池、重试逻辑、批量支持、GPU 预热。
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

import httpx

from app.config import AppConfig

logger = logging.getLogger(__name__)

# ── 连接池 ──────────────────────────────────────────────────────

_emb_client: Optional[httpx.AsyncClient] = None


def get_embedding_client(config: AppConfig) -> httpx.AsyncClient:
    """获取共享的 Embedding HTTP 客户端。"""
    global _emb_client
    if _emb_client is None:
        _emb_client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.models.embedding.timeout, connect=10.0),
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
            verify=False,
        )
    return _emb_client


async def close_embedding_client():
    """关闭 Embedding HTTP 客户端。"""
    global _emb_client
    if _emb_client:
        await _emb_client.aclose()
        _emb_client = None


# ── GPU 预热 ────────────────────────────────────────────────────

async def warmup_embedding(config: AppConfig) -> bool:
    """预热 Embedding 模型。

    Returns:
        True 如果预热成功。
    """
    emb_config = config.models.embedding
    if not emb_config.enabled:
        logger.info("Embedding 未启用，跳过预热")
        return False

    try:
        client = get_embedding_client(config)
        response = await client.post(
            f"{emb_config.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {emb_config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": emb_config.model,
                "input": "test",
            },
        )
        response.raise_for_status()
        data = response.json()
        dim = len(data["data"][0]["embedding"])
        logger.info("Embedding 预热成功: model=%s, dim=%d", emb_config.model, dim)
        return True
    except Exception as e:
        logger.warning("Embedding 预热失败: %s", e)
        return False


# ── 单条 Embedding ──────────────────────────────────────────────

async def get_embedding(text: str, config: AppConfig) -> Optional[List[float]]:
    """获取单条文本的向量。含重试。"""
    emb_config = config.models.embedding
    if not emb_config.enabled:
        return None

    client = get_embedding_client(config)
    for attempt in range(emb_config.retry_count + 1):
        try:
            response = await client.post(
                f"{emb_config.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {emb_config.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": emb_config.model,
                    "input": text[:8000],
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
        except Exception as e:
            if attempt < emb_config.retry_count:
                wait = 2 ** attempt
                logger.warning("Embedding 调用失败 (attempt %d): %s, 等待 %ds",
                               attempt + 1, e, wait)
                await asyncio.sleep(wait)
            else:
                logger.error("Embedding 调用最终失败: %s", e)
    return None


# ── 批量 Embedding ──────────────────────────────────────────────

async def get_embeddings_batch(
    texts: List[str],
    config: AppConfig,
) -> List[Optional[List[float]]]:
    """批量获取文本向量。OpenAI embedding API 支持数组输入。"""
    emb_config = config.models.embedding
    if not emb_config.enabled:
        return [None] * len(texts)

    client = get_embedding_client(config)
    for attempt in range(emb_config.retry_count + 1):
        try:
            response = await client.post(
                f"{emb_config.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {emb_config.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": emb_config.model,
                    "input": [t[:8000] for t in texts],
                },
            )
            response.raise_for_status()
            data = response.json()
            results = [None] * len(texts)
            for item in data["data"]:
                idx = item["index"]
                results[idx] = item["embedding"]
            return results
        except Exception as e:
            if attempt < emb_config.retry_count:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error("批量 Embedding 失败: %s", e)
    return [None] * len(texts)


# ── 同步版本 ────────────────────────────────────────────────────

def get_embedding_sync(text: str, config: AppConfig) -> Optional[List[float]]:
    """同步版本。"""
    if not config.models.embedding.enabled:
        return None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        return None
    return asyncio.run(get_embedding(text, config))
