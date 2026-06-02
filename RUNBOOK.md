# RUNBOOK.md — 最短启动路径

## 3 步启动

```bash
cd hermes-context-memory
uv sync
uv run context-memory init
uv run context-memory start
```

## 验证

```bash
# 另开终端
curl http://127.0.0.1:1833/health
```

## 配置 API (可选)

```bash
# 方式 1: .env.local (推荐)
cp .env.local.example .env.local
# 编辑填入 API key

# 方式 2: config.yaml
# 直接编辑 config.yaml

# 方式 3: Web UI
# 浏览器打开 http://127.0.0.1:1833/ui
```

## 快速测试

```bash
uv run context-memory doctor        # 诊断
uv run context-memory capture-once  # 截图
uv run context-memory recall "test" # 查询
```
