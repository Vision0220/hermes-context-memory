"""窗口信息采集模块 — 获取当前活动窗口的标题、应用名、进程信息。"""

from __future__ import annotations

import os
from typing import Optional


class WindowInfo:
    """当前活动窗口的信息。"""
    def __init__(self, app_name: str = "", process_name: str = "",
                 window_title: str = "", executable_path: str = "",
                 monitor_id: int = 0):
        self.app_name = app_name
        self.process_name = process_name
        self.window_title = window_title
        self.executable_path = executable_path
        self.monitor_id = monitor_id

    def to_dict(self) -> dict:
        return {
            "app_name": self.app_name,
            "process_name": self.process_name,
            "window_title": self.window_title,
            "executable_path": self.executable_path,
            "monitor_id": self.monitor_id,
        }


def get_active_window() -> Optional[WindowInfo]:
    """获取当前活动窗口的信息。

    优先使用 pygetwindow + psutil（跨平台）。
    如果不可用，尝试 Windows 原生 API。
    """
    info = _try_pygetwindow()
    if info:
        return info

    # Windows 原生 fallback
    if os.name == "nt":
        info = _try_win32()
        if info:
            return info

    return None


def _try_pygetwindow() -> Optional[WindowInfo]:
    """通过 pygetwindow + psutil 获取窗口信息。"""
    try:
        import pygetwindow as gw
        import psutil
    except ImportError:
        return None

    try:
        active = gw.getActiveWindow()
        if active is None:
            return None

        title = active.title or ""

        # 尝试获取进程信息
        app_name = ""
        process_name = ""
        exe_path = ""

        # psutil 获取所有进程，匹配窗口标题中的关键字
        # 这是一个简化实现 — 生产中可使用 pywin32 的 GetWindowThreadProcessId
        try:
            for proc in psutil.process_iter(["pid", "name", "exe"]):
                try:
                    if proc.info["name"] and proc.info["name"].lower() in title.lower():
                        app_name = proc.info["name"].rsplit(".", 1)[0]
                        process_name = proc.info["name"]
                        exe_path = proc.info.get("exe") or ""
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass

        # 从标题猜测应用名（fallback）
        if not app_name and title:
            # 取标题的最后一个 " - " 之后的部分作为应用名
            parts = title.rsplit(" - ", 1)
            if len(parts) > 1:
                app_name = parts[-1].strip()
            else:
                app_name = title[:50]

        return WindowInfo(
            app_name=app_name,
            process_name=process_name,
            window_title=title,
            executable_path=exe_path,
        )
    except Exception:
        return None


def _try_win32() -> Optional[WindowInfo]:
    """通过 Windows API 获取窗口信息（需要 pywin32）。"""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        # 获取前台窗口句柄
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None

        # 获取窗口标题
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value

        # 获取进程 ID
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        # 获取进程信息
        process_name = ""
        exe_path = ""
        app_name = ""
        try:
            import psutil
            proc = psutil.Process(pid.value)
            process_name = proc.name()
            exe_path = proc.exe() or ""
            app_name = process_name.rsplit(".", 1)[0]
        except Exception:
            pass

        if not app_name and title:
            parts = title.rsplit(" - ", 1)
            app_name = parts[-1].strip() if len(parts) > 1 else title[:50]

        return WindowInfo(
            app_name=app_name,
            process_name=process_name,
            window_title=title,
            executable_path=exe_path,
        )
    except Exception:
        return None
