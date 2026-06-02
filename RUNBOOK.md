# RUNBOOK.md — 运维手册

## 最短启动路径

```powershell
cd hermes-context-memory
uv sync
uv run context-memory init
.\scripts\start_service.ps1
```

## 脚本

| 脚本 | 用途 |
|------|------|
| `scripts\start_service.ps1` | 启动服务 |
| `scripts\stop_service.ps1` | 停止服务 |
| `scripts\check_status.ps1` | 检查状态（端口+健康+指标+DB大小+截图大小） |
| `scripts\cleanup_data.ps1 [-Days 14]` | 清理旧截图和 DB 记录 |

## Windows Task Scheduler 开机自启

```powershell
# 创建计划任务：登录时自动启动服务
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PWD\scripts\start_service.ps1`"" `
    -WorkingDirectory "$PWD"

$trigger = New-ScheduledTaskTrigger -AtLogOn

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName "HermesContextMemory" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Hermes Context Memory Service — 本地上下文记忆" `
    -RunLevel Limited

# 删除计划任务
Unregister-ScheduledTask -TaskName "HermesContextMemory" -Confirm:$false
```

## 日志管理

服务日志输出到 stdout。如需文件日志：

```powershell
.\scripts\start_service.ps1 *> logs\service.log
```

日志保留建议：
- 保留最近 7 天日志
- 每天轮转：`logs\service_2026-06-03.log`
- 用 `scripts\cleanup_data.ps1 -Days 7` 清理旧日志和截图

## 数据保留

```powershell
# 清理 14 天前的截图和 DB 记录
.\scripts\cleanup_data.ps1 -Days 14

# 只清理截图（不删 DB 记录）
Remove-Item data\screenshots\2026-05-* -Recurse -Force
```

## 配置管理

| 方式 | 文件 | 安全性 |
|------|------|--------|
| config.yaml | 本地配置 | .gitignore 已排除 |
| .env.local | API key | .gitignore 已排除 |
| /api/config | REST API | key 自动脱敏 |
| /ui | Web UI | key 自动脱敏 |

## 故障排查

### 截图失败
- 检查 mss：`uv run python -c "import mss; print('ok')"`
- Windows 不需要特殊权限
- WSL2 无法截取 Windows 桌面

### VLM 不可用
- 自动 fallback 到文本摘要
- 运行 `uv run context-memory warmup` 检查连通性
- 检查 .env.local 中的 API 配置

### 浏览器扩展连接失败
- 确认服务运行：`curl http://127.0.0.1:1833/health`
- 扩展 popup 应显示绿色状态
- chrome:// 和 edge:// 页面不会被捕获

### 数据库锁定
- SQLite WAL 模式支持并发读
- 如果出现锁定，重启服务
