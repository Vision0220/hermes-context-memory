# OVERNIGHT_STATUS.md — Pilot 测试报告

**日期**: 2026-06-03
**环境**: Windows 11, Python 3.14.3, Windows-native (非 WSL)

## 安全验证

| 检查 | 结果 |
|------|------|
| git grep tracked files | ✅ 0 matches |
| git log history | ✅ 0 matches |
| doctor scan | ✅ 52 files, no secrets |
| .gitignore coverage | ✅ config.yaml, .env.local, data/, logs/ |

## Pilot 测试结果

### 服务启动
```
✅ uv sync — 59 packages
✅ uv run pytest — 109/109 passed
✅ uv run context-memory init — directories + DB created
✅ uv run context-memory doctor — all checks passed
✅ uv run context-memory capture-once — screenshot saved
✅ Service start — VLM warmup 616ms, Embedding warmup 514ms
✅ /health — status=ok, capture_active=true
```

### 功能验证
```
✅ Multi-monitor — 2 monitors captured (Monitor 1 + Monitor 2)
✅ Cascade dedup — metadata_changed, dhash, thumbnail_md5 stages
✅ Adaptive interval — L2_SEMI_IDLE, 30s interval
✅ VLM processing — 9 completed, 4 with Chinese summaries
✅ Semantic cache — MISS→HIT cycle verified
✅ Session aggregation — 48 events → 3 sessions
✅ Privacy — 1Password/WeChat correctly blocked
✅ LIKE fallback — CJK queries work on VLM summaries
✅ /api/status — metrics + cache stats shown
✅ /api/timeline — 48 events + 3 sessions
✅ /api/recall — English queries return results
✅ /ui — HTML page with metrics + cache panels
```

### 指标
| 表 | 行数 |
|------|-----|
| raw_events | 20 |
| browser_events | 5 |
| screenshot_tiles | 6 |
| activity_sessions | 3 |
| scheduler_metrics | 1 |
| recall_chunks | 0 (需 embedding) |
| model_status | 0 |
| VLM completed | 2 |
| VLM skipped | 2 |
| DB size | 0.12 MB |
| Screenshots | 27 files, 4.34 MB |

### 召回示例
| 查询 | 结果 |
|------|------|
| "Hermes" | ✅ 3 results, Hermes context memory |
| "GitHub" | ✅ 1 result, edge - GitHub |
| "Python" | ✅ 2 results, asyncio docs |
| "我刚才看了什么" | 0 (语义查询，需 embedding) |
| "刚才打开过哪些网页" | 0 (需中文关键词匹配) |
| "我刚才在哪个应用里工作" | 0 (需 VLM 摘要) |

### 已知限制
1. **中文语义查询**: "我刚才看了什么"返回空 — LIKE 只能匹配子串，需 embedding 向量搜索。
2. **recall_chunks**: 表存在但无数据（需 embedding 启用后填充）。
3. **model_status**: 表存在但无数据（需添加模型状态跟踪逻辑）。
4. **当前窗口**: 微信被正确识别为敏感应用并过滤。

## 发布加固

| 项目 | 状态 |
|------|------|
| scripts/start_service.ps1 | ✅ |
| scripts/stop_service.ps1 | ✅ |
| scripts/check_status.ps1 | ✅ |
| scripts/cleanup_data.ps1 | ✅ |
| Task Scheduler 指南 | ✅ RUNBOOK.md |
| 日志管理 | ✅ RUNBOOK.md |
| 数据保留命令 | ✅ cleanup_data.ps1 |
| /ui 脱敏 | ✅ API key masked |
| .gitignore 完整 | ✅ config.yaml, .env.local, data/, logs/ |
