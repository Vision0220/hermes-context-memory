"""CLI 命令行接口 — 使用 Typer 实现。

命令：
  context-memory init          初始化目录、数据库、配置
  context-memory start         启动 FastAPI 服务和采集循环
  context-memory capture-once  截图一次，用于测试
  context-memory recall "关键词"  命令行查询
  context-memory status        显示服务状态
  context-memory forget --days 7  删除记录
"""

from __future__ import annotations

import io
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Windows 下强制 UTF-8 输出，避免 GBK 编码错误
if os.name == "nt":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.system("chcp 65001 >nul 2>&1")  # 设置 Windows 控制台代码页为 UTF-8

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="context-memory",
    help="Hermes Context Memory Service",
    no_args_is_help=True,
)
console = Console(force_terminal=True, width=120)

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@app.command()
def init():
    """初始化项目：创建目录、数据库、配置文件。"""
    from app.config import init_config, DATA_DIR
    from app.storage import Storage

    console.print("[bold]初始化 Hermes Context Memory...[/bold]")

    # 创建数据目录
    data_dirs = [
        DATA_DIR,
        DATA_DIR / "screenshots",
    ]
    for d in data_dirs:
        d.mkdir(parents=True, exist_ok=True)
        console.print(f"  [OK] dir: {d}")

    # 初始化配置
    config = init_config()
    console.print(f"  [OK] config: {PROJECT_ROOT / 'config.yaml'}")

    # 初始化数据库
    storage = Storage()
    storage.init_db()
    storage.close()
    console.print(f"  [OK] database: {DATA_DIR / 'context.sqlite'}")

    console.print("\n[green]Init done![/green]")
    console.print("  Next: [cyan]context-memory start[/cyan] or [cyan]context-memory capture-once[/cyan]")


@app.command()
def start():
    """启动 FastAPI 服务（含采集循环）。"""
    import uvicorn
    from app.config import load_config

    config = load_config()
    console.print(f"[bold]启动服务: http://{config.server.host}:{config.server.port}[/bold]")
    console.print(f"  采集间隔: {config.capture.interval_seconds}s")
    console.print(f"  VLM: {'启用' if config.models.vlm.enabled else '禁用'}")
    console.print(f"  Embedding: {'启用' if config.models.embedding.enabled else '禁用'}")
    console.print("  按 Ctrl+C 停止\n")

    uvicorn.run(
        "app.server.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=False,
        log_level="info",
    )


@app.command()
def capture_once():
    """执行一次截图和窗口信息采集，用于测试。"""
    from app.config import load_config
    from app.storage import Storage
    from app.capture.screen import capture_screen, compute_image_hash
    from app.capture.window import get_active_window
    from app.privacy import PrivacyGuard
    from app.models import RawEvent
    from app.processing.ocr import get_ocr_engine

    config = load_config()
    storage = Storage()
    storage.init_db()
    privacy = PrivacyGuard(config)

    console.print("[bold]Capture once...[/bold]")

    # 获取窗口信息
    window_info = get_active_window()
    if window_info:
        console.print(f"  Window: {window_info.window_title}")
        console.print(f"  App: {window_info.app_name}")
        console.print(f"  Process: {window_info.process_name}")

        # 隐私检查
        if privacy.is_sensitive(window_info.app_name, window_info.window_title):
            console.print("  [yellow]Sensitive window - skip screenshot, log only[/yellow]")
            ts = datetime.now().isoformat(timespec="seconds")
            event_data = privacy.create_sensitive_event(ts, window_info.app_name, window_info.window_title)
            event_data["source"] = "screenshot"
            event_data["process_name"] = window_info.process_name
            event = RawEvent(**event_data)
            storage.insert_event(event)
            console.print(f"  [OK] event recorded: {event.id}")
            storage.close()
            return
    else:
        console.print("  [yellow]Cannot get window info[/yellow]")
        window_info = None

    # 截图
    screenshot_path = capture_screen(config)
    if screenshot_path:
        console.print(f"  [OK] screenshot: {screenshot_path}")

        # 计算哈希
        image_hash = compute_image_hash(screenshot_path)
        console.print(f"  Hash: {image_hash}")

        # OCR（默认 no-op）
        ocr_engine = get_ocr_engine("noop")
        ocr_text = ocr_engine.extract_text(screenshot_path)
        if ocr_text:
            console.print(f"  OCR: {ocr_text[:100]}...")

        # 创建事件
        ts = datetime.now().isoformat(timespec="seconds")
        event = RawEvent(
            ts=ts,
            source="screenshot",
            app_name=window_info.app_name if window_info else "",
            process_name=window_info.process_name if window_info else "",
            window_title=window_info.window_title if window_info else "",
            screenshot_path=str(screenshot_path),
            image_hash=image_hash,
            ocr_text=ocr_text or None,
        )
        event_id = storage.insert_event(event)
        console.print(f"  [OK] event recorded: {event_id}")
    else:
        console.print("  [red]Screenshot failed[/red]")

    storage.close()
    console.print("\n[green]Capture done![/green]")


