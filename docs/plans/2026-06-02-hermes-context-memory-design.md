# Hermes Context Memory Service — 设计文档

**日期**: 2026-06-02
**状态**: 已批准

## 项目目标

让 Hermes Agent 拥有本地屏幕/浏览器上下文记忆能力，通过 MCP/REST API 实现 "我刚才/昨天看过什么" 的 recall 能力。

## 关键设计决策

### 1. 向量存储: sqlite-vec + FTS5

- **不使用 ChromaDB** — 安装不稳定（尤其 Windows），额外进程开销
- sqlite-vec 提供向量检索，FTS5 提供全文检索，同属一个 SQLite 文件
- 如果 sqlite-vec 安装失败，FTS5 作为唯一 fallback
- 数据库路径: `data/context.sqlite`

### 2. MCP SDK: 官方 `mcp` 包

- fastmcp 已合并进官方 SDK，直接用 `mcp[cli]`
- 暴露 4 个工具: recall_context, get_recent_context, get_activity_timeline, forget_context

### 3. OCR: 可插拔 + no-op fallback

- MVP 阶段默认 no-op（返回空字符串）
- 用户配置后可启用 RapidOCR/PaddleOCR
- 不阻塞核心流程

### 4. 实现分层（5 个 Phase）

| Phase | 内容 | 交付物 |
|-------|------|--------|
| 1 | 项目骨架 | pyproject.toml, 配置, 模型, 存储, 隐私, 服务器, CLI init/status |
| 2 | 采集层 | 截图, 窗口信息, 去重, capture-once, 浏览器捕获 |
| 3 | 检索层 | FTS5, recall/recent/timeline/forget API, CLI recall |
| 4 | 智能处理 | VLM, Embedding, Sessionizer |
| 5 | 集成 | 浏览器扩展, MCP Server, 测试, README |

### 5. 默认值

- 端口: 1733
- 截图间隔: 15s, 最大宽度 1600, 质量 75
- Session 聚合窗口: 5 分钟
- 隐私黑名单: 银行/密码管理器/社交敏感应用
- 数据保留: 原始截图 14 天

## 技术栈

- Python 3.11+, uv, FastAPI, SQLite (FTS5 + sqlite-vec)
- mss (截图), psutil + pygetwindow (窗口)
- imagehash (去重), Pillow (图像处理)
- pydantic (配置/模型), typer (CLI)
- mcp (MCP SDK), httpx (HTTP 客户端)
- pytest (测试)
