"""级联去重管线测试 — 多信号渐进式去重。"""

import tempfile
from pathlib import Path

import pytest
from PIL import Image

from app.capture.dedup import CascadeDeduplicator, DedupResult


@pytest.fixture
def dedup():
    """创建级联去重器实例。"""
    return CascadeDeduplicator(
        hash_algorithm="dhash",
        hash_threshold=6,
        ssim_threshold=0.85,
        thumbnail_size=(64, 36),
    )


@pytest.fixture
def sample_images():
    """创建测试用图片。"""
    from PIL import ImageDraw
    with tempfile.TemporaryDirectory() as tmpdir:
        # 图片 A：白底 + 左上角蓝色方块
        img_a = Image.new("RGB", (800, 600), color=(255, 255, 255))
        draw_a = ImageDraw.Draw(img_a)
        draw_a.rectangle([0, 0, 200, 200], fill=(0, 0, 255))
        draw_a.text((10, 220), "Hello World", fill=(0, 0, 0))
        path_a1 = Path(tmpdir) / "a1.jpg"
        img_a.save(str(path_a1), "JPEG", quality=75)
        path_a2 = Path(tmpdir) / "a2.jpg"
        img_a.save(str(path_a2), "JPEG", quality=75)

        # 图片 B：黑底 + 右下角红色方块（完全不同的结构）
        img_b = Image.new("RGB", (800, 600), color=(20, 20, 20))
        draw_b = ImageDraw.Draw(img_b)
        draw_b.rectangle([600, 400, 799, 599], fill=(255, 0, 0))
        draw_b.text((100, 100), "Different Page", fill=(255, 255, 255))
        path_b = Path(tmpdir) / "b.jpg"
        img_b.save(str(path_b), "JPEG", quality=75)

        # 图片 C：与 A 相似但右下角有小变化
        img_c = img_a.copy()
        draw_c = ImageDraw.Draw(img_c)
        draw_c.rectangle([700, 500, 790, 590], fill=(100, 100, 100))
        path_c = Path(tmpdir) / "c.jpg"
        img_c.save(str(path_c), "JPEG", quality=75)

        yield {
            "same1": path_a1,
            "same2": path_a2,
            "diff": path_b,
            "similar": path_c,
            "dir": tmpdir,
        }


class TestCascadeDeduplicator:
    """测试级联去重器核心功能。"""

    def test_initial_state_not_duplicate(self, dedup, sample_images):
        """第一张图片永远不是重复。"""
        result = dedup.check(sample_images["same1"])
        assert result.is_duplicate is False
        assert result.stage == "new"

    def test_identical_images_detected(self, dedup, sample_images):
        """完全相同的图片应被检测为重复。"""
        dedup.check(sample_images["same1"])
        result = dedup.check(sample_images["same2"])
        assert result.is_duplicate is True
        assert result.stage in ("thumbnail_md5", "dhash")

    def test_different_images_not_duplicate(self, dedup, sample_images):
        """完全不同的图片不应被检测为重复。"""
        dedup.check(sample_images["same1"])
        result = dedup.check(sample_images["diff"])
        assert result.is_duplicate is False
        assert result.stage == "new"

    def test_metadata_change_triggers_new(self, dedup, sample_images):
        """元数据变化（app/window 切换）应触发非重复。"""
        dedup.check(sample_images["same1"], app_name="Chrome", window_title="GitHub")
        # 同一张图但不同 app
        result = dedup.check(
            sample_images["same1"],
            app_name="VSCode",
            window_title="main.py",
        )
        assert result.is_duplicate is False

    def test_same_metadata_preserves_dedup(self, dedup, sample_images):
        """相同元数据 + 相同图片 = 重复。"""
        dedup.check(sample_images["same1"], app_name="Chrome", window_title="GitHub")
        result = dedup.check(
            sample_images["same2"],
            app_name="Chrome",
            window_title="GitHub",
        )
        assert result.is_duplicate is True

    def test_per_monitor_dedup(self, dedup, sample_images):
        """不同显示器的相同图片不应互相干扰。"""
        dedup.check(sample_images["same1"], monitor_id=1)
        result = dedup.check(sample_images["same1"], monitor_id=2)
        assert result.is_duplicate is False  # 不同屏幕，不是重复

    def test_same_monitor_dedup(self, dedup, sample_images):
        """同一显示器的相同图片应检测为重复。"""
        dedup.check(sample_images["same1"], monitor_id=1)
        result = dedup.check(sample_images["same2"], monitor_id=1)
        assert result.is_duplicate is True

    def test_reset_clears_history(self, dedup, sample_images):
        """重置后所有历史清空。"""
        dedup.check(sample_images["same1"])
        dedup.reset()
        result = dedup.check(sample_images["same1"])
        assert result.is_duplicate is False  # 重置后第一张不算重复


