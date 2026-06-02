"""隐私模块测试。"""

import pytest

from app.config import AppConfig, PrivacyConfig
from app.privacy import PrivacyGuard


@pytest.fixture
def privacy():
    """创建 PrivacyGuard 实例。"""
    config = AppConfig()
    return PrivacyGuard(config)


class TestAppExclusion:
    """测试应用黑名单检测。"""

    def test_excluded_app_detected(self, privacy):
        """测试黑名单中的应用被正确识别。"""
        assert privacy.is_app_excluded("1Password") is True
        assert privacy.is_app_excluded("WeChat") is True
        assert privacy.is_app_excluded("微信") is True
        assert privacy.is_app_excluded("Telegram") is True
        assert privacy.is_app_excluded("Bitwarden") is True

    def test_normal_app_allowed(self, privacy):
        """测试正常应用不被过滤。"""
        assert privacy.is_app_excluded("VSCode") is False
        assert privacy.is_app_excluded("Chrome") is False
        assert privacy.is_app_excluded("Firefox") is False
        assert privacy.is_app_excluded("Notepad") is False

    def test_window_title_check(self, privacy):
        """测试窗口标题中包含敏感应用名。"""
        assert privacy.is_app_excluded("Chrome", "1Password - Chrome") is True
        assert privacy.is_app_excluded("Chrome", "GitHub - Chrome") is False


class TestDomainExclusion:
    """测试域名黑名单检测。"""

    def test_excluded_domain_detected(self, privacy):
        """测试黑名单域名被正确识别。"""
        assert privacy.is_domain_excluded("online.bank.com") is True
        assert privacy.is_domain_excluded("paypal.com") is True
        assert privacy.is_domain_excluded("alipay.com") is True

    def test_normal_domain_allowed(self, privacy):
        """测试正常域名不被过滤。"""
        assert privacy.is_domain_excluded("github.com") is False
        assert privacy.is_domain_excluded("stackoverflow.com") is False

    def test_url_check(self, privacy):
        """测试 URL 中包含敏感关键词。"""
        assert privacy.is_domain_excluded(None, "https://example.com/login") is True
        assert privacy.is_domain_excluded(None, "https://example.com/auth/callback") is True


class TestTextRedaction:
    """测试文本脱敏。"""

    def test_redact_keywords(self, privacy):
        """测试敏感关键词被替换。"""
        result = privacy.redact_text("my password is 123456")
        assert "password" not in result
        assert "***" in result

    def test_redact_chinese(self, privacy):
        """测试中文敏感词脱敏。"""
        result = privacy.redact_text("请出示身份证")
        assert "身份证" not in result
        assert "***" in result

    def test_sanitize_window_title(self, privacy):
        """测试窗口标题脱敏。"""
        result = privacy.sanitize_window_title("Settings - password manager")
        assert "password" not in result.lower() or "***" in result

    def test_none_title(self, privacy):
        """测试 None 标题不报错。"""
        assert privacy.sanitize_window_title(None) is None


class TestScreenshotDecision:
    """测试截图保存决策。"""

    def test_sensitive_no_screenshot(self, privacy):
        """敏感应用不应保存截图。"""
        assert privacy.should_save_screenshot(app_name="1Password") is False
        assert privacy.should_save_screenshot(domain="bank.com") is False

    def test_normal_save_screenshot(self, privacy):
        """正常应用应保存截图。"""
        assert privacy.should_save_screenshot(app_name="VSCode") is True
        assert privacy.should_save_screenshot(domain="github.com") is True


class TestSensitiveEvent:
    """测试敏感事件创建。"""

    def test_create_sensitive_event(self, privacy):
        """测试创建低细节敏感事件。"""
        event = privacy.create_sensitive_event(
            ts="2026-06-02T10:00:00",
            app_name="1Password",
            window_title="password vault - 1Password",
        )
        assert event["sensitive"] is True
        assert event["screenshot_path"] is None
        assert event["ocr_text"] is None
