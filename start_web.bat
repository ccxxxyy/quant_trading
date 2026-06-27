@echo off
REM 启动 Web 仪表盘（绕过 quant-web.exe 锁定问题）
REM 浏览器访问: http://127.0.0.1:8888
echo Starting Quant Trading Web Dashboard...
echo URL: http://127.0.0.1:8888
echo Press Ctrl+C to stop.
echo.
.venv\Scripts\python.exe -m uvicorn quant_trading.interface.web.app:app --host 127.0.0.1 --port 8888
