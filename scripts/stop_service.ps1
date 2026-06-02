# stop_service.ps1 — 停止 Hermes Context Memory 服务
# 用法: .\scripts\stop_service.ps1

$port = 1833
$conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($conn) {
    $pid = $conn.OwningProcess | Select-Object -Unique
    foreach ($p in $pid) {
        $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "[STOP] Killing PID $p ($($proc.ProcessName)) on port $port" -ForegroundColor Yellow
            Stop-Process -Id $p -Force
        }
    }
    Write-Host "[OK] Service stopped" -ForegroundColor Green
} else {
    Write-Host "[INFO] No service running on port $port" -ForegroundColor Gray
}
