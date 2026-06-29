"""共享业务逻辑 - CLI 和 Web 接口共用的函数。"""

from __future__ import annotations

import importlib
import random
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from quant_trading.backtest.analyzer import PerformanceMetrics
from quant_trading.backtest.engine import BacktestEngine
from quant_trading.core.config import Settings
from quant_trading.data.engine import DataEngine
from quant_trading.data.store import DataStore
from quant_trading.model.instrument import Exchange, InstrumentId
from quant_trading.model.market import Bar, BarInterval
from quant_trading.strategy.context import StrategyContext

BUILTIN_STRATEGIES = {
    "dual_ma": {
        "class": "quant_trading.strategy.templates.cta.DualMovingAverageStrategy",
        "name": "双均线策略",
        "description": "快慢均线金叉买入、死叉卖出，经典 CTA 趋势跟踪",
        "params": {
            "fast_period": {"type": "int", "default": 10, "label": "快线周期"},
            "slow_period": {"type": "int", "default": 30, "label": "慢线周期"},
            "quantity": {"type": "int", "default": 100, "label": "下单数量"},
        },
    },
    "bollinger": {
        "class": "quant_trading.strategy.templates.cta.BollingerBandStrategy",
        "name": "布林带策略",
        "description": "价格触及下轨买入、上轨卖出，均值回归",
        "params": {
            "period": {"type": "int", "default": 20, "label": "布林带周期"},
            "num_std": {"type": "float", "default": 2.0, "label": "标准差倍数"},
            "quantity": {"type": "int", "default": 100, "label": "下单数量"},
        },
    },
    "rsi": {
        "class": "quant_trading.strategy.templates.rsi.RSIReversionStrategy",
        "name": "RSI 反转策略",
        "description": "RSI 超卖买入、超买卖出，均值回归型策略",
        "params": {
            "rsi_period": {"type": "int", "default": 14, "label": "RSI 周期"},
            "oversold": {"type": "int", "default": 30, "label": "超卖阈值"},
            "overbought": {"type": "int", "default": 70, "label": "超买阈值"},
            "quantity": {"type": "int", "default": 100, "label": "下单数量"},
        },
    },
    "macd": {
        "class": "quant_trading.strategy.templates.macd.MACDStrategy",
        "name": "MACD 策略",
        "description": "MACD 金叉做多、死叉平仓，经典趋势指标",
        "params": {
            "fast_period": {"type": "int", "default": 12, "label": "快线周期"},
            "slow_period": {"type": "int", "default": 26, "label": "慢线周期"},
            "signal_period": {"type": "int", "default": 9, "label": "信号线周期"},
            "quantity": {"type": "int", "default": 100, "label": "下单数量"},
        },
    },
    "turtle": {
        "class": "quant_trading.strategy.templates.turtle.TurtleTradingStrategy",
        "name": "海龟交易策略",
        "description": "突破 N 日最高价做多，跌破 M 日最低价止损，经典趋势跟踪系统",
        "params": {
            "entry_period": {"type": "int", "default": 20, "label": "入场通道周期"},
            "exit_period": {"type": "int", "default": 10, "label": "出场通道周期"},
            "quantity": {"type": "int", "default": 100, "label": "下单数量"},
        },
    },
    "grid": {
        "class": "quant_trading.strategy.templates.grid.GridTradingStrategy",
        "name": "网格交易策略",
        "description": "在价格区间内设置网格线，自动低买高卖，适合震荡行情",
        "params": {
            "upper_price": {"type": "float", "default": 110.0, "label": "网格上界"},
            "lower_price": {"type": "float", "default": 90.0, "label": "网格下界"},
            "grid_count": {"type": "int", "default": 10, "label": "网格数量"},
            "quantity_per_grid": {"type": "int", "default": 100, "label": "每格数量"},
        },
    },
    "pair": {
        "class": "quant_trading.strategy.templates.arbitrage.PairTradingStrategy",
        "name": "配对交易策略",
        "description": "统计套利，基于价差 Z-Score 入场/出场",
        "params": {
            "instrument_a": {"type": "str", "default": "", "label": "标的 A"},
            "instrument_b": {"type": "str", "default": "", "label": "标的 B"},
            "lookback": {"type": "int", "default": 60, "label": "回看周期"},
            "entry_threshold": {"type": "float", "default": 2.0, "label": "入场阈值"},
            "quantity": {"type": "int", "default": 100, "label": "下单数量"},
        },
    },
}

