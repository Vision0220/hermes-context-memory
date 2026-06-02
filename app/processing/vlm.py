"""VLM 摘要模块 — 使用 OpenAI-compatible API 分析截图生成结构化摘要。

支持本地 LM Studio / vLLM / Ollama 等 OpenAI-compatible 端点。
VLM 不可用时提供 fallback 摘要。
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Optional

import httpx

from app.config import AppConfig
from app.models import VLMSummary

logger = logging.getLogger(__name__)

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


# ── VLM 调用 ────────────────────────────────────────────────────

async def analyze_screenshot(
    image_path: Path,
    config: AppConfig,
    app_name: str = "",
    window_title: str = "",
    ocr_text: str = "",
) -> Optional[VLMSummary]:
    """使用 VLM 分析截图，返回结构化摘要。

    如果 VLM 不可用，返回 fallback 摘要。
    """
    vlm_config = config.models.vlm

    if not vlm_config.enabled:
        return _fallback_summary(app_name, window_title, ocr_text)

    try:
        # 读取图片并 base64 编码
        image_data = image_path.read_bytes()
        image_b64 = base64.b64encode(image_data).decode("utf-8")

        messages = [
            {"role": "system", "content": VLM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_b64}",
                        },
                    },
                    {
                        "type": "text",
                        "text": f"当前应用: {app_name}\n窗口标题: {window_title}\nOCR文本: {ocr_text[:500]}",
                    },
                ],
            },
        ]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{vlm_config.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {vlm_config.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": vlm_config.model,
                    "messages": messages,
                    "max_tokens": 1024,
                    "temperature": 0.1,
                },
            )
            response.raise_for_status()
            data = response.json()

        # 解析 VLM 返回的 JSON
        content = data["choices"][0]["message"]["content"]
        # 尝试提取 JSON（可能被 markdown 包裹）
        json_str = _extract_json(content)
        if json_str:
            parsed = json.loads(json_str)
            return VLMSummary(**parsed)
        else:
            # 无法解析 JSON，用原始文本作为摘要
            return VLMSummary(summary_zh=content[:200])

    except Exception as e:
        logger.warning(f"VLM 分析失败: {e}")
        return _fallback_summary(app_name, window_title, ocr_text)


def _extract_json(text: str) -> Optional[str]:
    """从文本中提取 JSON 字符串（处理 markdown 代码块等情况）。"""
    # 尝试直接解析
    text = text.strip()
    if text.startswith("{"):
        return text

    # 尝试从 ```json ... ``` 中提取
    import re
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    return None


def _fallback_summary(app_name: str, window_title: str, ocr_text: str) -> VLMSummary:
    """VLM 不可用时的 fallback 摘要。"""
    parts = []
    if app_name:
        parts.append(f"应用: {app_name}")
    if window_title:
        parts.append(f"窗口: {window_title}")
    if ocr_text:
        # 截取前 200 字
        parts.append(f"内容: {ocr_text[:200]}")

    summary = " | ".join(parts) if parts else "无可用摘要"
    return VLMSummary(
        app_or_website=app_name,
        page_title_or_document=window_title,
        summary_zh=summary,
    )


# ── 同步版本（用于 CLI） ────────────────────────────────────────

def analyze_screenshot_sync(
    image_path: Path,
    config: AppConfig,
    app_name: str = "",
    window_title: str = "",
    ocr_text: str = "",
) -> Optional[VLMSummary]:
    """同步版本的截图分析，用于 CLI 场景。"""
    vlm_config = config.models.vlm

    if not vlm_config.enabled:
        return _fallback_summary(app_name, window_title, ocr_text)

    try:
        import asyncio
        return asyncio.run(analyze_screenshot(image_path, config, app_name, window_title, ocr_text))
    except Exception as e:
        logger.warning(f"VLM 同步调用失败: {e}")
        return _fallback_summary(app_name, window_title, ocr_text)