@app.command()
def recall(
    query: str = typer.Argument(..., help="查询关键词"),
    time_range: str = typer.Option("last_24h", help="时间范围: last_24h, last_7d, YYYY-MM-DD"),
    top_k: int = typer.Option(8, help="返回结果数"),
):
    """命令行查询上下文记忆。"""
    from app.config import load_config
    from app.storage import Storage
    from app.models import RecallRequest
    from app.retrieval.search import search_context

    config = load_config()
    storage = Storage()
    storage.init_db()

    request = RecallRequest(
        query=query,
        time_range=time_range,
        top_k=top_k,
    )

    console.print(f"[bold]查询: {query}[/bold] (时间范围: {time_range})\n")

    results = search_context(request, config)

    if not results:
        console.print("[yellow]未找到相关上下文。[/yellow]")
        storage.close()
        return

    # 用表格展示结果
    table = Table(title=f"检索结果 ({len(results)} 条)")
    table.add_column("时间", style="cyan", width=20)
    table.add_column("应用", style="green", width=15)
    table.add_column("窗口/标题", width=30)
    table.add_column("摘要", width=40)
    table.add_column("类型", style="magenta", width=10)
    table.add_column("分数", style="yellow", width=6)

    for r in results:
        table.add_row(
            r.ts[:19] if r.ts else "-",
            r.app_name or "-",
            (r.window_title or "-")[:30],
            (r.summary or "-")[:40],
            r.evidence_type,
            f"{r.score:.2f}",
        )

    console.print(table)
    storage.close()


@app.command()
def status():
    """显示服务状态。"""
    from app.config import load_config
    from app.storage import Storage

    config = load_config()
    storage = Storage()
    storage.init_db()
    db_status = storage.get_status()

    console.print("[bold]Hermes Context Memory 状态[/bold]\n")
    console.print(f"  数据库: {db_status['db_path']}")
    console.print(f"  原始事件: {db_status['raw_events']}")
    console.print(f"  浏览器事件: {db_status['browser_events']}")
    console.print(f"  活动会话: {db_status['activity_sessions']}")
    console.print(f"\n  截图采集: {'启用' if config.capture.enabled else '禁用'}")
    console.print(f"  截图间隔: {config.capture.interval_seconds}s")
    console.print(f"  VLM: {'启用' if config.models.vlm.enabled else '禁用'}")
    console.print(f"  Embedding: {'启用' if config.models.embedding.enabled else '禁用'}")

    storage.close()


@app.command()
def forget(
    days: int = typer.Option(None, help="删除最近 N 天的记录"),
    app_name: str = typer.Option(None, help="按应用名删除"),
    domain: str = typer.Option(None, help="按域名删除"),
):
    """删除上下文记录和截图。"""
    from app.config import load_config
    from app.storage import Storage

    if not days and not app_name and not domain:
        console.print("[red]请至少指定一个删除条件: --days, --app-name, --domain[/red]")
        raise typer.Exit(1)

    storage = Storage()
    storage.init_db()

    conditions = {}
    if days:
        conditions["time_range"] = f"last_{days}d"
    if app_name:
        conditions["app_name"] = app_name
    if domain:
        conditions["domain"] = domain

    # 确认删除
    console.print(f"[yellow]即将删除以下条件的记录:[/yellow]")
    for k, v in conditions.items():
        console.print(f"  {k}: {v}")

    confirm = typer.confirm("确认删除？此操作不可恢复")
    if not confirm:
        console.print("已取消")
        storage.close()
        return

    deleted = storage.delete_events(conditions)
    console.print(f"[green]已删除 {deleted} 条记录及其关联截图。[/green]")
    storage.close()


def main():
    """入口函数。"""
    app()


if __name__ == "__main__":
    main()