INTERVAL_MAP = {
    "1m": BarInterval.MINUTE_1,
    "5m": BarInterval.MINUTE_5,
    "15m": BarInterval.MINUTE_15,
    "1h": BarInterval.HOUR_1,
    "1d": BarInterval.DAILY,
}


def load_strategy(strategy_id: str, instrument_id: str, params: dict | None = None):
    """按策略ID或完整类路径加载策略实例。"""
    params = dict(params or {})
    params.setdefault("instrument_id", instrument_id)

    class_path = strategy_id
    if strategy_id in BUILTIN_STRATEGIES:
        class_path = BUILTIN_STRATEGIES[strategy_id]["class"]

    try:
        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        strategy_class = getattr(module, class_name)
    except (ValueError, ImportError, AttributeError) as e:
        raise ValueError(f"Cannot load strategy '{strategy_id}': {e}") from e

    return strategy_class(params=params)


def generate_demo_bars(
    instrument_id: InstrumentId,
    count: int = 250,
    start_price: float = 100.0,
    seed: int = 42,
) -> list[Bar]:
    """生成用于演示回测的模拟K线数据。"""
    random.seed(seed)
    bars: list[Bar] = []
    price = Decimal(str(start_price))
    base_time = datetime(2023, 1, 3)

    for i in range(count):
        change = Decimal(str(random.gauss(0, start_price * 0.02)))
        price = max(price + change, Decimal("1"))
        bars.append(
            Bar(
                instrument_id=instrument_id,
                timestamp=base_time + timedelta(days=i),
                interval=BarInterval.DAILY,
                open=price - Decimal(str(round(random.uniform(0, 2), 2))),
                high=price + Decimal(str(round(random.uniform(0, 5), 2))),
                low=price - Decimal(str(round(random.uniform(0, 5), 2))),
                close=price,
                volume=random.randint(10000, 100000),
            )
        )
    return bars


def run_backtest(
    strategy_id: str,
    symbol: str,
    start: datetime,
    end: datetime | None = None,
    capital: float = 1_000_000.0,
    params: dict | None = None,
    use_demo_data: bool = False,
    settings: Settings | None = None,
    enable_t1: bool = False,
    adjust: str = "none",
) -> dict[str, Any]:
    """运行回测并返回结构化的结果。"""
    from quant_trading.data.adjust import AdjustType

    settings = settings or Settings.load()
    instrument_id = InstrumentId.from_str(symbol)
    end = end or datetime.now()

    adjust_type = AdjustType(adjust) if adjust != "none" else AdjustType.NONE
    store = DataStore(settings.data.parquet_dir)
    bars = store.load_bars(instrument_id, BarInterval.DAILY, start, end, adjust=adjust_type)
    used_demo_data = False

    if not bars and use_demo_data:
        bars = generate_demo_bars(instrument_id)
        used_demo_data = True
    elif not bars:
        raise ValueError(f"No data for {symbol}. Fetch data first or enable demo mode.")

    engine = BacktestEngine(
        initial_capital=capital,
        commission_rate=settings.backtest.default_commission,
        slippage_rate=settings.backtest.default_slippage,
        enable_t1=enable_t1,
    )
    engine.add_bar_data(instrument_id, bars)

    strategy = load_strategy(strategy_id, str(instrument_id), params)
    ctx = StrategyContext(engine, strategy.strategy_id)
    strategy.attach(ctx)
    engine.add_strategy(strategy)

    metrics = engine.run()

    return {
        "metrics": metrics_to_dict(metrics),
        "equity_curve": [
            {"timestamp": ts.isoformat(), "equity": eq} for ts, eq in engine.equity_curve
        ],
        "trades": [
            {
                "instrument_id": t.instrument_id,
                "side": t.side,
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat(),
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "pnl": t.pnl,
                "commission": t.commission,
                "return_pct": t.return_pct,
            }
            for t in engine.trade_records
        ],
        "report": engine.get_report(),
        "bar_count": len(bars),
        "used_demo_data": used_demo_data,
    }


