"""因子策略模板 - 基于因子排序的截面选股策略。"""

from __future__ import annotations

from abc import abstractmethod
from decimal import Decimal

from quant_trading.model.instrument import InstrumentId
from quant_trading.model.market import Bar
from quant_trading.strategy.base import BaseStrategy


class FactorStrategy(BaseStrategy):
    """因子策略基类。

    因子策略对一组标的计算 Alpha 因子分数，
    按因子排名分配资金进行投资。

    参数：
        universe: 交易标的池的ID列表
        rebalance_interval: 每隔多少根K线调一次仓
        top_n: 持有排名前N的标的
        quantity_per_position: 每个持仓的下单数量
    """

    def __init__(self, params: dict | None = None, **kwargs) -> None:
        params = params or {}
        params.setdefault("rebalance_interval", 20)
        params.setdefault("top_n", 10)
        params.setdefault("quantity_per_position", 10)
        super().__init__(params=params, **kwargs)
        self._bar_count = 0
        self._universe: list[InstrumentId] = []
        self._latest_bars: dict[str, Bar] = {}

    def on_init(self) -> None:
        universe_strs = self._params.get("universe", [])
        self._universe = [InstrumentId.from_str(s) for s in universe_strs]

    def on_bar(self, bar: Bar) -> None:
        self._latest_bars[str(bar.instrument_id)] = bar
        self._bar_count += 1

        if self._bar_count % self._params["rebalance_interval"] == 0:
            self._rebalance()

    @abstractmethod
    def compute_factor(self, instrument_id: InstrumentId, bars: list[Bar]) -> float | None:
        """计算单个标的的 Alpha 因子分数。

        如果数据不足则返回 None。
        """
        ...

    def _rebalance(self) -> None:
        """基于因子分数进行组合调仓。"""
        scores: list[tuple[InstrumentId, float]] = []

        for instrument_id in self._universe:
            key = str(instrument_id)
            if key not in self._latest_bars:
                continue
            score = self.compute_factor(instrument_id, [])
            if score is not None:
                scores.append((instrument_id, score))

        if not scores:
            return

        # 按因子分数降序排列
        scores.sort(key=lambda x: x[1], reverse=True)
        top_n = self._params["top_n"]
        target_holdings = {s[0] for s in scores[:top_n]}

        quantity = self._params["quantity_per_position"]

        # 平仓不在目标持仓中的标的
        for key, position in list(self.ctx._engine.positions.items()):
            if not position.is_flat:
                instrument_id = position.instrument_id
                if instrument_id not in target_holdings:
                    self.ctx.close_position(instrument_id)

        # 建仓目标标的
        for instrument_id in target_holdings:
            position = self.ctx.get_position(instrument_id)
            if position.is_flat:
                self.ctx.buy_market(instrument_id, quantity)


class MomentumFactorStrategy(FactorStrategy):
    """动量因子策略 - 买入近期涨幅最大的标的（追涨策略）。"""

    def __init__(self, params: dict | None = None, **kwargs) -> None:
        params = params or {}
        params.setdefault("lookback", 20)
        super().__init__(strategy_id="MomentumFactor", params=params, **kwargs)
        self._price_history: dict[str, list[Decimal]] = {}

    def on_bar(self, bar: Bar) -> None:
        key = str(bar.instrument_id)
        if key not in self._price_history:
            self._price_history[key] = []
        self._price_history[key].append(bar.close)
        # 只保留有限的历史长度
        max_len = self._params["lookback"] + 10
        if len(self._price_history[key]) > max_len:
            self._price_history[key] = self._price_history[key][-max_len:]
        super().on_bar(bar)

    def compute_factor(self, instrument_id: InstrumentId, bars: list[Bar]) -> float | None:
        key = str(instrument_id)
        prices = self._price_history.get(key, [])
        lookback = self._params["lookback"]

        if len(prices) < lookback:
            return None

        # 动量 = 回看期内的涨跌幅
        start_price = prices[-lookback]
        end_price = prices[-1]
        if start_price == 0:
            return None
        return float((end_price - start_price) / start_price)
