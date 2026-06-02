"""OCR 模块 — 可插拔的 OCR 引擎接口。

默认为 no-op fallback（返回空字符串）。
用户可通过配置启用 RapidOCR 或 PaddleOCR。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


class OCREngine(Protocol):
    """OCR 引擎接口。"""
    def extract_text(self, image_path: Path) -> str: ...


class NoopOCR:
    """无操作 OCR — 始终返回空字符串。当 OCR 库不可用时使用。"""

    def extract_text(self, image_path: Path) -> str:
        return ""


class RapidOCREngine:
    """RapidOCR 引擎。需要安装 rapidocr-onnxruntime。"""

    def __init__(self):
        try:
            from rapidocr_onnxruntime import RapidOCR
            self._ocr = RapidOCR()
        except ImportError:
            raise ImportError(
                "RapidOCR 不可用。请安装: uv pip install rapidocr-onnxruntime"
            )

    def extract_text(self, image_path: Path) -> str:
        try:
            result, _ = self._ocr(str(image_path))
            if result:
                # result 是列表，每个元素是 [[坐标], (文本, 置信度)]
                texts = []
                for item in result:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        text_part = item[1]
                        if isinstance(text_part, (list, tuple)):
                            texts.append(str(text_part[0]))
                        else:
                            texts.append(str(text_part))
                return "\n".join(texts)
            return ""
        except Exception as e:
            logger.warning(f"OCR 提取失败: {e}")
            return ""


def get_ocr_engine(engine_name: str = "noop") -> OCREngine:
    """获取 OCR 引擎实例。

    Args:
        engine_name: 引擎名称，支持 "noop", "rapid", "paddle"。
    """
    if engine_name == "rapid":
        try:
            return RapidOCREngine()
        except ImportError:
            logger.warning("RapidOCR 不可用，退化为 no-op")
            return NoopOCR()
    elif engine_name == "paddle":
        # TODO: 实现 PaddleOCR 引擎
        logger.warning("PaddleOCR 暂未实现，退化为 no-op")
        return NoopOCR()
    else:
        return NoopOCR()