def metrics_to_dict(metrics: PerformanceMetrics) -> dict[str, Any]:
    return {
        "total_return": metrics.total_return,
        "annual_return": metrics.annual_return,
        "sharpe_ratio": metrics.sharpe_ratio,
        "sortino_ratio": metrics.sortino_ratio,
        "max_drawdown": metrics.max_drawdown,
        "max_drawdown_duration_days": metrics.max_drawdown_duration_days,
        "calmar_ratio": metrics.calmar_ratio,
        "win_rate": metrics.win_rate,
        "profit_factor": metrics.profit_factor,
        "total_trades": metrics.total_trades,
        "winning_trades": metrics.winning_trades,
        "losing_trades": metrics.losing_trades,
        "avg_win": metrics.avg_win,
        "avg_loss": metrics.avg_loss,
        "avg_trade_duration_days": metrics.avg_trade_duration_days,
        "volatility": metrics.volatility,
        "initial_capital": metrics.initial_capital,
        "final_capital": metrics.final_capital,
        "start_date": metrics.start_date.isoformat() if metrics.start_date else None,
        "end_date": metrics.end_date.isoformat() if metrics.end_date else None,
    }


async def fetch_market_data(
    symbol: str,
    start: datetime,
    end: datetime | None = None,
    interval: str = "1d",
    provider: str = "akshare",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """从数据源获取行情数据并保存到本地。"""
    settings = settings or Settings.load()
    instrument_id = InstrumentId.from_str(symbol)
    bar_interval = INTERVAL_MAP.get(interval, BarInterval.DAILY)
    end = end or datetime.now()

    store = DataStore(settings.data.parquet_dir)
    data_engine = DataEngine(event_bus=None, store=store)

    if provider == "akshare":
        from quant_trading.data.providers.akshare import AkShareFeed

        data_engine.add_feed(AkShareFeed())
    elif provider == "yfinance":
        from quant_trading.data.providers.yfinance import YFinanceFeed

        data_engine.add_feed(YFinanceFeed())
    else:
        raise ValueError(f"Unknown provider: {provider}")

    bars = await data_engine.fetch_bars(instrument_id, bar_interval, start, end)
    return {
        "symbol": symbol,
        "bar_count": len(bars),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "interval": interval,
        "provider": provider,
    }


def list_instruments(settings: Settings | None = None) -> list[str]:
    settings = settings or Settings.load()
    store = DataStore(settings.data.parquet_dir)
    return store.list_instruments()


def get_bar_preview(
    symbol: str,
    limit: int = 100,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """获取最近的K线数据用于图表展示。"""
    settings = settings or Settings.load()
    instrument_id = InstrumentId.from_str(symbol)
    store = DataStore(settings.data.parquet_dir)
    bars = store.load_bars(instrument_id, BarInterval.DAILY)
    if not bars:
        return []
    bars = bars[-limit:]
    return [
        {
            "timestamp": b.timestamp.isoformat(),
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": b.volume,
        }
        for b in bars
    ]


def get_system_info() -> dict[str, Any]:
    import sys

    from quant_trading import __version__

    settings = Settings.load()
    return {
        "version": __version__,
        "python": sys.version,
        "name": settings.system.name,
        "timezone": settings.system.timezone,
        "data_dir": settings.data.parquet_dir,
        "instrument_count": len(list_instruments(settings)),
        "strategies": [
            {"id": k, "name": v["name"], "description": v["description"]}
            for k, v in BUILTIN_STRATEGIES.items()
        ],
        "exchanges": [e.value for e in Exchange],
        "risk": settings.risk.model_dump(),
        "backtest_defaults": settings.backtest.model_dump(),
    }