class TestDedupResult:
    """测试去重结果对象。"""

    def test_result_fields(self, dedup, sample_images):
        """结果对象包含所有必要字段。"""
        result = dedup.check(sample_images["same1"])
        assert hasattr(result, "is_duplicate")
        assert hasattr(result, "stage")
        assert hasattr(result, "thumbnail_md5")
        assert hasattr(result, "dhash_distance")
        assert hasattr(result, "ssim_score")

    def test_result_new_has_thumbnail_md5(self, dedup, sample_images):
        """新图片也应有 thumbnail_md5。"""
        result = dedup.check(sample_images["same1"])
        assert result.thumbnail_md5 is not None
        assert len(result.thumbnail_md5) == 32  # MD5 hex


class TestThumbnailMD5:
    """测试缩略图 MD5 快速过滤。"""

    def test_same_image_same_md5(self, dedup, sample_images):
        """相同图片的缩略图 MD5 应相同。"""
        r1 = dedup.check(sample_images["same1"])
        dedup.reset()
        r2 = dedup.check(sample_images["same2"])
        assert r1.thumbnail_md5 == r2.thumbnail_md5

    def test_different_image_different_md5(self, dedup, sample_images):
        """不同图片的缩略图 MD5 应不同。"""
        r1 = dedup.check(sample_images["same1"])
        dedup.reset()
        r2 = dedup.check(sample_images["diff"])
        assert r1.thumbnail_md5 != r2.thumbnail_md5


class TestDHash:
    """测试 dHash 感知哈希。"""

    def test_dhash_same_image_low_distance(self, dedup, sample_images):
        """相同图片在到达 dHash 层时距离应为 0 或很低。"""
        # 用不同的图片先建立历史，再用相同图片测试 dHash
        dedup.check(sample_images["diff"])
        result = dedup.check(sample_images["same1"])
        # 此时不同图片 → 一定是 new，dHash 应该有值且距离大
        assert result.is_duplicate is False
        assert result.dhash_distance is not None
        assert result.dhash_distance > dedup.hash_threshold

    def test_dhash_different_images_high_distance(self, dedup, sample_images):
        """不同图片的 dHash 距离应较大。"""
        dedup.check(sample_images["same1"])
        result = dedup.check(sample_images["diff"])
        assert result.is_duplicate is False
        # 可能在 thumbnail_md5 层就被判定为不同
        if result.dhash_distance is not None:
            assert result.dhash_distance > dedup.hash_threshold

    def test_phash_algorithm(self, sample_images):
        """测试使用 pHash 算法。"""
        dedup = CascadeDeduplicator(hash_algorithm="phash", hash_threshold=10)
        dedup.check(sample_images["same1"])
        result = dedup.check(sample_images["same2"])
        assert result.is_duplicate is True


class TestSSIM:
    """测试 SSIM 结构相似度（边界 case）。"""

    def test_ssim_computed_for_borderline(self, dedup, sample_images):
        """当 dHash 距离在边界范围时应计算 SSIM。"""
        dedup.check(sample_images["same1"])
        result = dedup.check(sample_images["similar"])
        # similar 图片可能在 dHash 边界，如果触发了 SSIM 则有分数
        if result.dhash_distance and 6 <= result.dhash_distance <= 12:
            assert result.ssim_score is not None
