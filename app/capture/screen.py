"""截图采集模块 — 使用 mss 进行屏幕截图，支持缩放和 JPEG 压缩。"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.config import AppConfig, DATA_DIR


def _screenshots_dir(date_str: str | None = None) -> Path:
    """获取截图保存目录。按日期分目录。"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    d = DATA_DIR / "screenshots" / date_str
    d.mkdir(parents=True, exist_ok=True)
    return d


def capture_screen(config: AppConfig) -> Optional[Path]:
    """截取屏幕截图，返回保存路径。

    按配置进行缩放和压缩，返回 JPEG 文件路径。
    如果 mss 不可用或截图失败，返回 None。
    """
    try:
        import mss
        from PIL import Image
    except ImportError:
        return None

    cap_config = config.capture
    ts = datetime.now()
    filename = f"{ts.strftime('%H%M%S')}_{ts.microsecond // 1000:03d}.jpg"
    save_dir = _screenshots_dir(ts.strftime("%Y-%m-%d"))
    save_path = save_dir / filename

    try:
        with mss.mss() as sct:
            # 截取所有显示器的组合画面
            monitor = sct.monitors[0]  # 0 = 所有显示器组合
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

            # 缩放
            max_width = cap_config.max_width
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.LANCZOS)

            # 保存为 JPEG
            img.save(str(save_path), "JPEG", quality=cap_config.quality)
            return save_path

    except Exception:
        return None


def compute_image_hash(image_path: Path) -> Optional[str]:
    """计算图片的感知哈希值，用于去重。

    使用 imagehash 库的 phash 算法。如果库不可用，使用文件 MD5 作为 fallback。
    """
    try:
        import imagehash
        from PIL import Image
        img = Image.open(str(image_path))
        h = imagehash.phash(img)
        return str(h)
    except ImportError:
        # fallback: 文件内容 MD5
        try:
            return hashlib.md5(image_path.read_bytes()).hexdigest()
        except OSError:
            return None
    except Exception:
        return None


def cleanup_old_screenshots(config: AppConfig):
    """清理超过保留天数的原始截图。"""
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=config.capture.save_raw_screenshot_days)
    screenshots_base = DATA_DIR / "screenshots"
    if not screenshots_base.exists():
        return

    deleted = 0
    for date_dir in screenshots_base.iterdir():
        if not date_dir.is_dir():
            continue
        try:
            dir_date = datetime.strptime(date_dir.name, "%Y-%m-%d")
        except ValueError:
            continue
        if dir_date < cutoff:
            import shutil
            shutil.rmtree(date_dir)
            deleted += 1

    return deleted
