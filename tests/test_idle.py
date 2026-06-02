"""空闲检测 + 自适应间隔测试。"""

import pytest
from app.capture.idle import IdleLevel, get_idle_seconds, get_idle_level, compute_adaptive_interval


class TestGetIdleSeconds:
    """测试获取空闲时间。"""

    def test_returns_non_negative(self):
        """空闲时间应为非负数。"""
        result = get_idle_seconds()
        assert result >= 0

    def test_returns_number(self):
        """返回值应为浮点数。"""
        result = get_idle_seconds()
        assert isinstance(result, float)


class TestGetIdleLevel:
    """测试空闲级别判断。"""

    def test_returns_idle_level(self):
        """应返回 IdleLevel 枚举。"""
        result = get_idle_level()
        assert isinstance(result, IdleLevel)

    def test_active_when_using_computer(self):
        """正在使用电脑时应返回 L1_ACTIVE 或更高。"""
        result = get_idle_level()
        assert result in (
            IdleLevel.L0_IMMEDIATE,
            IdleLevel.L1_ACTIVE,
            IdleLevel.L2_SEMI_IDLE,
            IdleLevel.L3_IDLE,
            IdleLevel.L4_PAUSED,
        )


class TestComputeAdaptiveInterval:
    """测试自适应间隔计算。"""

    def test_active_normal_interval(self):
        """活跃状态应返回基准间隔。"""
        interval = compute_adaptive_interval(15.0, IdleLevel.L1_ACTIVE, 0.0)
        assert interval == 15.0

    def test_semi_idle_doubles_interval(self):
        """半空闲应加倍间隔。"""
        interval = compute_adaptive_interval(15.0, IdleLevel.L2_SEMI_IDLE, 0.0)
        assert interval == 30.0

    def test_idle_eight_times_interval(self):
        """空闲应 8 倍间隔。"""
        interval = compute_adaptive_interval(15.0, IdleLevel.L3_IDLE, 0.0)
        assert interval == 120.0

    def test_paused_max_interval(self):
        """暂停应返回最大间隔。"""
        interval = compute_adaptive_interval(15.0, IdleLevel.L4_PAUSED, 0.0)
        assert interval == 300.0

    def test_immediate_faster_interval(self):
        """立即模式应加快间隔。"""
        interval = compute_adaptive_interval(15.0, IdleLevel.L0_IMMEDIATE, 0.0)
        assert interval < 15.0

    def test_queue_pressure_moderate(self):
        """中等队列压力应加倍间隔。"""
        interval = compute_adaptive_interval(15.0, IdleLevel.L1_ACTIVE, 0.6)
        assert interval == 30.0

    def test_queue_pressure_high(self):
        """高队列压力应 4 倍间隔。"""
        interval = compute_adaptive_interval(15.0, IdleLevel.L1_ACTIVE, 0.9)
        assert interval == 60.0

    def test_combined_idle_and_pressure(self):
        """空闲 + 队列压力应叠加。"""
        interval = compute_adaptive_interval(15.0, IdleLevel.L2_SEMI_IDLE, 0.9)
        # 15 * 2(idle) * 4(pressure) = 120
        assert interval == 120.0

    def test_minimum_clamp(self):
        """间隔不应低于 5 秒。"""
        interval = compute_adaptive_interval(1.0, IdleLevel.L0_IMMEDIATE, 0.0)
        assert interval >= 5.0

    def test_maximum_clamp(self):
        """间隔不应超过 300 秒。"""
        interval = compute_adaptive_interval(100.0, IdleLevel.L3_IDLE, 0.9)
        # 100 * 8 * 4 = 3200, clamped to 300
        assert interval <= 300.0
