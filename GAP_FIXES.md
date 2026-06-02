# GAP_FIXES.md — 缺口修复记录

记录每个已知缺口的修复状态。

## 1. Secret 管理
- **问题**: config.yaml 中硬编码 API key
- **修复**: 支持 .env.local + HCM_ 前缀环境变量 + /api/config UI 配置
- **状态**: 实施中

## 2. 缺少数据库表
- **问题**: screenshot_tiles, scheduler_metrics, model_status 未实现
- **修复**: 添加建表语句 + 迁移
- **状态**: 实施中

## 3. 高分辨率瓦片处理
- **问题**: 5120x2160 直接发给 VLM
- **修复**: overview(2048px) + 4x3 tiles(512px each)，只处理变化瓦片
- **状态**: 实施中

## 4. 缺少 API 端点
- **问题**: /api/status, /api/config, /api/warmup, /api/capture-once 不存在
- **修复**: 添加到 routes.py
- **状态**: 实施中

## 5. 缺少 doctor CLI
- **问题**: 无 doctor 命令和 secret scan
- **修复**: 添加 doctor 命令含 API key 泄露检测
- **状态**: 实施中

## 6. 环境变量前缀
- **问题**: 使用 HERMES_ 而非 HCM_ 前缀
- **修复**: 更新为 HCM_VLM_BASE_URL, HCM_VLM_API_KEY, HCM_VLM_MODEL, HCM_EMBEDDING_BASE_URL, HCM_EMBEDDING_API_KEY, HCM_EMBEDDING_MODEL
- **状态**: 实施中

## 7. /ui 端点
- **问题**: 无 UI 界面
- **修复**: 添加简单 HTML 页面展示状态
- **状态**: 实施中

## 8. MCP get_context_service_status
- **问题**: MCP 缺少状态工具
- **修复**: 添加到 mcp_server.py
- **状态**: 实施中

## 9. 缺少文档
- **问题**: 无 RUNBOOK.md, OVERNIGHT_STATUS.md
- **修复**: 创建文档
- **状态**: 实施中
