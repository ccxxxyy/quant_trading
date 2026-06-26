# 启动 Web 仪表盘（绕过 quant-web.exe 锁定问题）
# 浏览器访问: http://127.0.0.1:8888
param(
    [int]$Port = 8888
)

$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    Write-Host "Port $Port is already in use (PID $($listening.OwningProcess))." -ForegroundColor Yellow
    Write-Host "Stopping old web server..." -ForegroundColor Cyan
    & "$PSScriptRoot\stop_web.ps1" -Port $Port
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Run .\stop_web.ps1 manually, or use: -Port 8889" -ForegroundColor Red
        exit 1
    }
}

Write-Host "Starting Quant Trading Web Dashboard..." -ForegroundColor Cyan
Write-Host "URL: http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop.`n"
& .venv\Scripts\python.exe -m uvicorn quant_trading.interface.web.app:app --host 127.0.0.1 --port $Port
