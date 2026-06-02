# DEV_NOTES.md — 技术债务

## 已完成

- ✅ 瓦片处理: TileProcessor + capture_loop 集成
- ✅ 语义缓存: SemanticCache + keyframe + reused_from_event_id
- ✅ 会话聚合: sessionize_events + _sessionizer_loop
- ✅ 调度器指标: SchedulerMetrics + persist_metrics + /api/status + /ui
- ✅ 中文 FTS: LIKE fallback with CJK detection + browser_events union
- ✅ 多屏截图: capture_screens_multi per-monitor
- ✅ 级联去重: MD5→dHash→SSIM
- ✅ 自适应频率: GetLastInputInfo + 5级状态机 + 队列背压
- ✅ VLM/Embedding: 连接池 + 重试 + GPU预热 + SSL verify=False
- ✅ 隐私保护: 黑名单 + 截图过滤 + 脱敏
- ✅ Secret 管理: .env.local + HCM_ 前缀 + doctor scan
- ✅ 发布脚本: start/stop/check_status/cleanup PowerShell 脚本
- ✅ Task Scheduler: 开机自启指南

## 待改进

### 中优先级
1. **中文泛化查询**: FTS5 LIKE 搜索对"我刚才看了什么"等泛化查询无效
   - 方案: 添加 jieba 分词，或在 VLM 摘要中生成关键词标签
   - 或: 对每个事件生成 5-10 个关键词存入 ocr_text 字段
2. **瓦片 VLM**: TileProcessor 已接入但 VLM 分析需 API 可用
   - 当前只记录瓦片 metadata 和 text_density，不调用 VLM
3. **截图目录按 monitor_id 分目录**: 当前所有截图在同一目录
4. **sqlite-vec 向量检索**: 模块存在但 search.py 未集成

### 低优先级
5. **浏览器扩展 popup 实时刷新**: 当前只在打开时读取一次
6. **日志轮转**: 当前无自动日志轮转，需手动管理
7. **DB 迁移系统**: 当前用 ALTER TABLE try/except，无版本管理
