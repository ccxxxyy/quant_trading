"""FastAPI Web 应用 - REST API 和仪表盘服务器。"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

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
from quant_trading.interface.web.schemas import (
    BacktestRequest,
    FetchDataRequest,
    HealthResponse,
    OptimizeRequest,
    PaperConfigRequest,
    PaperOrderRequest,
)

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

# ── Paper trading gateway singleton ────────────────────────
_paper_gateway: Any = None


def _get_paper_gateway(
    capital: float = 1_000_000.0,
    commission: float = 0.0003,
    slippage: float = 0.0001,
    reset: bool = False,
) -> Any:
    global _paper_gateway
    if _paper_gateway is None or reset:
        from quant_trading.gateway.paper import PaperTradingGateway

        _paper_gateway = PaperTradingGateway(
            initial_capital=capital,
            commission_rate=commission,
            slippage_rate=slippage,
        )
    return _paper_gateway


# ── Static pages ───────────────────────────────────────────


@app.get("/")
async def index():
    """提供仪表盘单页应用。"""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Quant Trading API", "docs": "/docs"}


# ── Core APIs ──────────────────────────────────────────────


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


# ── Parameter Optimization APIs ────────────────────────────


@app.post("/api/optimize/run")
async def optimize_run(req: OptimizeRequest):
    """运行参数网格搜索优化。"""
    from quant_trading.strategy.optimizer import StrategyOptimizer

    try:
        start = datetime.strptime(req.start, "%Y-%m-%d")
        end = datetime.strptime(req.end, "%Y-%m-%d") if req.end else None
        optimizer = StrategyOptimizer(
            strategy_id=req.strategy,
            symbol=req.symbol,
            start=start,
            end=end,
            capital=req.capital,
            use_demo_data=req.use_demo_data,
        )
        results = await asyncio.to_thread(optimizer.optimize, req.param_grid)
        return {
            "results": [dataclasses.asdict(r) for r in results],
            "total": len(results),
            "strategy": req.strategy,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# ── Monitor / Alert APIs ──────────────────────────────────


@app.get("/api/monitor/alerts")
async def monitor_alerts(limit: int = 50):
    """获取最近的告警记录。"""
    from quant_trading.monitoring.alert import AlertManager

    manager = AlertManager()
    return {"alerts": manager.get_recent_alerts(limit), "count": manager.alert_count}


@app.get("/api/monitor/config")
async def monitor_config():
    """获取监控告警阈值配置。"""
    from quant_trading.monitoring.alert import AlertManager

    manager = AlertManager()
    return {"thresholds": manager._thresholds}


@app.post("/api/monitor/test")
async def monitor_test_alert():
    """发送一条测试告警。"""
    from quant_trading.monitoring.alert import AlertLevel, AlertManager, AlertType

    manager = AlertManager()
    from quant_trading.monitoring.alert import Alert

    manager.fire(
        Alert(
            alert_type=AlertType.CUSTOM,
            level=AlertLevel.INFO,
            message="这是一条测试告警（Web 界面触发）",
        )
    )
    return {"alerts": manager.get_recent_alerts(10), "count": manager.alert_count}


# ── Paper Trading APIs ─────────────────────────────────────


@app.post("/api/paper/connect")
async def paper_connect(req: PaperConfigRequest | None = None):
    """初始化/重置模拟盘网关。"""
    cfg = req or PaperConfigRequest()
    gw = _get_paper_gateway(cfg.initial_capital, cfg.commission_rate, cfg.slippage_rate, reset=True)
    await gw.connect()
    account = await gw.query_account()
    return {
        "status": "connected",
        "account": _serialize_account(account),
    }


@app.get("/api/paper/account")
async def paper_account():
    """查询模拟盘账户。"""
    gw = _get_paper_gateway()
    if not gw.is_connected:
        await gw.connect()
    account = await gw.query_account()
    return {"account": _serialize_account(account)}


@app.get("/api/paper/positions")
async def paper_positions():
    """查询模拟盘持仓。"""
    gw = _get_paper_gateway()
    if not gw.is_connected:
        await gw.connect()
    positions = await gw.query_positions()
    return {
        "positions": [_serialize_position(p) for p in positions],
        "count": len(positions),
    }


@app.post("/api/paper/order")
async def paper_submit_order(req: PaperOrderRequest):
    """模拟盘下单。"""
    from quant_trading.model.instrument import InstrumentId
    from quant_trading.model.order import Order, OrderSide, OrderType

    gw = _get_paper_gateway()
    if not gw.is_connected:
        await gw.connect()

    instrument_id = InstrumentId.from_str(req.symbol)
    side = OrderSide.BUY if req.side.lower() == "buy" else OrderSide.SELL
    order_type = OrderType.MARKET if req.order_type.lower() == "market" else OrderType.LIMIT

    order = Order(
        instrument_id=instrument_id,
        side=side,
        order_type=order_type,
        quantity=req.quantity,
        price=Decimal(str(req.price)) if req.price else Decimal(0),
    )

    if order_type == OrderType.MARKET:
        gw.on_price_update(instrument_id, Decimal("100.00"))

    order_id = await gw.submit_order(order)
    account = await gw.query_account()
    positions = await gw.query_positions()

    return {
        "order_id": order_id,
        "status": order.status.value,
        "account": _serialize_account(account),
        "positions": [_serialize_position(p) for p in positions],
    }


@app.get("/api/paper/orders")
async def paper_orders():
    """查询模拟盘挂单。"""
    gw = _get_paper_gateway()
    if not gw.is_connected:
        await gw.connect()
    pending = gw._pending_orders
    return {
        "orders": [
            {
                "order_id": o.order_id,
                "instrument_id": str(o.instrument_id),
                "side": o.side.value,
                "order_type": o.order_type.value,
                "quantity": o.quantity,
                "price": float(o.price) if o.price else None,
                "status": o.status.value,
            }
            for o in pending
        ],
        "count": len(pending),
    }


def _serialize_account(account: Any) -> dict:
    return {
        "account_id": account.account_id,
        "balance": float(account.balance),
        "available": float(account.available),
        "commission": float(account.commission),
        "currency": account.currency.value,
    }


def _serialize_position(pos: Any) -> dict:
    return {
        "instrument_id": str(pos.instrument_id),
        "quantity": pos.quantity,
        "avg_price": float(pos.avg_cost),
        "realized_pnl": float(pos.realized_pnl),
        "side": "long" if pos.quantity > 0 else "short",
    }


# ── AI Lab APIs ────────────────────────────────────────────


@app.get("/api/alpha/features")
async def alpha_features():
    """获取可用的 AI 特征列表及其描述。"""
    from quant_trading.alpha.feature import FeatureEngine

    engine = FeatureEngine()
    engine.register_defaults()
    features = []
    for name, factor in engine._factors.items():
        features.append(
            {
                "name": name,
                "dependencies": factor.dependencies,
                "type": type(factor).__name__,
            }
        )
    return {"features": features, "count": len(features)}


@app.post("/api/alpha/compute")
async def alpha_compute(symbol: str = "DEMO.SSE"):
    """对指定标的计算全部 AI 特征。"""
    from quant_trading.alpha.feature import FeatureEngine
    from quant_trading.interface.services import generate_demo_bars

    import polars as pl

    from quant_trading.model.instrument import InstrumentId

    instrument_id = InstrumentId.from_str(symbol)

    from quant_trading.core.config import Settings
    from quant_trading.data.store import DataStore
    from quant_trading.model.market import BarInterval

    settings = Settings.load()
    store = DataStore(settings.data.parquet_dir)
    bars = store.load_bars(instrument_id, BarInterval.DAILY)

    if not bars:
        bars = generate_demo_bars(instrument_id, count=120)

    df = pl.DataFrame(
        {
            "timestamp": [b.timestamp for b in bars],
            "open": [float(b.open) for b in bars],
            "high": [float(b.high) for b in bars],
            "low": [float(b.low) for b in bars],
            "close": [float(b.close) for b in bars],
            "volume": [b.volume for b in bars],
        }
    )

    engine = FeatureEngine()
    engine.register_defaults()
    result_df = engine.compute_features(df)

    tail = result_df.tail(20)
    rows = tail.to_dicts()
    for row in rows:
        if "timestamp" in row:
            row["timestamp"] = str(row["timestamp"])

    return {
        "symbol": symbol,
        "rows": rows,
        "columns": result_df.columns,
        "total_rows": len(result_df),
    }


@app.get("/api/alpha/models")
async def alpha_models():
    """获取可用的 ML 模型列表。"""
    return {
        "models": [
            {
                "id": "lightgbm",
                "name": "LightGBM",
                "description": "梯度提升树，适合金融表格数据",
                "status": "available",
            },
        ]
    }


# ── Entrypoint ─────────────────────────────────────────────


def main():
    """quant-web 命令的入口点。"""
    import sys

    import uvicorn

    use_reload = sys.platform != "win32"

    uvicorn.run(
        "quant_trading.interface.web.app:app",
        host="127.0.0.1",
        port=8888,
        reload=use_reload,
    )


if __name__ == "__main__":
    main()
