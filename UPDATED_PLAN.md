# UPDATED_PLAN.md — 最终实施计划

## 目标
让 Hermes Agent 能回答"我刚才看了什么"、"昨天看过哪个网页"。

## 核心约束
1. API key 只从 .env.local 或 UI 配置读取，不入 repo
2. Windows 原生截图必须可用，WSL 限制需文档化
3. VLM/Embedding 失败时系统必须降级运行（FTS5 fallback）

## 实施清单

### 1. 捕获层
- [x] 多屏截图 (mss per-monitor)
- [x] 高分辨率处理 (vlm_max_width=2048, hash_max_width=640)
- [ ] 瓦片处理: 5120x2160 → overview(2048) + tiles(4x3=12块)
- [ ] 只处理变化/文本密集/重要的瓦片
- [ ] 窗口元数据: app, process, title, active monitor (Win32)

### 2. 存储层
- [x] SQLite + FTS5
- [x] 表: raw_events, browser_events, activity_sessions, recall_chunks
- [ ] 新增表: screenshot_tiles, scheduler_metrics, model_status, config_state
- [ ] 迁移脚本 (idempotent ALTER TABLE)

### 3. 去重/相似性门控
- [x] 元数据变化检测
- [x] 缩略图 MD5
- [x] dHash 感知哈希
- [x] SSIM 结构相似度
- [ ] 瓦片级 diff
- [ ] 语义缓存 (VLM 结果复用)

### 4. 处理层
- [x] VLM 客户端 (OpenAI-compatible)
- [x] Embedding 客户端
- [x] 连接池 + 重试
- [x] GPU 预热 (VLM 优先)
- [ ] 瓦片级 VLM 分析

### 5. 自适应调度器
- [x] GetLastInputInfo 空闲检测
- [x] 5 级状态机
- [x] 队列背压
- [ ] scheduler_metrics 记录
- [ ] 关键帧保留 + 低价值帧合并

### 6. API 端点
- [x] /health, /api/recall, /api/recent, /api/timeline, /api/forget, /api/browser/events
- [ ] /api/status
- [ ] /api/config GET/POST
- [ ] /api/warmup
- [ ] /api/capture-once

### 7. CLI
- [x] init, start, status, capture-once, recall, forget
- [ ] doctor (含 secret scan)
- [ ] warmup

### 8. MCP
- [x] recall_context, get_recent_context, get_activity_timeline, forget_context
- [ ] get_context_service_status

### 9. 隐私
- [x] 敏感应用/域名黑名单
- [x] 截图过滤
- [ ] forget 删除文件验证

### 10. 配置
- [ ] .env.local 支持 (HCM_VLM_BASE_URL, HCM_VLM_API_KEY 等)
- [ ] /ui 端点 (状态、队列、截图、模型配置)
- [ ] doctor secret scan

### 11. 浏览器扩展
- [x] Manifest V3 基础
- [ ] 确认 POST 格式完整

### 12. 文档
- [x] README.md
- [ ] RUNBOOK.md
- [ ] OVERNIGHT_STATUS.md
- [ ] DEV_NOTES.md 更新
