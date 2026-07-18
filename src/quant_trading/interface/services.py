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
            "quantity": {"type": "int", "default": 10, "label": "下单数量"},
        },
    },
    "bollinger": {
        "class": "quant_trading.strategy.templates.cta.BollingerBandStrategy",
        "name": "布林带策略",
        "description": "价格触及下轨买入、上轨卖出，均值回归",
        "params": {
            "period": {"type": "int", "default": 20, "label": "布林带周期"},
            "num_std": {"type": "float", "default": 2.0, "label": "标准差倍数"},
            "quantity": {"type": "int", "default": 10, "label": "下单数量"},
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
            "quantity": {"type": "int", "default": 10, "label": "下单数量"},
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
            "quantity": {"type": "int", "default": 10, "label": "下单数量"},
        },
    },
    "turtle": {
        "class": "quant_trading.strategy.templates.turtle.TurtleTradingStrategy",
        "name": "海龟交易策略",
        "description": "突破 N 日最高价做多，跌破 M 日最低价止损，经典趋势跟踪系统",
        "params": {
            "entry_period": {"type": "int", "default": 20, "label": "入场通道周期"},
            "exit_period": {"type": "int", "default": 10, "label": "出场通道周期"},
            "quantity": {"type": "int", "default": 10, "label": "下单数量"},
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
            "quantity_per_grid": {"type": "int", "default": 10, "label": "每格数量"},
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
            "quantity": {"type": "int", "default": 10, "label": "下单数量"},
        },
    },
}

