# Hermes Context Memory Service

本地上下文记忆服务 — 让 Hermes Agent 记住你看过什么。

## 项目目标

Hermes Context Memory 为 AI Agent 提供类似 MineContext 的能力：
- 定时截取屏幕截图，记录当前窗口/应用信息
- 监听浏览器 URL 和页面标题
- 对截图进行 OCR 和 VLM 分析，生成结构化摘要
- 通过 REST API 和 MCP 工具被 Agent 查询
- 实现"我刚才/昨天/前几天看过什么"的 recall 能力

**核心原则：本地优先，不上传任何截图、OCR 文本或浏览记录到云端。**

## 安装

### 前提条件

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) 包管理器

### 安装步骤

```bash
cd hermes-context-memory

# 安装依赖
uv sync

# 如果需要 OCR 功能
uv sync --extra ocr

# 初始化项目（创建目录、数据库、配置文件）
uv run context-memory init
```

## Windows 运行

本项目优先支持 Windows 11。截图使用 `mss` 库，窗口信息使用 `psutil` + `pygetwindow`。

```powershell
cd hermes-context-memory
uv sync
uv run context-memory init
```

### WSL2 注意事项

WSL2 环境**无法直接截取 Windows 桌面截图**。请在 Windows 原生 PowerShell/CMD 中运行服务。如果需要在 WSL2 中使用检索功能，可以将服务运行在 Windows 端，WSL2 通过 `http://127.0.0.1:1833` 访问。

## 启动服务

```bash
# 启动 FastAPI 服务 + 截图采集循环
uv run context-memory start
```

服务启动后：
- REST API: http://127.0.0.1:1833
- 健康检查: http://127.0.0.1:1833/health
- API 文档: http://127.0.0.1:1833/docs

## 测试截图

```bash
# 执行一次截图，验证采集功能
uv run context-memory capture-once
```

## 命令行查询

```bash
# 查询最近 24 小时内与 "Python" 相关的上下文
uv run context-memory recall "Python"

# 查询最近 7 天
uv run context-memory recall "GitHub" --time-range last_7d

# 查看状态
uv run context-memory status

# 删除最近 7 天的记录
uv run context-memory forget --days 7
```

## REST API

### 健康检查

```bash
curl http://127.0.0.1:1833/health
```

### 语义检索

```bash
curl -X POST http://127.0.0.1:1833/api/recall \
  -H "Content-Type: application/json" \
  -d '{
    "query": "我昨天看过 MineContext 吗",
    "time_range": "last_24h",
    "top_k": 8
  }'
```

### 最近活动

```bash
curl http://127.0.0.1:1833/api/recent?minutes=30
```

### 时间线

```bash
curl http://127.0.0.1:1833/api/timeline?date=2026-06-02
```

### 遗忘（删除记录）

```bash
curl -X POST http://127.0.0.1:1833/api/forget \
  -H "Content-Type: application/json" \
  -d '{"time_range": "last_7d"}'
```

## 浏览器扩展

### 安装 Chrome/Edge 扩展

1. 打开 Chrome/Edge，访问 `chrome://extensions/` 或 `edge://extensions/`
2. 开启右上角的「开发者模式」
3. 点击「加载已解压的扩展程序」
4. 选择 `browser_extension/` 目录
5. 扩展图标应出现在工具栏，点击可查看连接状态

扩展功能：
- 监听 tab 切换、页面加载、窗口焦点变化
- 自动将 URL 和标题发送到本地服务
- 跳过 `chrome://`、`edge://` 等内部页面
- 2 秒去抖，避免重复发送

## MCP 接入

### Hermes Agent 配置

在 Hermes Agent 的 MCP 配置中添加：

```json
{
  "hermes-context-memory": {
    "command": "uv",
    "args": ["run", "python", "-m", "app.mcp_server"],
    "cwd": "/path/to/hermes-context-memory"
  }
}
```

### MCP 工具

| 工具 | 说明 |
|------|------|
| `recall_context` | 语义查询上下文记忆 |
| `get_recent_context` | 获取最近活动 |
| `get_activity_timeline` | 获取某天时间线 |
| `forget_context` | 删除上下文记录 |

## 配置

首次运行 `context-memory init` 会自动创建 `config.yaml`。可手动编辑：

