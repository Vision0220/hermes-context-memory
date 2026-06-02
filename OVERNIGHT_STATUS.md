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
| 指标 | 值 |
|------|-----|
| Total events | 48 |
| Screenshot files | 53 |
| Screenshots size | 8.19 MB |
| DB size | 0.12 MB |
| VLM completed | 9 |
| VLM pending | 33 |
| VLM skipped | 4 |
| Sessions | 3 |
| Monitors | 2 |
| Latest resolution | 1600x1000 |
| Screenshot tiles | 0 (resolution <1920px) |

### 召回示例
| 查询 | 结果 |
|------|------|
| "Hermes" | ✅ 3 results, score=0.80, app=Hermes Studio |
| "Studio" | ✅ 3 results via LIKE fallback |
| "应用: M" | ✅ 1 result (VLM summary match) |
| "我刚才看了什么" | 0 results (VLM summaries use specific terms, not generic) |

### 已知限制
1. **中文泛化查询**: "我刚才看了什么"返回空，因为VLM摘要使用具体描述而非泛化词。可通过OCR+更多VLM处理改善。
2. **截图分辨率**: 当前显示器1600x1000，未触发瓦片处理（需>1920px）。
3. **浏览器事件**: 浏览器扩展未在pilot中加载，browser_events=0。
4. **DB并发**: 服务运行时直接访问DB可能触发disk I/O错误（WAL模式限制）。

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
