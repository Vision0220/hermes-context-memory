# start_service.ps1 — 启动 Hermes Context Memory 服务
# 用法: .\scripts\start_service.ps1

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $projectRoot) { $projectRoot = $PSScriptRoot }

Write-Host "=== Hermes Context Memory Service ===" -ForegroundColor Cyan
Write-Host "Project: $projectRoot" -ForegroundColor Gray

# 检查端口是否已占用
$port = 1833
$existing = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[WARN] Port $port already in use (PID: $($existing.OwningProcess))" -ForegroundColor Yellow
    Write-Host "  Stop existing service first: .\scripts\stop_service.ps1" -ForegroundColor Yellow
    exit 1
}

# 初始化（如果需要）
if (-not (Test-Path "$projectRoot\data\context.sqlite")) {
    Write-Host "[INIT] First run — initializing..." -ForegroundColor Yellow
    & uv run context-memory init
}

# 启动服务
Write-Host "[START] Launching on http://127.0.0.1:$port ..." -ForegroundColor Green
Write-Host "  UI: http://127.0.0.1:$port/ui" -ForegroundColor Gray
Write-Host "  Health: http://127.0.0.1:$port/health" -ForegroundColor Gray
Write-Host "  Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

& uv run uvicorn app.server.main:app --host 127.0.0.1 --port $port --log-level info
