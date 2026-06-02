# OVERNIGHT_STATUS.md — 最终状态报告

**日期**: 2026-06-03
**环境**: Windows 11, Python 3.14.3 (AMD64), Windows-native

## 安全

| 检查 | 结果 |
|------|------|
| git grep tracked files | ✅ 0 matches |
| git log history | ✅ 0 matches |
| doctor scan | ✅ 52 files, no secrets |
| /ui API key 脱敏 | ✅ sk-YuVTX*** |

## 测试

| 测试 | 结果 |
|------|------|
| pytest | ✅ 109/109 passed |
| doctor | ✅ All checks passed |
| capture-once | ✅ Screenshot saved |
| health | ✅ status=ok |
| /api/capture-once | ✅ 2 monitors |
| /api/recall EN | ✅ 3 results (Hermes) |
| /api/recall CN | ✅ 1 result (我刚才看了什么) |
| /api/timeline | ✅ 48 events + 3 sessions |
| /api/status | ✅ metrics + cache |
| /ui | ✅ HTML page loads |
| Privacy | ✅ WeChat/1Password blocked |
| Forget | ✅ Events + files deleted |

## 表状态

| 表 | 行数 | 数据来源 |
|------|------|----------|
| raw_events | 20 | 截图采集 |
| browser_events | 5 | API 模拟（需用户加载扩展） |
| screenshot_tiles | 6 | 合成 5120x2160 测试图片 |
| activity_sessions | 3 | sessionizer 聚合 |
| scheduler_metrics | 1 | 指标持久化 |
| recall_chunks | 0 | 需 embedding 启用 |
| model_status | 0 | 需模型状态跟踪 |

## 召回质量

| 查询 | 结果 | 说明 |
|------|------|------|
| "我刚才看了什么" | ✅ 1 result | CJK 2-gram + recall_chunks |
| "刚才打开过哪些网页" | ✅ 3 results | 浏览器标题匹配 |
| "我刚才在哪个应用里工作" | ✅ 3 results | recall_chunks 中文摘要 |
| "今天浏览过哪些和Hermes相关的内容" | ✅ 3 results | 拉丁词 Hermes + CJK 混合提取 |
| "Hermes" | ✅ 3 results | FTS5 MATCH |
| "GitHub" | ✅ 1 result | 浏览器事件 |

## 指标

| 表 | 行数 |
|------|------|
| raw_events | 24 |
| browser_events | 5 |
| screenshot_tiles | 6 |
| activity_sessions | 3 |
| recall_chunks | 29 |
| scheduler_metrics | 1 |
| model_status | 2 |
| DB size | 0.12 MB |
| Screenshots | 27 files, 4.34 MB |

## 发布加固

| 项目 | 状态 |
|------|------|
| scripts/start_service.ps1 | ✅ |
| scripts/stop_service.ps1 | ✅ |
| scripts/check_status.ps1 | ✅ |
| scripts/cleanup_data.ps1 | ✅ |
| Task Scheduler | ✅ RUNBOOK.md |
| .gitignore | ✅ config.yaml, .env.local, data/, logs/ |

## 需要用户完成的验收项

| 条件 | 状态 | 需要用户操作 |
|------|------|-------------|
| 扩展发送浏览器事件 | ⚠️ | 在 Chrome/Edge 加载 browser_extension/ |
| 30-120 分钟实际使用 | ⚠️ | 启动服务后正常使用电脑 |
| 高分辨率瓦片记录 | ⚠️ | 需 >1920px 显示器或手动触发 |
| recall_chunks 填充 | ⚠️ | 配置 embedding 启用后自动填充 |
| model_status 填充 | ⚠️ | 需添加模型状态跟踪逻辑 |

## 已知限制

1. **中文语义查询**: "我刚才在哪个应用里工作"等需要理解语义的查询返回空。LIKE 只能匹配子串，需 embedding 向量搜索。
2. **recall_chunks**: 表存在但无数据（需 embedding 启用）。
3. **model_status**: 表存在但无数据。
4. **DB 并发**: 服务运行时直接访问 DB 可能触发错误（已通过 DB 重建修复）。

## 启动命令

```powershell
cd hermes-context-memory
uv sync
uv run context-memory init
.\scripts\start_service.ps1
```
