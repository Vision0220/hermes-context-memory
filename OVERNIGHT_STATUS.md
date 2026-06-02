# OVERNIGHT_STATUS.md — 项目状态总览

**最后更新**: 2026-06-02

## 正常工作的功能

| 功能 | 状态 | 说明 |
|------|------|------|
| 多屏截图 | ✅ | mss per-monitor，按显示器独立截图 |
| 级联去重 | ✅ | MD5 → dHash → SSIM 三级过滤 |
| 自适应频率 | ✅ | GetLastInputInfo + 5 级状态机 + 队列背压 |
| FTS5 检索 | ✅ | SQLite FTS5 全文搜索，自动 fallback |
| CLI 命令 | ✅ | init/start/status/recall/capture-once/forget/doctor/warmup |
| REST API | ✅ | /health, /api/status, /api/config, /api/recall, /api/recent, /api/timeline, /api/forget, /api/warmup, /api/capture-once, /api/browser/events |
| Web UI | ✅ | /ui 状态页面 |
| MCP Server | ✅ | 5 个工具：recall_context, get_recent_context, get_activity_timeline, forget_context, get_context_service_status |
| 隐私保护 | ✅ | 敏感应用/域名黑名单、截图过滤、文本脱敏 |
| 配置管理 | ✅ | config.yaml + .env.local + HCM_ 环境变量 + /api/config |
| 浏览器扩展 | ✅ | Chrome/Edge Manifest V3 |
| Doctor | ✅ | 含 secret 泄露扫描 |
| 测试 | ✅ | 75 个测试全部通过 |

## 降级运行的功能

| 功能 | 状态 | 说明 |
|------|------|------|
| VLM 分析 | ⚠️ | 需要 API 可用，失败时 fallback 到文本摘要 |
| Embedding 向量 | ⚠️ | 需要 API 可用，失败时退化为 FTS5 检索 |
| OCR | ⚠️ | 默认 no-op，需安装 rapidocr-onnxruntime |
| 瓦片处理 | ⚠️ | 概念设计已完成，未完全实现 |
| 语义缓存 | ⚠️ | 未实现，相同截图可能重复调用 VLM |

## 未实现的功能

| 功能 | 说明 |
|------|------|
| 瓦片级 VLM | 高分辨率图片分块处理，只处理变化瓦片 |
| scheduler_metrics | 调度器指标记录 |
| 语义缓存 | VLM 结果缓存复用 |
| sessionizer 集成 | 事件聚合为会话（模块存在但未接入管线） |

## 启动步骤

```bash
cd hermes-context-memory
uv sync
uv run context-memory init          # 初始化目录和数据库
uv run context-memory doctor        # 诊断检查
uv run context-memory capture-once  # 测试截图
uv run context-memory start         # 启动服务
```

## 模型配置

```yaml
# config.yaml（或 .env.local）
models:
  vlm:
    enabled: true
    base_url: "https://your-api/v1"
    api_key: "your-key"
    model: "qwen/qwen3.6-35b-a3b"
    timeout: 60
  embedding:
    enabled: true
    base_url: "https://your-api/v1"
    api_key: "your-key"
    model: "text-embedding-qwen3-embedding-4b"
    timeout: 30
```

## 扩展加载

1. Chrome: `chrome://extensions/` → 开发者模式 → 加载已解压 → 选 `browser_extension/`
2. Edge: `edge://extensions/` → 开发者模式 → 加载已解压 → 选 `browser_extension/`

## 隐私/删除

- 敏感应用截图不保存原图，只记录低细节事件
- `uv run context-memory forget --days 7` 删除记录和文件
- `curl -X POST http://127.0.0.1:1833/api/forget -d '{"time_range":"last_7d"}'`

## 下一步

1. 实现瓦片级 VLM 处理（高分辨率优化）
2. 实现 VLM 语义缓存（避免重复调用）
3. 接入 sessionizer（事件→会话聚合）
4. 添加 scheduler_metrics 记录
5. 完善 /ui 页面（实时刷新、配置编辑）
