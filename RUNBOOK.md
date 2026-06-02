# RUNBOOK.md — 运维手册

## 启动

```bash
cd hermes-context-memory
uv sync
uv run context-memory init
uv run context-memory start
```

## 健康检查

```bash
curl http://127.0.0.1:1833/health
curl http://127.0.0.1:1833/api/status
```

## 诊断

```bash
uv run context-memory doctor     # 完整诊断 + secret scan
uv run context-memory status     # 服务状态
uv run context-memory warmup     # 预热 VLM/Embedding
```

## 配置管理

### 通过 .env.local（推荐，API key 不入 repo）
```bash
cp .env.local.example .env.local
# 编辑 .env.local 填入 API key
```

### 通过 config.yaml
编辑 config.yaml，重启服务生效。

### 通过 API
```bash
curl http://127.0.0.1:1833/api/config
curl -X POST http://127.0.0.1:1833/api/config -d '{"capture":{"interval_seconds":10}}'
```

### 通过 Web UI
打开 http://127.0.0.1:1833/ui

## 截图管理

```bash
# 手动截图
uv run context-memory capture-once

# 通过 API
curl -X POST http://127.0.0.1:1833/api/capture-once

# 清理旧截图
uv run context-memory forget --days 7
```

## 查询

```bash
# CLI
uv run context-memory recall "Python"

# API
curl -X POST http://127.0.0.1:1833/api/recall -d '{"query":"Python","time_range":"last_24h"}'

# MCP（在 Hermes Agent 中）
recall_context(query="Python", time_range="last_24h")
```

## 故障排查

### 截图失败
- 检查 mss 是否安装：`uv run python -c "import mss; print('ok')"`
- Windows 不需要特殊权限
- WSL2 无法截取 Windows 桌面

### VLM 不可用
- 服务会自动 fallback 到文本摘要
- 运行 `uv run context-memory warmup` 检查连通性
- 检查 .env.local 或 config.yaml 中的 API 配置

### 数据库锁定
- SQLite WAL 模式支持并发读
- 如果出现锁定，重启服务

### 浏览器扩展连接失败
- 确认服务运行：`curl http://127.0.0.1:1833/health`
- 扩展 popup 应显示绿色状态
- chrome:// 和 edge:// 页面不会被捕获
