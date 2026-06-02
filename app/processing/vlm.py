"""VLM 摘要模块 — 使用 OpenAI-compatible API 分析截图生成结构化摘要。

支持本地 LM Studio / vLLM / Ollama 等 OpenAI-compatible 端点。
含连接池、重试逻辑、GPU 预热。
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
from pathlib import Path
from typing import Optional

import httpx

from app.config import AppConfig
from app.models import VLMSummary

logger = logging.getLogger(__name__)

# ── 连接池 ──────────────────────────────────────────────────────

_vlm_client: Optional[httpx.AsyncClient] = None


def get_vlm_client(config: AppConfig) -> httpx.AsyncClient:
    """获取共享的 VLM HTTP 客户端（连接池复用）。"""
    global _vlm_client
    if _vlm_client is None:
        # 自签名证书：verify=False
        _vlm_client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.models.vlm.timeout, connect=10.0),
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
            verify=False,
        )
    return _vlm_client


async def close_vlm_client():
    """关闭 VLM HTTP 客户端。"""
    global _vlm_client
    if _vlm_client:
        await _vlm_client.aclose()
        _vlm_client = None


# ── VLM 提示词 ──────────────────────────────────────────────────

VLM_PROMPT = """你是本地屏幕上下文分析器。请只基于截图内容输出 JSON，不要编造。字段：
- app_or_website
- page_title_or_document
- visible_task
- key_entities
- possible_intent
- useful_facts
- sensitive_content: true/false
- summary_zh: 一句话中文摘要"""


# ── GPU 预热 ────────────────────────────────────────────────────

async def warmup_vlm(config: AppConfig) -> bool:
    """预热 VLM 模型：发送一个小测试请求确保模型加载到 GPU。

    Returns:
        True 如果预热成功（API 可达且返回有效响应）。
    """
    vlm_config = config.models.vlm
    if not vlm_config.enabled:
        logger.info("VLM 未启用，跳过预热")
        return False

    try:
        # 生成 64x64 白色 JPEG 作为测试图片
        from PIL import Image
        img = Image.new("RGB", (64, 64), (255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=50)
        img_b64 = base64.b64encode(buf.getvalue()).decode()

        client = get_vlm_client(config)
        response = await client.post(
            f"{vlm_config.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {vlm_config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": vlm_config.model,
                "messages": [
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                        {"type": "text", "text": "请回复 ok"},
                    ]},
                ],
                "max_tokens": 10,
                "temperature": 0,
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        logger.info("VLM 预热成功: model=%s, response=%s", vlm_config.model, content[:50])
        return True
    except Exception as e:
        logger.warning("VLM 预热失败: %s", e)
        return False


# ── VLM 分析 ────────────────────────────────────────────────────

async def analyze_screenshot(
    image_path: Path,
    config: AppConfig,
    app_name: str = "",
    window_title: str = "",
    ocr_text: str = "",
) -> Optional[VLMSummary]:
    """使用 VLM 分析截图，返回结构化摘要。含重试逻辑。"""
    vlm_config = config.models.vlm

    if not vlm_config.enabled:
        return _fallback_summary(app_name, window_title, ocr_text)

    # 读取并可能缩放图片
    image_data = _prepare_image(image_path, config.capture.vlm_max_width)
    if not image_data:
        return _fallback_summary(app_name, window_title, ocr_text)

    image_b64 = base64.b64encode(image_data).decode("utf-8")

    messages = [
        {"role": "system", "content": VLM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                {"type": "text", "text": f"当前应用: {app_name}\n窗口标题: {window_title}\nOCR文本: {ocr_text[:500]}"},
            ],
        },
    ]

    # 带重试的 API 调用
    client = get_vlm_client(config)
    last_error = None
    for attempt in range(vlm_config.retry_count + 1):
        try:
            response = await client.post(
                f"{vlm_config.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {vlm_config.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": vlm_config.model,
                    "messages": messages,
                    "max_tokens": vlm_config.max_tokens,
                    "temperature": vlm_config.temperature,
                },
            )
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"]
            json_str = _extract_json(content)
            if json_str:
                parsed = json.loads(json_str)
                return VLMSummary(**parsed)
            else:
                return VLMSummary(summary_zh=content[:200])

        except Exception as e:
            last_error = e
            if attempt < vlm_config.retry_count:
                wait = 2 ** attempt  # 1s, 2s, 4s
                logger.warning("VLM 调用失败 (attempt %d/%d): %s, 等待 %ds 重试",
                               attempt + 1, vlm_config.retry_count + 1, e, wait)
                await asyncio.sleep(wait)

    logger.error("VLM 调用最终失败: %s", last_error)
    return _fallback_summary(app_name, window_title, ocr_text)


def _prepare_image(image_path: Path, max_width: int) -> Optional[bytes]:
    """读取图片，按需缩放，返回 JPEG bytes。"""
    try:
        from PIL import Image
        img = Image.open(str(image_path))
        img.load()

        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        return buf.getvalue()
    except Exception as e:
        logger.warning("图片预处理失败: %s", e)
        return None


def _extract_json(text: str) -> Optional[str]:
    """从文本中提取 JSON 字符串。"""
    text = text.strip()
    if text.startswith("{"):
        return text
    import re
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # 尝试找第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return None


def _fallback_summary(app_name: str, window_title: str, ocr_text: str) -> VLMSummary:
    """VLM 不可用时的 fallback 摘要。"""
    parts = []
    if app_name:
        parts.append(f"应用: {app_name}")
    if window_title:
        parts.append(f"窗口: {window_title}")
    if ocr_text:
        parts.append(f"内容: {ocr_text[:200]}")
    summary = " | ".join(parts) if parts else "无可用摘要"
    return VLMSummary(
        app_or_website=app_name,
        page_title_or_document=window_title,
        summary_zh=summary,
    )


# ── 同步版本 ────────────────────────────────────────────────────

def analyze_screenshot_sync(
    image_path: Path,
    config: AppConfig,
    app_name: str = "",
    window_title: str = "",
    ocr_text: str = "",
) -> Optional[VLMSummary]:
    """同步版本的截图分析。"""
    vlm_config = config.models.vlm
    if not vlm_config.enabled:
        return _fallback_summary(app_name, window_title, ocr_text)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # 在已有事件循环中（如 FastAPI），用 fallback
        return _fallback_summary(app_name, window_title, ocr_text)
    return asyncio.run(analyze_screenshot(image_path, config, app_name, window_title, ocr_text))
