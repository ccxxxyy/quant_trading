"""示例：用于回测的双均线策略。"""

from quant_trading.strategy.templates.cta import DualMovingAverageStrategy

# 该策略可以通过命令行运行：
#   quant backtest dual_ma --symbol 600519.SSE --start 2023-01-01
#
# 也可以直接在代码中实例化：
#   strategy = DualMovingAverageStrategy(params={
#       "instrument_id": "600519.SSE",
#       "fast_period": 10,
#       "slow_period": 30,
#       "quantity": 100,
#   })

if __name__ == "__main__":
    from datetime import datetime, timedelta
    from decimal import Decimal

    from quant_trading.backtest.engine import BacktestEngine
    from quant_trading.model.instrument import Exchange, InstrumentId
    from quant_trading.model.market import Bar, BarInterval
    from quant_trading.strategy.context import StrategyContext

    # 创建演示用的标的
    instrument_id = InstrumentId(symbol="600519", exchange=Exchange.SSE)

    # 生成测试用的模拟K线数据
    import random
    random.seed(42)
    bars = []
    price = Decimal("1800.00")
    base_time = datetime(2023, 1, 3)

    for i in range(250):
        change = Decimal(str(random.gauss(0, 20)))
        price = max(price + change, Decimal("100"))
        bar = Bar(
            instrument_id=instrument_id,
            timestamp=base_time + timedelta(days=i),
            interval=BarInterval.DAILY,
            open=price - Decimal(str(round(random.uniform(0, 10), 2))),
            high=price + Decimal(str(round(random.uniform(0, 30), 2))),
            low=price - Decimal(str(round(random.uniform(0, 30), 2))),
            close=price,
            volume=random.randint(10000, 100000),
        )
        bars.append(bar)

    # 初始化回测引擎
    engine = BacktestEngine(initial_capital=1_000_000.0)
    engine.add_bar_data(instrument_id, bars)

    strategy = DualMovingAverageStrategy(params={
        "instrument_id": str(instrument_id),
        "fast_period": 10,
        "slow_period": 30,
        "quantity": 100,
    })

    ctx = StrategyContext(engine, strategy.strategy_id)
    strategy.attach(ctx)
    engine.add_strategy(strategy)

    # 运行回测并输出报告
    metrics = engine.run()
    print(engine.get_report())
