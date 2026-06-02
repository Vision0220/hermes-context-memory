"""去重模块 — 基于图像哈希判断截图是否重复。"""

from __future__ import annotations

from typing import Optional


class Deduplicator:
    """截图去重器。

    使用感知哈希（phash）判断两张截图是否"高度相似"。
    相似阈值可通过 hamming_distance 控制。
    """

    def __init__(self, hamming_distance: int = 5):
        """
        Args:
            hamming_distance: 哈希距离阈值。<=此值视为相同。默认 5。
        """
        self.hamming_distance = hamming_distance
        self._last_hash: Optional[str] = None

    def is_duplicate(self, image_hash: Optional[str]) -> bool:
        """判断当前截图是否与上一张重复。

        Args:
            image_hash: 当前截图的感知哈希（十六进制字符串）。

        Returns:
            True 如果与上一张高度相似。
        """
        if image_hash is None or self._last_hash is None:
            self._last_hash = image_hash
            return False

        try:
            import imagehash
            h1 = imagehash.hex_to_hash(self._last_hash)
            h2 = imagehash.hex_to_hash(image_hash)
            distance = h1 - h2
            is_dup = distance <= self.hamming_distance
            # 只有不重复时才更新 last_hash，确保连续重复都被捕获
            if not is_dup:
                self._last_hash = image_hash
            return is_dup
        except (ImportError, ValueError):
            # imagehash 不可用或哈希格式不对，退化为字符串比较
            is_dup = self._last_hash == image_hash
            if not is_dup:
                self._last_hash = image_hash
            return is_dup

    def reset(self):
        """重置去重器状态。"""
        self._last_hash = None