INTERVAL_MAP = {
    "1m": BarInterval.MINUTE_1,
    "5m": BarInterval.MINUTE_5,
    "15m": BarInterval.MINUTE_15,
    "1h": BarInterval.HOUR_1,
    "1d": BarInterval.DAILY,
    "tick": BarInterval.TICK,
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
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[Bar]:
    """生成用于演示回测的模拟K线数据。

    如果提供了 start/end，则生成覆盖该日期范围的数据（跳过周末）。
    否则从当前日期往前推 count 个交易日。
    """
    random.seed(seed)
    bars: list[Bar] = []
    price = Decimal(str(start_price))

    if start and end:
        s = start if isinstance(start, datetime) else datetime.combine(start, datetime.min.time())
        e = end if isinstance(end, datetime) else datetime.combine(end, datetime.min.time())
        trading_days = []
        current = s
        while current <= e:
            if current.weekday() < 5:
                trading_days.append(current)
            current += timedelta(days=1)
        if not trading_days:
            trading_days = [start + timedelta(days=i) for i in range(count)]
    else:
        today = end or datetime.now()
        trading_days = []
        d = today - timedelta(days=int(count * 1.5))
        while len(trading_days) < count:
            if d.weekday() < 5:
                trading_days.append(d)
            d += timedelta(days=1)

    for day in trading_days:
        change = Decimal(str(random.gauss(0, start_price * 0.02)))
        price = max(price + change, Decimal("1"))
        bars.append(
            Bar(
                instrument_id=instrument_id,
                timestamp=day,
                interval=BarInterval.DAILY,
                open=price - Decimal(str(round(random.uniform(0, 2), 2))),
                high=price + Decimal(str(round(random.uniform(0, 5), 2))),
                low=price - Decimal(str(round(random.uniform(0, 5), 2))),
                close=price,
                volume=random.randint(10000, 100000),
            )
        )
    return bars


def _generate_correlated_bars(
    base_bars: list[Bar], instrument_id: InstrumentId, correlation: float = 0.8
) -> list[Bar]:
    """基于已有K线生成一组相关的配对标的K线数据（用于配对交易演示）。"""
    random.seed(123)
    bars: list[Bar] = []
    for bar in base_bars:
        noise = Decimal(str(round(random.gauss(0, float(bar.close) * 0.01), 2)))
        offset = Decimal(str(round(float(bar.close) * 0.05, 2)))
        close = bar.close + offset + noise
        high = close + Decimal(str(round(random.uniform(0, 3), 2)))
        low = close - Decimal(str(round(random.uniform(0, 3), 2)))
        open_ = close - Decimal(str(round(random.uniform(-1, 1), 2)))
        bars.append(
            Bar(
                instrument_id=instrument_id,
                timestamp=bar.timestamp,
                interval=bar.interval,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=random.randint(10000, 80000),
            )
        )
    return bars


def run_backtest(
    strategy_id: str,
    symbol: str,
    start: datetime,
    end: datetime | None = None,
    capital: float = 100_000.0,
    params: dict | None = None,
    use_demo_data: bool = False,
    settings: Settings | None = None,
    enable_t1: bool = False,
    adjust: str = "none",
    transfer_fee_rate: float = 0.00002,
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

    if not bars:
        if use_demo_data:
            bars = generate_demo_bars(instrument_id, start=start, end=end)
            used_demo_data = True
        else:
            raise ValueError(f"No data for {symbol}. Fetch data first or enable demo mode.")

    engine = BacktestEngine(
        initial_capital=capital,
        commission_rate=settings.backtest.default_commission,
        slippage_rate=settings.backtest.default_slippage,
        enable_t1=enable_t1,
        transfer_fee_rate=transfer_fee_rate,
    )
    engine.add_bar_data(instrument_id, bars)

    # 为网格策略自动计算合理的价格边界
    if strategy_id == "grid" and bars:
        params = dict(params or {})
        closes = [float(b.close) for b in bars]
        price_min, price_max = min(closes), max(closes)
        margin = (price_max - price_min) * 0.1 or price_min * 0.1
        if "upper_price" not in params or params["upper_price"] == 110.0:
            params["upper_price"] = round(price_max + margin, 2)
        if "lower_price" not in params or params["lower_price"] == 90.0:
            params["lower_price"] = round(price_min - margin, 2)

    # 配对策略在单标的回测时，生成第二个相关标的的数据
    if strategy_id == "pair" and bars:
        params = dict(params or {})
        pair_b_symbol = params.get("instrument_b", "")
        if not pair_b_symbol:
            pair_b_symbol = f"PAIR_B.{instrument_id.exchange.value}"
            params["instrument_b"] = pair_b_symbol
        if not params.get("instrument_a"):
            params["instrument_a"] = str(instrument_id)
        pair_b_id = InstrumentId.from_str(pair_b_symbol)
        pair_b_bars = _generate_correlated_bars(bars, pair_b_id)
        engine.add_bar_data(pair_b_id, pair_b_bars)

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
        "bars": [
            {
                "timestamp": b.timestamp.isoformat(),
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": int(b.volume),
            }
            for b in bars
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


def _safe_float(val: Any) -> float:
    """确保数值可以安全序列化为 JSON（处理 complex / nan / inf）。"""
    import math

    if isinstance(val, complex):
        return val.real
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return 0.0
    return float(val)


def metrics_to_dict(metrics: PerformanceMetrics) -> dict[str, Any]:
    return {
        "total_return": _safe_float(metrics.total_return),
        "annual_return": _safe_float(metrics.annual_return),
        "sharpe_ratio": _safe_float(metrics.sharpe_ratio),
        "sortino_ratio": _safe_float(metrics.sortino_ratio),
        "max_drawdown": _safe_float(metrics.max_drawdown),
        "max_drawdown_duration_days": metrics.max_drawdown_duration_days,
        "calmar_ratio": _safe_float(metrics.calmar_ratio),
        "win_rate": _safe_float(metrics.win_rate),
        "profit_factor": _safe_float(metrics.profit_factor),
        "total_trades": metrics.total_trades,
        "winning_trades": metrics.winning_trades,
        "losing_trades": metrics.losing_trades,
        "avg_win": _safe_float(metrics.avg_win),
        "avg_loss": _safe_float(metrics.avg_loss),
        "avg_trade_duration_days": _safe_float(metrics.avg_trade_duration_days),
        "volatility": _safe_float(metrics.volatility),
        "initial_capital": _safe_float(metrics.initial_capital),
        "final_capital": _safe_float(metrics.final_capital),
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

    if interval == "tick":
        ticks = await data_engine.fetch_ticks(instrument_id, start, end)
        return {
            "symbol": symbol,
            "tick_count": len(ticks),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "interval": "tick",
            "provider": provider,
        }

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
    limit: int = 0,
    settings: Settings | None = None,
    start_str: str | None = None,
    end_str: str | None = None,
) -> list[dict[str, Any]]:
    """获取K线数据用于图表展示。limit=0 表示返回全部。"""
    settings = settings or Settings.load()
    instrument_id = InstrumentId.from_str(symbol)
    store = DataStore(settings.data.parquet_dir)
    start = datetime.strptime(start_str, "%Y-%m-%d") if start_str else None
    end = datetime.strptime(end_str, "%Y-%m-%d") if end_str else None
    bars = store.load_bars(instrument_id, BarInterval.DAILY, start=start, end=end)
    if not bars:
        return []
    if limit > 0:
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
