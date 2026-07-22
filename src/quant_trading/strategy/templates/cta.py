"""CTA策略模板 - 适用于期货和股票的趋势跟踪策略。"""

from __future__ import annotations

from decimal import Decimal

from quant_trading.model.instrument import InstrumentId
from quant_trading.model.market import Bar
from quant_trading.strategy.base import BarSeriesStrategy


class DualMovingAverageStrategy(BarSeriesStrategy):
    """经典双均线交叉策略。

    当快线上穿慢线时做多（金叉买入），
    当快线下穿慢线时平仓或做空（死叉卖出）。

    参数：
        fast_period: 快线均线周期（默认10日）
        slow_period: 慢线均线周期（默认30日）
        quantity: 每次交易的下单数量（默认100股）
        instrument_id: 目标交易标的（必填）
    """

    def __init__(self, params: dict | None = None, **kwargs) -> None:
        params = params or {}
        params.setdefault("fast_period", 10)
        params.setdefault("slow_period", 30)
        params.setdefault("quantity", 60)
        super().__init__(strategy_id="DualMA", params=params, **kwargs)
        self._instrument_id: InstrumentId | None = None
        self._prev_fast_ma: Decimal | None = None
        self._prev_slow_ma: Decimal | None = None

    def on_init(self) -> None:
        instrument_str = self._params.get("instrument_id")
        if instrument_str:
            self._instrument_id = InstrumentId.from_str(instrument_str)

    def on_bar_update(self, bar: Bar) -> None:
        if self._instrument_id and bar.instrument_id != self._instrument_id:
            return

        instrument_id = bar.instrument_id
        closes = self.get_closes(instrument_id)
        fast_period = self._params["fast_period"]
        slow_period = self._params["slow_period"]

        if len(closes) < slow_period:
            return

        fast_ma = sum(closes[-fast_period:]) / fast_period
        slow_ma = sum(closes[-slow_period:]) / slow_period

        if self._prev_fast_ma is None:
            self._prev_fast_ma = fast_ma
            self._prev_slow_ma = slow_ma
            return

        quantity = self._params["quantity"]
        position = self.ctx.get_position(instrument_id)

        # 金叉信号 - 快线上穿慢线，买入
        if self._prev_fast_ma <= self._prev_slow_ma and fast_ma > slow_ma:
            if position.quantity <= 0:
                if position.quantity < 0:
                    self.ctx.buy_market(instrument_id, abs(position.quantity))
                self.ctx.buy_market(instrument_id, quantity)

        # 死叉信号 - 快线下穿慢线，卖出
        elif self._prev_fast_ma >= self._prev_slow_ma and fast_ma < slow_ma:
            if position.quantity >= 0:
                if position.quantity > 0:
                    self.ctx.sell_market(instrument_id, position.quantity)
                self.ctx.sell_market(instrument_id, quantity)

        self._prev_fast_ma = fast_ma
        self._prev_slow_ma = slow_ma


class BollingerBandStrategy(BarSeriesStrategy):
    """布林带均值回归策略。

    价格触及布林带下轨时买入，触及上轨时卖出。

    参数：
        period: 布林带计算周期（默认20日）
        num_std: 标准差倍数（默认2.0）
        quantity: 每次交易的下单数量（默认100股）
    """

    def __init__(self, params: dict | None = None, **kwargs) -> None:
        params = params or {}
        params.setdefault("period", 20)
        params.setdefault("num_std", 2.0)
        params.setdefault("quantity", 60)
        super().__init__(strategy_id="BollingerBand", params=params, **kwargs)

    def on_init(self) -> None:
        pass

    def on_bar_update(self, bar: Bar) -> None:
        closes = self.get_closes(bar.instrument_id)
        period = self._params["period"]

        if len(closes) < period:
            return

        window = closes[-period:]
        mean = sum(window) / period
        variance = sum((x - mean) ** 2 for x in window) / period
        raw = variance.sqrt() if hasattr(variance, "sqrt") else variance ** Decimal("0.5")
        std = Decimal(str(raw))

        num_std = Decimal(str(self._params["num_std"]))
        upper_band = mean + num_std * std
        lower_band = mean - num_std * std

        quantity = self._params["quantity"]
        position = self.ctx.get_position(bar.instrument_id)
        price = bar.close

        if price <= lower_band and position.quantity <= 0:
            if position.quantity < 0:
                self.ctx.buy_market(bar.instrument_id, abs(position.quantity))
            self.ctx.buy_market(bar.instrument_id, quantity)

        elif price >= upper_band and position.quantity >= 0:
            if position.quantity > 0:
                self.ctx.sell_market(bar.instrument_id, position.quantity)
            self.ctx.sell_market(bar.instrument_id, quantity)

        elif position.quantity != 0 and abs(price - mean) < std * Decimal("0.5"):
            self.ctx.close_position(bar.instrument_id)
