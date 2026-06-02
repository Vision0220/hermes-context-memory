"""空闲检测模块 — Windows GetLastInputInfo API。

检测用户键盘/鼠标空闲时间，用于自适应截图频率。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import os
from enum import Enum

logger = logging.getLogger(__name__)


class IdleLevel(Enum):
    """用户空闲级别。"""
    L0_IMMEDIATE = 0   # App/窗口切换 → 立即截图
    L1_ACTIVE = 1      # 有键盘/鼠标输入 → 正常频率
    L2_SEMI_IDLE = 2   # 无输入 10-60s → 降低频率
    L3_IDLE = 3        # 无输入 60s+ → 大幅降低频率
    L4_PAUSED = 4      # 屏幕锁定 → 停止截图


# Windows LASTINPUTINFO 结构体
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.UINT),
        ("dwTime", ctypes.wintypes.DWORD),
    ]


def get_idle_seconds() -> float:
    """获取自上次输入以来的秒数。

    在 Windows 上调用 GetLastInputInfo API。
    非 Windows 平台返回 0（假定始终活跃）。
    """
    if os.name != "nt":
        return 0.0

    try:
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return 0.0

        current_tick = ctypes.windll.kernel32.GetTickCount()
        # 处理 DWORD 溢出（~49.7 天）
        if current_tick >= lii.dwTime:
            elapsed_ms = current_tick - lii.dwTime
        else:
            elapsed_ms = (0xFFFFFFFF - lii.dwTime) + current_tick + 1

        return elapsed_ms / 1000.0
    except Exception as e:
        logger.debug("GetLastInputInfo 失败: %s", e)
        return 0.0


def get_idle_level() -> IdleLevel:
    """获取当前用户空闲级别。"""
    idle = get_idle_seconds()

    if idle > 300:
        return IdleLevel.L4_PAUSED
    elif idle > 60:
        return IdleLevel.L3_IDLE
    elif idle > 10:
        return IdleLevel.L2_SEMI_IDLE
    else:
        return IdleLevel.L1_ACTIVE


def compute_adaptive_interval(
    base_interval: float,
    idle_level: IdleLevel,
    queue_pressure: float = 0.0,
) -> float:
    """计算自适应截图间隔。

    Args:
        base_interval: 基准间隔（秒），来自配置
        idle_level: 当前空闲级别
        queue_pressure: 队列压力 (0.0-1.0)，queue_depth / max_queue_size

    Returns:
        调整后的间隔（秒），范围 [5, 300]
    """
    # L4 = 停止
    if idle_level == IdleLevel.L4_PAUSED:
        return 300.0  # 最大间隔（实际采集循环会检查并跳过）

    # 空闲倍率
    idle_multipliers = {
        IdleLevel.L0_IMMEDIATE: 0.5,   # 紧急：加快
        IdleLevel.L1_ACTIVE: 1.0,
        IdleLevel.L2_SEMI_IDLE: 2.0,
        IdleLevel.L3_IDLE: 8.0,
        IdleLevel.L4_PAUSED: 1.0,      # 不会到这里
    }
    idle_mult = idle_multipliers.get(idle_level, 1.0)

    # 队列压力倍率
    if queue_pressure > 0.8:
        pressure_mult = 4.0
    elif queue_pressure > 0.5:
        pressure_mult = 2.0
    else:
        pressure_mult = 1.0

    interval = base_interval * idle_mult * pressure_mult

    # 限制范围
    return max(5.0, min(interval, 300.0))


def is_screen_locked() -> bool:
    """检测屏幕是否锁定。

    使用 OpenInputDesktop 检测：如果无法打开桌面句柄，说明已锁定。
    """
    if os.name != "nt":
        return False

    try:
        user32 = ctypes.windll.user32
        desktop = user32.OpenInputDesktop(0, False, 0x0001)  # DESKTOP_READOBJECTS
        if desktop:
            ctypes.windll.user32.CloseDesktop(desktop)
            return False
        return True
    except Exception:
        return False
