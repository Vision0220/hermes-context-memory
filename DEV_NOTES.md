# DEV_NOTES.md — 技术债务

## 已修复 (本次验证)

1. **/ui f-string bug**: JS 花括号在 Python f-string 中被解释 → 用 `{{}}` 转义
2. **MCP FastMCP API**: `description` → `instructions`
3. **SSL 自签名证书**: httpx 添加 `verify=False`
4. **Secret 泄露**: filter-branch 清理 git 历史

## 技术债务

### 高优先级 (已完成)
1. ✅ **瓦片处理**: TileProcessor + 主循环集成，高分辨率自动分块+变化检测+DB记录
2. ✅ **语义缓存**: SemanticCache + 正确键(domain+url+title+hash) + keyframe 强制 + reused_from_event_id
3. ✅ **会话聚合**: sessionize_events + _sessionizer_loop 后台任务
4. ✅ **调度器指标**: SchedulerMetrics + /api/status 和 /ui 展示

### 高优先级 (待完成)
1. **中文 FTS5 分词**: SQLite FTS5 默认不支持中文分词,搜索中文关键词返回空
   - 方案: 使用 jieba 分词预处理,或 VLM 摘要中生成英文关键词
2. **瓦片 VLM 集成**: TileProcessor 已实现但未接入主采集循环
   - 需要在 capture_loop 中检测高分辨率→分块→选择重要瓦片→逐块 VLM

### 中优先级
3. **sessionizer 接入管线**: 模块已实现，需要在采集循环中定期调用
4. **timeline API 展示会话**: /api/timeline 已返回 sessions，但需要验证数据流
5. **VLM 超时处理**: 如果 VLM 响应 >60s,采集循环会阻塞
   - 方案: 用 asyncio.wait_for 包装,超时则 fallback

### 低优先级
6. **sqlite-vec 向量检索**: 模块存在但未在 search.py 中集成
7. **截图目录按 monitor_id 分目录**: 当前所有截图在同一目录

## 环境特定问题

- **Windows GBK 编码**: Rich console 输出中文/Unicode 可能报错 → CLI 已强制 UTF-8
- **pygetwindow 局限**: 某些窗口类型无法获取进程名 → Win32 API fallback
- **WSL2 截图**: WSL2 无法截取 Windows 桌面 → 必须在 Windows 原生 Python 运行
