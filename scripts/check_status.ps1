# check_status.ps1 — 检查 Hermes Context Memory 服务状态
# 用法: .\scripts\check_status.ps1

$port = 1833

Write-Host "=== Hermes Context Memory Status ===" -ForegroundColor Cyan

# 检查端口
$conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($conn) {
    Write-Host "[OK] Service running on port $port (PID: $($conn.OwningProcess))" -ForegroundColor Green

    # Health
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -TimeoutSec 5
        Write-Host "  Status: $($health.status)" -ForegroundColor Green
        Write-Host "  DB: $($health.database) | Events: $($health.total_events) | Sessions: $($health.total_sessions)"
        Write-Host "  Capture: $($health.capture_active) | VLM: $($health.vlm_available) | Embedding: $($health.embedding_available)"
    } catch {
        Write-Host "[WARN] Health check failed: $_" -ForegroundColor Yellow
    }

    # Status
    try {
        $status = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/status" -TimeoutSec 5
        $m = $status.metrics
        Write-Host "  Metrics: captures=$($m.captures_total) skipped=$($m.duplicates_skipped) vlm=$($m.vlm_processed) queue=$($m.queue_depth)/$($m.queue_maxsize)"
        Write-Host "  Cache: size=$($status.semantic_cache.size) hits=$($status.semantic_cache.hits) misses=$($status.semantic_cache.misses)"
    } catch {
        Write-Host "[WARN] Status check failed: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "[INFO] No service running on port $port" -ForegroundColor Gray
}

# DB 大小
$dbPath = Join-Path $PSScriptRoot "..\data\context.sqlite"
if (Test-Path $dbPath) {
    $dbSize = (Get-Item $dbPath).Length / 1MB
    Write-Host "  DB size: $([math]::Round($dbSize, 2)) MB" -ForegroundColor Gray
}

# 截图文件夹大小
$ssDir = Join-Path $PSScriptRoot "..\data\screenshots"
if (Test-Path $ssDir) {
    $ssSize = (Get-ChildItem $ssDir -Recurse -File | Measure-Object -Property Length -Sum).Sum / 1MB
    $ssCount = (Get-ChildItem $ssDir -Recurse -File).Count
    Write-Host "  Screenshots: $ssCount files, $([math]::Round($ssSize, 2)) MB" -ForegroundColor Gray
}
