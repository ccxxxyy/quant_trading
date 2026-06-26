# 停止占用端口的 Web 服务（含 uvicorn 遗留子进程）
param(
    [int]$Port = 8888
)

$listeningPids = @(
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
)

$pythonProcs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue
$targets = [System.Collections.Generic.HashSet[int]]::new()

foreach ($processId in $listeningPids) { [void]$targets.Add([int]$processId) }

foreach ($proc in $pythonProcs) {
    $cmd = $proc.CommandLine
    if ($cmd -match 'uvicorn.*quant_trading\.interface\.web') {
        [void]$targets.Add([int]$proc.ProcessId)
        continue
    }
    foreach ($parentPid in $listeningPids) {
        if ($cmd -match "parent_pid=$parentPid") {
            [void]$targets.Add([int]$proc.ProcessId)
            break
        }
    }
}

if ($targets.Count -eq 0) {
    Write-Host "Port $Port is not in use." -ForegroundColor Yellow
    exit 0
}

foreach ($processId in $targets) {
    $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
    $name = if ($proc) { $proc.ProcessName } else { "unknown" }
    Write-Host "Stopping PID $processId ($name)..." -ForegroundColor Cyan
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 1

if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "Port $Port is still in use. Close other terminals/PyCharm runs or reboot." -ForegroundColor Red
    exit 1
}

Write-Host "Port $Port is free." -ForegroundColor Green
