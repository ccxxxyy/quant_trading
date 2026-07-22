"""套利策略模板 - 配对交易/价差交易策略。"""

from __future__ import annotations

from collections import deque
from decimal import Decimal

from quant_trading.model.instrument import InstrumentId
from quant_trading.model.market import Bar
from quant_trading.strategy.base import BarSeriesStrategy


class PairTradingStrategy(BarSeriesStrategy):
    """统计配对交易策略。

    跟踪两个高度相关标的之间的价差，
    当价差偏离正常范围（超过阈值）时入场，
    当价差回归均值时出场。

    参数：
        instrument_a: A腿标的代码
        instrument_b: B腿标的代码（对冲腿）
        lookback: 计算价差统计量的回看周期
        entry_threshold: 入场的 Z-Score 阈值（默认2.0，即偏离2个标准差时入场）
        exit_threshold: 出场的 Z-Score 阈值（默认0.5，即回归到0.5个标准差内时出场）
        quantity: 每腿的下单数量
        hedge_ratio: B腿与A腿的对冲比例（默认1.0，即1:1配对）
    """

    def __init__(self, params: dict | None = None, **kwargs) -> None:
        params = params or {}
        params.setdefault("lookback", 60)
        params.setdefault("entry_threshold", 2.0)
        params.setdefault("exit_threshold", 0.5)
        params.setdefault("quantity", 60)
        params.setdefault("hedge_ratio", 1.0)
        super().__init__(strategy_id="PairTrading", params=params, **kwargs)
        self._instrument_a: InstrumentId | None = None
        self._instrument_b: InstrumentId | None = None
        self._spread_history: deque[Decimal] = deque(maxlen=params["lookback"])
        self._in_position = False
        self._position_side: str = ""

    def on_init(self) -> None:
        a_str = self._params.get("instrument_a")
        b_str = self._params.get("instrument_b")
        if a_str:
            self._instrument_a = InstrumentId.from_str(a_str)
        if b_str:
            self._instrument_b = InstrumentId.from_str(b_str)

    def on_bar_update(self, bar: Bar) -> None:
        if not self._instrument_a or not self._instrument_b:
            return

        # 获取两腿最新价格
        closes_a = self.get_closes(self._instrument_a)
        closes_b = self.get_closes(self._instrument_b)

        if not closes_a or not closes_b:
            return

        # 计算价差
        hedge_ratio = Decimal(str(self._params["hedge_ratio"]))
        spread = closes_a[-1] - hedge_ratio * closes_b[-1]
        self._spread_history.append(spread)

        lookback = self._params["lookback"]
        if len(self._spread_history) < lookback:
            return

        # 计算 Z-Score（标准化得分）
        spread_list = list(self._spread_history)
        mean_spread = sum(spread_list) / len(spread_list)
        variance = sum((s - mean_spread) ** 2 for s in spread_list) / len(spread_list)
        std_spread = Decimal(str(float(variance) ** 0.5))

        if std_spread == 0:
            return

        z_score = float((spread - mean_spread) / std_spread)

        entry_threshold = self._params["entry_threshold"]
        exit_threshold = self._params["exit_threshold"]
        quantity = self._params["quantity"]
        hedge_qty = int(quantity * float(hedge_ratio))

        if not self._in_position:
            # 入场：价差偏高 → 做空价差（卖A买B）
            if z_score > entry_threshold:
                self.ctx.sell_market(self._instrument_a, quantity)
                self.ctx.buy_market(self._instrument_b, hedge_qty)
                self._in_position = True
                self._position_side = "short_spread"

            # 入场：价差偏低 → 做多价差（买A卖B）
            elif z_score < -entry_threshold:
                self.ctx.buy_market(self._instrument_a, quantity)
                self.ctx.sell_market(self._instrument_b, hedge_qty)
                self._in_position = True
                self._position_side = "long_spread"

        else:
            # 出场：价差回归均值
            if abs(z_score) < exit_threshold:
                self.ctx.close_position(self._instrument_a)
                self.ctx.close_position(self._instrument_b)
                self._in_position = False
                self._position_side = ""
