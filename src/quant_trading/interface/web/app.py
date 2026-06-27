"""FastAPI Web 应用 - REST API 和仪表盘服务器。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from quant_trading import __version__
from quant_trading.interface.services import (
    BUILTIN_STRATEGIES,
    fetch_market_data,
    get_bar_preview,
    get_system_info,
    list_instruments,
    run_backtest,
)
from quant_trading.interface.web.schemas import BacktestRequest, FetchDataRequest, HealthResponse

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Quant Trading System",
    description="个人量化交易系统 Web API",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    """提供仪表盘单页应用。"""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Quant Trading API", "docs": "/docs"}


@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", version=__version__)


@app.get("/api/system/info")
async def system_info():
    return get_system_info()


@app.get("/api/strategies")
async def strategies():
    return {
        "strategies": [
            {"id": k, **{key: v for key, v in meta.items() if key != "class"}}
            for k, meta in BUILTIN_STRATEGIES.items()
        ]
    }


@app.get("/api/data/instruments")
async def data_instruments():
    instruments = list_instruments()
    return {"instruments": instruments, "count": len(instruments)}


@app.get("/api/data/bars/{symbol}")
async def data_bars(symbol: str, limit: int = 200):
    try:
        bars = get_bar_preview(symbol, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"symbol": symbol, "bars": bars, "count": len(bars)}


@app.post("/api/data/fetch")
async def data_fetch(req: FetchDataRequest):
    try:
        start = datetime.strptime(req.start, "%Y-%m-%d")
        end = datetime.strptime(req.end, "%Y-%m-%d") if req.end else None
        result = await fetch_market_data(
            symbol=req.symbol,
            start=start,
            end=end,
            interval=req.interval,
            provider=req.provider,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Data provider not installed: {e}. Run: uv sync --extra data",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/backtest/run")
async def backtest_run(req: BacktestRequest):
    try:
        start = datetime.strptime(req.start, "%Y-%m-%d")
        end = datetime.strptime(req.end, "%Y-%m-%d") if req.end else None
        result = run_backtest(
            strategy_id=req.strategy,
            symbol=req.symbol,
            start=start,
            end=end,
            capital=req.capital,
            params=req.params,
            use_demo_data=req.use_demo_data,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/backtest/compare")
async def backtest_compare(req: BacktestRequest):
    """对比所有策略在相同标的和日期范围上的表现。"""
    try:
        start = datetime.strptime(req.start, "%Y-%m-%d")
        end = datetime.strptime(req.end, "%Y-%m-%d") if req.end else None
        results = {}
        for sid in BUILTIN_STRATEGIES:
            if sid == "pair":
                continue
            try:
                result = run_backtest(
                    strategy_id=sid,
                    symbol=req.symbol,
                    start=start,
                    end=end,
                    capital=req.capital,
                    use_demo_data=True,
                )
                results[sid] = result
            except Exception:
                pass
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/monitor/alerts")
async def monitor_alerts(limit: int = 50):
    """获取最近的告警记录。"""
    from quant_trading.monitoring.alert import AlertManager

    manager = AlertManager()
    return {"alerts": manager.get_recent_alerts(limit), "count": manager.alert_count}


@app.get("/api/alpha/features")
async def alpha_features():
    """获取可用的 AI 特征列表。"""
    from quant_trading.alpha.feature import FeatureEngine

    engine = FeatureEngine()
    engine.register_defaults()
    return {"features": list(engine._factors.keys())}


def main():
    """quant-web 命令的入口点。"""
    import sys

    import uvicorn

    # Windows 下 reload 会启动子进程，若依赖不完整容易报 websockets.legacy 等错误
    use_reload = sys.platform != "win32"

    uvicorn.run(
        "quant_trading.interface.web.app:app",
        host="127.0.0.1",
        port=8888,
        reload=use_reload,
    )


if __name__ == "__main__":
    main()