```yaml
# 服务端口
server:
  port: 1833

# 截图配置
capture:
  enabled: true
  interval_seconds: 15  # 截图间隔
  max_width: 1600       # 最大宽度
  quality: 75           # JPEG 质量

# VLM 配置（可选）
models:
  vlm:
    enabled: true
    base_url: "http://127.0.0.1:1234/v1"  # LM Studio
    api_key: "lm-studio"
    model: "your-vlm-model"
```

完整配置参见 `config.example.yaml`。

## 隐私说明

### 默认保护

- **敏感应用黑名单**：1Password、Bitwarden、KeePass、微信、Telegram、Signal 等
- **敏感域名关键词**：bank、paypal、alipay、login、auth 等
- 敏感窗口命中时不保存截图原图，只记录低细节事件
- OCR 文本自动脱敏（password、token、api_key、身份证、银行卡等）

### 数据保留

- 原始截图默认保留 **14 天**，之后自动清理
- 元数据（事件、会话）保留在 SQLite 中，直到手动删除
- 所有数据存储在本地 `data/` 目录

### 删除数据

```bash
# 命令行删除
uv run context-memory forget --days 7

# API 删除
curl -X POST http://127.0.0.1:1833/api/forget \
  -d '{"time_range": "last_30d"}'

# 按应用删除
uv run context-memory forget --app-name "Chrome"
```

## 常见问题

### 截图权限问题

Windows 下截图不需要特殊权限。如果截图失败，检查是否有安全软件拦截了 `mss` 的屏幕访问。

### VLM 不可用

VLM（视觉语言模型）默认禁用。即使不配置 VLM，服务仍可正常运行：
- 截图正常保存
- 窗口标题和 URL 正常记录
- 基于 FTS5 的全文检索正常工作

启用 VLM 需要运行 LM Studio 或其他 OpenAI-compatible 服务端。

### ChromaDB 安装失败

本项目**不使用 ChromaDB**。向量存储使用 sqlite-vec（如果可用），全文检索使用 SQLite 内置的 FTS5。两者都在同一 SQLite 文件中，零外部依赖。

### 浏览器扩展连接失败

1. 确认服务已启动：`curl http://127.0.0.1:1833/health`
2. 确认扩展已加载（开发者模式）
3. 检查扩展 popup 显示的状态
4. 浏览器内部页面（`chrome://`、`edge://`）不会被捕获

### WSL 无法截图

WSL2 不直接访问 Windows 桌面。请在 Windows 端运行服务。检索 API 可通过 localhost 跨 WSL2 访问。

## 开发

```bash
# 运行测试
uv run pytest tests/ -v

# 仅运行某个测试
uv run pytest tests/test_storage.py -v
```

## 项目结构

```
hermes-context-memory/
├── pyproject.toml          # 项目配置和依赖
├── config.example.yaml     # 配置模板
├── README.md               # 本文档
├── DEV_NOTES.md            # 开发笔记
├── app/
│   ├── __init__.py
│   ├── cli.py              # 命令行接口
│   ├── config.py           # 配置管理
│   ├── models.py           # 数据模型
│   ├── storage.py          # SQLite 存储层
│   ├── privacy.py          # 隐私保护
│   ├── mcp_server.py       # MCP Server
│   ├── capture/            # 采集层
│   │   ├── screen.py       # 截图采集
│   │   ├── window.py       # 窗口信息
│   │   ├── browser.py      # 浏览器事件
│   │   └── dedup.py        # 去重
│   ├── processing/         # 处理层
│   │   ├── ocr.py          # OCR
│   │   ├── vlm.py          # VLM 摘要
│   │   ├── embedding.py    # Embedding
│   │   └── sessionizer.py  # 会话聚合
│   ├── retrieval/          # 检索层
│   │   ├── search.py       # 统一检索
│   │   ├── fts.py          # FTS5
│   │   └── vector.py       # 向量检索
│   └── server/             # 服务器
│       ├── main.py         # FastAPI 入口
│       └── routes.py       # API 路由
├── browser_extension/      # Chrome/Edge 扩展
│   ├── manifest.json
│   ├── background.js
│   ├── popup.html
│   └── popup.js
├── tests/                  # 测试
│   ├── test_storage.py
│   ├── test_privacy.py
│   └── test_recall.py
└── data/                   # 数据目录（运行时生成）
    ├── context.sqlite
    └── screenshots/
```
