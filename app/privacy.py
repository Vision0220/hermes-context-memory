"""隐私保护模块 — 敏感应用/域名检测、OCR 文本脱敏、截图过滤。"""

from __future__ import annotations

import re
from typing import Optional

from app.config import AppConfig


class PrivacyGuard:
    """隐私保护器，根据配置判断是否应过滤/脱敏。"""

    def __init__(self, config: AppConfig):
        self.config = config.privacy
        # 预编译正则：脱敏关键词
        self._redact_patterns = [
            re.compile(re.escape(kw), re.IGNORECASE)
            for kw in self.config.redact_keywords
        ]

    def is_app_excluded(self, app_name: Optional[str], window_title: Optional[str] = None) -> bool:
        """检查应用是否在隐私黑名单中。"""
        if not app_name and not window_title:
            return False
        check_text = f"{app_name or ''} {window_title or ''}".lower()
        for excluded in self.config.excluded_apps:
            if excluded.lower() in check_text:
                return True
        return False

    def is_domain_excluded(self, domain: Optional[str], url: Optional[str] = None) -> bool:
        """检查域名/URL 是否在隐私黑名单中。"""
        check_text = f"{domain or ''} {url or ''}".lower()
        for excluded in self.config.excluded_domains:
            if excluded.lower() in check_text:
                return True
        return False

    def is_sensitive(self, app_name: Optional[str] = None, window_title: Optional[str] = None,
                     domain: Optional[str] = None, url: Optional[str] = None) -> bool:
        """综合判断是否为敏感上下文。"""
        return (
            self.is_app_excluded(app_name, window_title)
            or self.is_domain_excluded(domain, url)
        )

    def redact_text(self, text: str) -> str:
        """对文本进行脱敏处理，替换敏感关键词为 ***。"""
        result = text
        for pattern in self._redact_patterns:
            result = pattern.sub("***", result)
        return result

    def sanitize_window_title(self, title: Optional[str]) -> Optional[str]:
        """脱敏窗口标题中的敏感信息。"""
        if not title:
            return title
        result = title
        for keyword in self.config.redact_keywords:
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            result = pattern.sub("***", result)
        return result

    def should_save_screenshot(self, app_name: Optional[str] = None,
                               window_title: Optional[str] = None,
                               domain: Optional[str] = None,
                               url: Optional[str] = None) -> bool:
        """判断是否应该保存截图原图。敏感上下文不保存原图。"""
        return not self.is_sensitive(app_name, window_title, domain, url)

    def create_sensitive_event(self, ts: str, app_name: Optional[str] = None,
                               window_title: Optional[str] = None) -> dict:
        """为敏感窗口创建低细节事件（不保存截图）。"""
        return {
            "ts": ts,
            "source": "screenshot",
            "app_name": app_name,
            "window_title": self.sanitize_window_title(window_title),
            "sensitive": True,
            "screenshot_path": None,
            "ocr_text": None,
            "vlm_summary": None,
        }
