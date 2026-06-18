"""命令行界面 - 量化交易系统的命令行工具。"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from quant_trading.backtest.engine import BacktestEngine
from quant_trading.core.config import Settings
from quant_trading.data.engine import DataEngine
from quant_trading.data.store import DataStore
from quant_trading.model.instrument import InstrumentId
from quant_trading.model.market import BarInterval


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quant",
        description="量化交易系统 - 命令行工具",
    )
    subparsers = parser.add_subparsers(dest="command")

    # 数据管理命令
    data_parser = subparsers.add_parser("data", help="数据管理命令")
    data_sub = data_parser.add_subparsers(dest="data_command")

    fetch_parser = data_sub.add_parser("fetch", help="获取历史行情数据")
    fetch_parser.add_argument("symbol", help="标的代码（如 600519.SSE）")
    fetch_parser.add_argument("--start", required=True, help="起始日期（YYYY-MM-DD）")
    fetch_parser.add_argument("--end", help="结束日期（YYYY-MM-DD）")
    fetch_parser.add_argument("--interval", default="1d", help="K线周期")
    fetch_parser.add_argument("--provider", default="akshare", help="数据源")

    data_sub.add_parser("list", help="列出已存储的标的数据")

    # 回测命令
    bt_parser = subparsers.add_parser("backtest", help="运行回测")
    bt_parser.add_argument("strategy", help="策略名称或模块路径")
    bt_parser.add_argument("--symbol", required=True, help="标的代码")
    bt_parser.add_argument("--start", required=True, help="起始日期")
    bt_parser.add_argument("--end", help="结束日期")
    bt_parser.add_argument("--capital", type=float, default=1_000_000, help="初始资金")
    bt_parser.add_argument("--params", help="策略参数（key=value 格式，逗号分隔）")

    # 系统信息命令
    subparsers.add_parser("info", help="显示系统信息")

    return parser


def cmd_data_fetch(args: argparse.Namespace) -> None:
    """从数据源获取历史行情数据。"""
    settings = Settings.load()
    instrument_id = InstrumentId.from_str(args.symbol)

    interval_map = {
        "1m": BarInterval.MINUTE_1,
        "5m": BarInterval.MINUTE_5,
        "15m": BarInterval.MINUTE_15,
        "1h": BarInterval.HOUR_1,
        "1d": BarInterval.DAILY,
    }
    interval = interval_map.get(args.interval, BarInterval.DAILY)
    start = datetime.strptime(args.start, "%Y-%m-%d")
    end = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.now()

    store = DataStore(settings.data.parquet_dir)
    data_engine = DataEngine(event_bus=None, store=store)

    # 选择数据源
    if args.provider == "akshare":
        from quant_trading.data.providers.akshare import AkShareFeed

        data_engine.add_feed(AkShareFeed())
    elif args.provider == "yfinance":
        from quant_trading.data.providers.yfinance import YFinanceFeed

        data_engine.add_feed(YFinanceFeed())

    bars = asyncio.run(data_engine.fetch_bars(instrument_id, interval, start, end))
    print(f"Fetched and saved {len(bars)} bars for {args.symbol}")


def cmd_data_list(args: argparse.Namespace) -> None:
    """列出本地已存储数据的所有标的。"""
    settings = Settings.load()
    store = DataStore(settings.data.parquet_dir)
    instruments = store.list_instruments()
    if instruments:
        print(f"已存储的标的 ({len(instruments)}):")
        for inst in instruments:
            print(f"  {inst}")
    else:
        print("未找到已存储的数据。")


def cmd_backtest(args: argparse.Namespace) -> None:
    """使用指定策略运行回测。"""
    settings = Settings.load()
    instrument_id = InstrumentId.from_str(args.symbol)

    start = datetime.strptime(args.start, "%Y-%m-%d")
    end = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.now()

    # 加载数据
    store = DataStore(settings.data.parquet_dir)
    bars = store.load_bars(instrument_id, BarInterval.DAILY, start, end)

    if not bars:
        print(f"未找到 {args.symbol} 的数据，请先运行 'quant data fetch' 获取数据。")
        return

    # 创建回测引擎
    engine = BacktestEngine(
        initial_capital=args.capital,
        commission_rate=settings.backtest.default_commission,
        slippage_rate=settings.backtest.default_slippage,
    )
    engine.add_bar_data(instrument_id, bars)

    # 加载策略
    strategy = _load_strategy(args.strategy, args.params, str(instrument_id))
    if strategy is None:
        return

    from quant_trading.strategy.context import StrategyContext

    ctx = StrategyContext(engine, strategy.strategy_id)
    strategy.attach(ctx)
    engine.add_strategy(strategy)

    # 运行回测
    engine.run()
    print(engine.get_report())


def _load_strategy(strategy_path: str, params_str: str | None, instrument_id: str):
    """按名称或模块路径加载策略。"""
    builtin = {
        "dual_ma": "quant_trading.strategy.templates.cta.DualMovingAverageStrategy",
        "bollinger": "quant_trading.strategy.templates.cta.BollingerBandStrategy",
        "rsi": "quant_trading.strategy.templates.rsi.RSIReversionStrategy",
        "macd": "quant_trading.strategy.templates.macd.MACDStrategy",
        "turtle": "quant_trading.strategy.templates.turtle.TurtleTradingStrategy",
        "grid": "quant_trading.strategy.templates.grid.GridTradingStrategy",
        "pair": "quant_trading.strategy.templates.arbitrage.PairTradingStrategy",
    }

    if strategy_path in builtin:
        strategy_path = builtin[strategy_path]

    try:
        module_path, class_name = strategy_path.rsplit(".", 1)
        import importlib

        module = importlib.import_module(module_path)
        strategy_class = getattr(module, class_name)
    except (ValueError, ImportError, AttributeError) as e:
        print(f"加载策略 '{strategy_path}' 失败: {e}")
        return None

    # 解析参数
    params = {"instrument_id": instrument_id}
    if params_str:
        for pair in params_str.split(","):
            key, value = pair.split("=")
            try:
                params[key.strip()] = int(value.strip())
            except ValueError:
                try:
                    params[key.strip()] = float(value.strip())
                except ValueError:
                    params[key.strip()] = value.strip()

    return strategy_class(params=params)


def cmd_info(args: argparse.Namespace) -> None:
    """显示系统信息。"""
    from quant_trading import __version__

    print(f"量化交易系统 v{__version__}")
    print(f"Python: {sys.version}")
    print(f"配置文件: {Path('config/settings.yaml').absolute()}")
    settings = Settings.load()
    print(f"数据目录: {settings.data.parquet_dir}")
    print("模式: 个人研究与交易")


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.command == "data":
        if args.data_command == "fetch":
            cmd_data_fetch(args)
        elif args.data_command == "list":
            cmd_data_list(args)
        else:
            print("使用方法: quant data {fetch|list}")
    elif args.command == "backtest":
        cmd_backtest(args)
    elif args.command == "info":
        cmd_info(args)


if __name__ == "__main__":
    main()
