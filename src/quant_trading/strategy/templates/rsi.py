"""RSI 反转策略模板 - 基于相对强弱指标的均值回归策略。"""

from __future__ import annotations

from decimal import Decimal

from quant_trading.model.instrument import InstrumentId
from quant_trading.model.market import Bar
from quant_trading.strategy.base import BarSeriesStrategy


class RSIReversionStrategy(BarSeriesStrategy):
    """RSI 均值回归策略。

    RSI（Relative Strength Index，相对强弱指标）是衡量价格涨跌速度的指标，
    取值范围 0~100。RSI 低于超卖线时买入，高于超买线时卖出。

    原理：
        - RSI < 30 → 市场超卖（跌得太多），价格可能反弹 → 买入信号
        - RSI > 70 → 市场超买（涨得太多），价格可能回落 → 卖出信号
        - RSI 回到 40~60 区间 → 恢复正常 → 平仓

    参数：
        rsi_period: RSI 计算周期（默认14天）
        oversold: 超卖阈值（默认30，低于此值触发买入）
        overbought: 超买阈值（默认70，高于此值触发卖出）
        exit_low: 平多仓的 RSI 阈值（默认50）
        exit_high: 平空仓的 RSI 阈值（默认50）
        quantity: 每次交易的下单数量（默认100股）
        instrument_id: 目标交易标的
    """

    def __init__(self, params: dict | None = None, **kwargs) -> None:
        params = params or {}
        params.setdefault("rsi_period", 14)
        params.setdefault("oversold", 30)
        params.setdefault("overbought", 70)
        params.setdefault("exit_low", 50)
        params.setdefault("exit_high", 50)
        params.setdefault("quantity", 100)
        super().__init__(strategy_id="RSIReversion", params=params, **kwargs)
        self._instrument_id: InstrumentId | None = None

    def on_init(self) -> None:
        instrument_str = self._params.get("instrument_id")
        if instrument_str:
            self._instrument_id = InstrumentId.from_str(instrument_str)

    def on_bar_update(self, bar: Bar) -> None:
        if self._instrument_id and bar.instrument_id != self._instrument_id:
            return

        instrument_id = bar.instrument_id
        closes = self.get_closes(instrument_id)
        period = self._params["rsi_period"]

        if len(closes) < period + 1:
            return

        rsi = self._compute_rsi(closes, period)
        if rsi is None:
            return

        quantity = self._params["quantity"]
        position = self.ctx.get_position(instrument_id)
        oversold = self._params["oversold"]
        overbought = self._params["overbought"]
        exit_low = self._params["exit_low"]
        exit_high = self._params["exit_high"]

        if position.is_flat:
            # 空仓时寻找入场信号
            if rsi < oversold:
                self.ctx.buy_market(instrument_id, quantity)
            elif rsi > overbought:
                self.ctx.sell_market(instrument_id, quantity)
        elif position.quantity > 0:
            # 持有多仓时，RSI 回到中性区域则平仓
            if rsi >= exit_low:
                self.ctx.close_position(instrument_id)
        elif position.quantity < 0:
            # 持有空仓时，RSI 回到中性区域则平仓
            if rsi <= exit_high:
                self.ctx.close_position(instrument_id)

    @staticmethod
    def _compute_rsi(closes: list[Decimal], period: int) -> float | None:
        """计算 RSI 指标值。"""
        if len(closes) < period + 1:
            return None

        gains = []
        losses = []
        for i in range(-period, 0):
            change = closes[i] - closes[i - 1]
            if change > 0:
                gains.append(float(change))
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(float(change)))

        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
