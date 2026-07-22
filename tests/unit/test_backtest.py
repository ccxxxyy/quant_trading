"""回测引擎的单元测试。"""

from datetime import datetime
from decimal import Decimal

from quant_trading.backtest.engine import BacktestEngine
from quant_trading.model.instrument import Exchange, InstrumentId
from quant_trading.model.market import Bar, BarInterval
from quant_trading.strategy.base import BarSeriesStrategy
from quant_trading.strategy.context import StrategyContext


class SimpleTestStrategy(BarSeriesStrategy):
    """测试用简单策略：第2根K线买入，第8根K线卖出。"""

    def __init__(self):
        super().__init__(strategy_id="test", params={"buy_bar": 2, "sell_bar": 8})
        self._bar_count = 0

    def on_init(self):
        pass

    def on_bar_update(self, bar: Bar):
        self._bar_count += 1
        if self._bar_count == self.params["buy_bar"]:
            self.ctx.buy_market(bar.instrument_id, 100)
        elif self._bar_count == self.params["sell_bar"]:
            self.ctx.sell_market(bar.instrument_id, 100)


def make_bars(n: int = 10, start_price: float = 100.0) -> list[Bar]:
    """生成用于测试的模拟K线数据。"""
    iid = InstrumentId("TEST", Exchange.SSE)
    bars = []
    price = start_price
    for i in range(n):
        price += 1.0  # 模拟上涨趋势
        bars.append(
            Bar(
                instrument_id=iid,
                timestamp=datetime(2023, 1, i + 1),
                interval=BarInterval.DAILY,
                open=Decimal(str(price - 0.5)),
                high=Decimal(str(price + 1)),
                low=Decimal(str(price - 1)),
                close=Decimal(str(price)),
                volume=10000,
            )
        )
    return bars


class TestBacktestEngine:
    def test_basic_backtest(self):
        engine = BacktestEngine(initial_capital=100_000.0)
        iid = InstrumentId("TEST", Exchange.SSE)
        bars = make_bars(10)
        engine.add_bar_data(iid, bars)

        strategy = SimpleTestStrategy()
        ctx = StrategyContext(engine, "test")
        strategy.attach(ctx)
        engine.add_strategy(strategy)

        metrics = engine.run()
        assert metrics.total_trades >= 1
        assert metrics.final_capital != 100_000.0

    def test_no_data_returns_empty_metrics(self):
        engine = BacktestEngine()
        metrics = engine.run()
        assert metrics.total_trades == 0

    def test_buy_and_sell_produces_pnl(self):
        engine = BacktestEngine(initial_capital=100_000.0, slippage_rate=0, commission_rate=0)
        iid = InstrumentId("TEST", Exchange.SSE)
        bars = make_bars(10, start_price=100.0)
        engine.add_bar_data(iid, bars)

        strategy = SimpleTestStrategy()
        ctx = StrategyContext(engine, "test")
        strategy.attach(ctx)
        engine.add_strategy(strategy)

        metrics = engine.run()
        # 价格每根K线涨1元，第2根买入(开盘约102.5)，第8根卖出(开盘约108.5)
        # 应有正收益
        assert metrics.total_return > 0

    def test_trade_records_keep_entry_after_flat(self):
        """平仓后入场价/时间不应被清零；多轮交易各自独立。"""

        class TwoRoundStrategy(BarSeriesStrategy):
            def __init__(self):
                super().__init__(strategy_id="two_round")
                self._n = 0

            def on_init(self):
                pass

            def on_bar_update(self, bar: Bar):
                self._n += 1
                if self._n == 2:
                    self.ctx.buy_market(bar.instrument_id, 10)
                elif self._n == 4:
                    self.ctx.sell_market(bar.instrument_id, 10)
                elif self._n == 6:
                    self.ctx.buy_market(bar.instrument_id, 10)
                elif self._n == 8:
                    self.ctx.sell_market(bar.instrument_id, 10)

        engine = BacktestEngine(initial_capital=100_000.0, slippage_rate=0, commission_rate=0)
        iid = InstrumentId("TEST", Exchange.SSE)
        bars = make_bars(10, start_price=100.0)
        engine.add_bar_data(iid, bars)
        strategy = TwoRoundStrategy()
        strategy.attach(StrategyContext(engine, "two_round"))
        engine.add_strategy(strategy)
        engine.run()

        trades = engine.trade_records
        assert len(trades) == 2
        assert trades[0].entry_price > 0
        assert trades[1].entry_price > 0
        assert trades[0].entry_time < trades[1].entry_time
        assert trades[0].exit_time < trades[1].entry_time
