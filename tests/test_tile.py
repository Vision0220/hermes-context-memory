"""瓦片处理测试 — 高分辨率截图分块、变化检测、VLM 分析。"""

import tempfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.capture.tile import TileProcessor, TileInfo


@pytest.fixture
def tile_processor():
    """创建瓦片处理器。"""
    return TileProcessor(
        tile_width=640,
        tile_height=360,
        overlap=64,
        change_threshold=0.15,
    )


@pytest.fixture
def large_image():
    """创建合成大图 (2560x1440)。"""
    img = Image.new("RGB", (2560, 1440), (200, 200, 200))
    draw = ImageDraw.Draw(img)
    # 左上区域：文本密集区
    for y in range(0, 400, 20):
        draw.text((50, y), f"Line {y}: This is important text content", fill=(0, 0, 0))
    # 右下区域：另一个文本区
    for y in range(1000, 1400, 20):
        draw.text((1400, y), f"Section {y}: More document content here", fill=(0, 0, 0))
    # 中间区域：空白
    return img


@pytest.fixture
def small_image():
    """创建小图 (400x300)，不应被分块。"""
    return Image.new("RGB", (400, 300), (255, 255, 255))


class TestTileProcessor:
    """测试瓦片处理器核心功能。"""

    def test_should_tile_large_image(self, tile_processor, large_image):
        """大图应被分块。"""
        assert tile_processor.should_tile(large_image) is True

    def test_should_not_tile_small_image(self, tile_processor, small_image):
        """小图不应被分块。"""
        assert tile_processor.should_tile(small_image) is False

    def test_generate_tiles(self, tile_processor, large_image):
        """大图应生成多个瓦片。"""
        tiles = tile_processor.generate_tiles(large_image)
        assert len(tiles) > 1
        # 应该有行 x 列个瓦片
        assert len(tiles) >= 4  # 至少 2x2

    def test_tile_dimensions(self, tile_processor, large_image):
        """每个瓦片应有正确的尺寸和位置。"""
        tiles = tile_processor.generate_tiles(large_image)
        for tile in tiles:
            assert isinstance(tile, TileInfo)
            assert tile.width > 0
            assert tile.height > 0
            assert tile.x >= 0
            assert tile.y >= 0

    def test_tile_covers_full_image(self, tile_processor, large_image):
        """瓦片应覆盖整个图片（含重叠）。"""
        tiles = tile_processor.generate_tiles(large_image)
        # 检查所有区域都被覆盖
        img_w, img_h = large_image.size
        covered = set()
        for tile in tiles:
            for x in range(tile.x, min(tile.x + tile.width, img_w)):
                for y in range(tile.y, min(tile.y + tile.height, img_h)):
                    covered.add((x // 100, y // 100))  # 100px 粒度
        # 大部分区域应被覆盖
        total_cells = (img_w // 100) * (img_h // 100)
        assert len(covered) >= total_cells * 0.8


class TestTileChangeDetection:
    """测试瓦片变化检测。"""

    def test_changed_tile_detected(self, tile_processor, large_image):
        """变化的瓦片应被检测到。"""
        tiles = tile_processor.generate_tiles(large_image)
        # 计算当前帧哈希
        for tile in tiles:
            tile_processor.compute_tile_hash(tile, large_image)
        # 创建上一帧（空白）并计算哈希
        prev = Image.new("RGB", large_image.size, (200, 200, 200))
        prev_tiles = tile_processor.generate_tiles(prev)
        for tile in prev_tiles:
            tile_processor.compute_tile_hash(tile, prev)

        changed = tile_processor.detect_changes(tiles, prev_tiles)
        assert any(t.changed_score > 0 for t in changed)

    def test_unchanged_tile_not_detected(self, tile_processor):
        """相同的瓦片不应标记为变化。"""
        img = Image.new("RGB", (2560, 1440), (128, 128, 128))
        tiles = tile_processor.generate_tiles(img)
        for tile in tiles:
            tile_processor.compute_tile_hash(tile, img)
        prev_tiles = tile_processor.generate_tiles(img)
        for tile in prev_tiles:
            tile_processor.compute_tile_hash(tile, img)

        changed = tile_processor.detect_changes(tiles, prev_tiles)
        # 相同图片的 changed_score 应为 0
        assert all(t.changed_score == 0.0 for t in changed)

    def test_select_important_tiles(self, tile_processor, large_image):
        """应优先选择变化大/文本密集的瓦片。"""
        tiles = tile_processor.generate_tiles(large_image)
        prev = Image.new("RGB", large_image.size, (200, 200, 200))
        prev_tiles = tile_processor.generate_tiles(prev)
        changed = tile_processor.detect_changes(tiles, prev_tiles)

        important = tile_processor.select_important_tiles(changed, max_tiles=3)
        assert len(important) <= 3
        # 按 changed_score 降序
        scores = [t.changed_score for t in important]
        assert scores == sorted(scores, reverse=True)


class TestTileTextDensity:
    """测试瓦片文本密度检测。"""

    def test_text_dense_tile(self, tile_processor, large_image):
        """有文本的瓦片应有较高文本密度。"""
        tiles = tile_processor.generate_tiles(large_image)
        for tile in tiles:
            tile_processor.compute_text_density(tile, large_image)
        # 左上角瓦片应有较高密度
        top_left = [t for t in tiles if t.x < 100 and t.y < 100]
        if top_left:
            assert top_left[0].text_density > 0.0

    def test_blank_tile_low_density(self, tile_processor):
        """空白瓦片应有低文本密度。"""
        img = Image.new("RGB", (2560, 1440), (200, 200, 200))
        tiles = tile_processor.generate_tiles(img)
        for tile in tiles:
            tile_processor.compute_text_density(tile, img)
        assert all(t.text_density < 0.3 for t in tiles)


class TestTileSave:
    """测试瓦片保存。"""

    def test_save_tiles(self, tile_processor, large_image):
        """瓦片应能保存为文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tiles = tile_processor.generate_tiles(large_image)
            saved = tile_processor.save_tiles(tiles, large_image, Path(tmpdir))
            assert len(saved) == len(tiles)
            for tile in saved:
                assert tile.tile_path is not None
                assert Path(tile.tile_path).exists()
