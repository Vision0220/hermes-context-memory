"""瓦片处理模块 — 高分辨率截图分块、变化检测、重要性排序。

对于 5120x2160 等高分辨率截图：
1. 生成 overview（缩放到 vlm_max_width）
2. 将原图分为 tile_width x tile_height 的瓦片（含重叠）
3. 检测变化瓦片（与上一帧比较）
4. 计算文本密度（边缘检测）
5. 选择最重要的瓦片送 VLM
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)


@dataclass
class TileInfo:
    """单个瓦片的元数据。"""
    tile_id: int = 0
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    tile_path: Optional[str] = None
    tile_hash: Optional[str] = None
    text_density: float = 0.0
    changed_score: float = 0.0
    ocr_text: Optional[str] = None
    vlm_summary: Optional[str] = None
    reused_from_tile_id: Optional[int] = None


class TileProcessor:
    """瓦片处理器 — 将大图分块、检测变化、选择重要瓦片。"""

    def __init__(
        self,
        tile_width: int = 1280,
        tile_height: int = 720,
        overlap: int = 64,
        change_threshold: float = 0.15,
        min_tile_size: int = 200,
    ):
        self.tile_width = tile_width
        self.tile_height = tile_height
        self.overlap = overlap
        self.change_threshold = change_threshold
        self.min_tile_size = min_tile_size

    def should_tile(self, img: Image.Image) -> bool:
        """判断图片是否需要分块处理。"""
        w, h = img.size
        # 如果图片大于单个瓦片的 1.5 倍，需要分块
        return w > self.tile_width * 1.5 or h > self.tile_height * 1.5

    def generate_tiles(self, img: Image.Image) -> List[TileInfo]:
        """将图片分块，返回瓦片信息列表。"""
        img_w, img_h = img.size
        tiles: List[TileInfo] = []
        tile_id = 0

        step_x = max(self.tile_width - self.overlap, self.min_tile_size)
        step_y = max(self.tile_height - self.overlap, self.min_tile_size)

        y = 0
        while y < img_h:
            x = 0
            while x < img_w:
                right = min(x + self.tile_width, img_w)
                bottom = min(y + self.tile_height, img_h)
                tw = right - x
                th = bottom - y

                if tw >= self.min_tile_size and th >= self.min_tile_size:
                    tiles.append(TileInfo(
                        tile_id=tile_id,
                        x=x, y=y,
                        width=tw, height=th,
                    ))
                    tile_id += 1

                if right >= img_w:
                    break
                x += step_x

            if bottom >= img_h:
                break
            y += step_y

        return tiles

    def crop_tile(self, tile: TileInfo, img: Image.Image) -> Image.Image:
        """从原图中裁剪出瓦片。"""
        box = (tile.x, tile.y, tile.x + tile.width, tile.y + tile.height)
        return img.crop(box)

    def compute_text_density(self, tile: TileInfo, img: Image.Image) -> float:
        """计算瓦片的文本密度（基于边缘检测）。"""
        cropped = self.crop_tile(tile, img)
        # 转灰度
        gray = cropped.convert("L")
        # 边缘检测
        edges = gray.filter(ImageFilter.FIND_EDGES)
        arr = np.array(edges)
        # 边缘像素占比作为文本密度
        threshold = 50
        edge_pixels = np.sum(arr > threshold)
        total_pixels = arr.size
        density = edge_pixels / total_pixels if total_pixels > 0 else 0.0
        tile.text_density = round(density, 4)
        return tile.text_density

    def compute_tile_hash(self, tile: TileInfo, img: Image.Image) -> str:
        """计算瓦片的感知哈希。"""
        cropped = self.crop_tile(tile, img)
        # 缩小到 16x16 算 MD5
        small = cropped.resize((16, 16), Image.NEAREST)
        h = hashlib.md5(small.tobytes()).hexdigest()
        tile.tile_hash = h
        return h

    def detect_changes(
        self,
        current_tiles: List[TileInfo],
        prev_tiles: List[TileInfo],
    ) -> List[TileInfo]:
        """检测当前帧与上一帧的瓦片变化。

        通过 tile_hash 比较，返回更新了 changed_score 的瓦片列表。
        """
        prev_hashes = {}
        for pt in prev_tiles:
            if pt.tile_hash:
                prev_hashes[pt.tile_id] = pt.tile_hash

        for tile in current_tiles:
            if not tile.tile_hash:
                tile.changed_score = 1.0  # 无哈希 = 视为变化
                continue

            prev_hash = prev_hashes.get(tile.tile_id)
            if prev_hash is None:
                tile.changed_score = 1.0  # 上一帧无此瓦片
            elif prev_hash == tile.tile_hash:
                tile.changed_score = 0.0  # 完全相同
            else:
                # 用汉明距离估算变化程度（简化：不同=有变化）
                tile.changed_score = 1.0

        return current_tiles

    def select_important_tiles(
        self,
        tiles: List[TileInfo],
        max_tiles: int = 6,
    ) -> List[TileInfo]:
        """选择最重要的瓦片（变化大 + 文本密集）。

        综合评分 = changed_score * 0.6 + text_density * 0.4
        """
        for tile in tiles:
            tile.changed_score = tile.changed_score * 0.6 + tile.text_density * 0.4

        # 按综合分数降序排列
        sorted_tiles = sorted(tiles, key=lambda t: t.changed_score, reverse=True)
        return sorted_tiles[:max_tiles]

    def save_tiles(
        self,
        tiles: List[TileInfo],
        img: Image.Image,
        save_dir: Path,
    ) -> List[TileInfo]:
        """保存瓦片图片到磁盘。"""
        save_dir.mkdir(parents=True, exist_ok=True)
        for tile in tiles:
            cropped = self.crop_tile(tile, img)
            filename = f"tile_{tile.tile_id:03d}.jpg"
            path = save_dir / filename
            cropped.save(str(path), "JPEG", quality=80)
            tile.tile_path = str(path)
            self.compute_tile_hash(tile, img)
        return tiles

    def create_overview(self, img: Image.Image, max_width: int = 2048) -> Image.Image:
        """创建 overview 缩略图。"""
        if img.width <= max_width:
            return img.copy()
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        return img.resize((max_width, new_height), Image.LANCZOS)
