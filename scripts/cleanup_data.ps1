# cleanup_data.ps1 — 清理旧截图和数据
# 用法: .\scripts\cleanup_data.ps1 [-Days 14]

param(
    [int]$Days = 14
)

$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $projectRoot) { $projectRoot = $PSScriptRoot }

Write-Host "=== Cleanup: older than $Days days ===" -ForegroundColor Cyan

# 清理旧截图
$ssDir = Join-Path $projectRoot "data\screenshots"
if (Test-Path $ssDir) {
    $cutoff = (Get-Date).AddDays(-$Days)
    $dirs = Get-ChildItem $ssDir -Directory | Where-Object {
        try {
            $dirDate = [datetime]::ParseExact($_.Name, "yyyy-MM-dd", $null)
            $dirDate -lt $cutoff
        } catch { $false }
    }
    $totalSize = 0
    foreach ($d in $dirs) {
        $size = (Get-ChildItem $d.FullName -Recurse -File | Measure-Object -Property Length -Sum).Sum
        $totalSize += $size
        Remove-Item $d.FullName -Recurse -Force
        Write-Host "  Deleted: $($d.Name) ($([math]::Round($size/1MB, 2)) MB)" -ForegroundColor Yellow
    }
    Write-Host "[OK] Cleaned $([math]::Round($totalSize/1MB, 2)) MB of screenshots older than $Days days" -ForegroundColor Green
} else {
    Write-Host "[INFO] No screenshots directory" -ForegroundColor Gray
}

# 通过 API 清理 DB 记录
try {
    $body = @{ time_range = "last_${Days}d" } | ConvertTo-Json
    $result = Invoke-RestMethod -Uri "http://127.0.0.1:1833/api/forget" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 5
    Write-Host "[OK] DB cleanup: $($result.deleted_count) records removed" -ForegroundColor Green
} catch {
    Write-Host "[INFO] Service not running, DB records not cleaned (run when service is up)" -ForegroundColor Gray
}
