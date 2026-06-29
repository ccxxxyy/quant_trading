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
            enable_t1=req.enable_t1,
            adjust=req.adjust,
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


# ── Emergency Risk Control APIs ────────────────────────────

_risk_engine: Any = None


def _get_risk_engine() -> Any:
    global _risk_engine
    if _risk_engine is None:
        from quant_trading.risk.engine import RiskEngine

        _risk_engine = RiskEngine()
    return _risk_engine


@app.get("/api/risk/status")
async def risk_status():
    """获取风控引擎当前状态。"""
    engine = _get_risk_engine()
    return engine.get_status()


@app.post("/api/risk/freeze")
async def risk_freeze():
    """紧急冻结 - 拒绝所有新订单。"""
    engine = _get_risk_engine()
    engine.emergency_freeze()
    return {"action": "freeze", "status": engine.get_status()}


@app.post("/api/risk/unfreeze")
async def risk_unfreeze():
    """解除紧急冻结。"""
    engine = _get_risk_engine()
    engine.emergency_unfreeze()
    return {"action": "unfreeze", "status": engine.get_status()}


@app.post("/api/risk/halt")
async def risk_halt_strategies():
    """暂停所有策略。"""
    engine = _get_risk_engine()
    engine.halt_strategies()
    return {"action": "halt_strategies", "status": engine.get_status()}


@app.post("/api/risk/resume")
async def risk_resume_strategies():
    """恢复所有策略。"""
    engine = _get_risk_engine()
    engine.resume_strategies()
    return {"action": "resume_strategies", "status": engine.get_status()}


@app.post("/api/risk/close-all")
async def risk_close_all():
    """一键清仓 - 对模拟盘所有持仓发出市价平仓指令。"""
    gw = _get_paper_gateway()
    if not gw.is_connected:
        await gw.connect()

    positions = await gw.query_positions()
    if not positions:
        return {"action": "close_all", "closed": 0, "message": "No positions to close"}

    closed = 0
    for pos in positions:
        if pos.is_flat:
            continue
        from quant_trading.model.order import Order, OrderSide, OrderType

        side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
        qty = abs(pos.quantity)
        order = Order(
            instrument_id=pos.instrument_id,
            side=side,
            order_type=OrderType.MARKET,
            quantity=qty,
            strategy_id="emergency_close",
        )
        gw.on_price_update(pos.instrument_id, pos.avg_cost)
        await gw.submit_order(order)
        closed += 1

    engine = _get_risk_engine()
    engine.emergency_freeze()

    account = await gw.query_account()
    return {
        "action": "close_all",
        "closed": closed,
        "account": _serialize_account(account),
        "risk_status": engine.get_status(),
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
    import polars as pl

    from quant_trading.alpha.feature import FeatureEngine
    from quant_trading.core.config import Settings
    from quant_trading.data.store import DataStore
    from quant_trading.interface.services import generate_demo_bars
    from quant_trading.model.instrument import InstrumentId
    from quant_trading.model.market import BarInterval

    instrument_id = InstrumentId.from_str(symbol)

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


# ── Live Strategy Runner APIs ──────────────────────────────

_live_runner: Any = None


def _get_live_runner() -> Any:
    global _live_runner
    if _live_runner is None:
        from quant_trading.strategy.runner import LiveStrategyRunner

        _live_runner = LiveStrategyRunner(
            gateway=_get_paper_gateway(),
            risk_engine=_get_risk_engine(),
        )
    return _live_runner


@app.get("/api/live/status")
async def live_status():
    """获取实时策略运行器状态。"""
    runner = _get_live_runner()
    return runner.get_status()


@app.post("/api/live/start")
async def live_start(strategy_id: str = "ma_cross", symbol: str = "DEMO.SSE"):
    """启动实时策略运行。"""
    runner = _get_live_runner()
    if runner.running:
        return {"status": "already_running", **runner.get_status()}

    if strategy_id not in BUILTIN_STRATEGIES:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {strategy_id}")

    strategy_cls = BUILTIN_STRATEGIES[strategy_id]["class"]
    strategy = strategy_cls(strategy_id=strategy_id)
    runner.add_strategy(strategy, [symbol])
    await runner.start()
    return {"status": "started", **runner.get_status()}


@app.post("/api/live/stop")
async def live_stop():
    """停止实时策略运行。"""
    global _live_runner
    runner = _get_live_runner()
    await runner.stop()
    _live_runner = None
    return {"status": "stopped"}


@app.post("/api/live/feed")
async def live_feed(symbol: str = "DEMO.SSE", price: float = 100.0, volume: int = 1000):
    """手动推送一根模拟K线到运行器（用于测试）。"""
    from quant_trading.model.instrument import InstrumentId
    from quant_trading.model.market import Bar, BarInterval

    runner = _get_live_runner()
    if not runner.running:
        raise HTTPException(status_code=400, detail="Runner not started")

    instrument_id = InstrumentId.from_str(symbol)
    bar = Bar(
        instrument_id=instrument_id,
        timestamp=datetime.now(),
        interval=BarInterval.MINUTE_1,
        open=Decimal(str(price)),
        high=Decimal(str(price * 1.001)),
        low=Decimal(str(price * 0.999)),
        close=Decimal(str(price)),
        volume=volume,
    )
    runner.on_bar(bar)
    return {"status": "fed", "bar_count": runner.bar_count, **runner.get_status()}


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
