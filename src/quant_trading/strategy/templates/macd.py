"""MACD 策略模板 - 基于指数移动平均线交叉的趋势策略。"""

from __future__ import annotations

from decimal import Decimal

from quant_trading.model.instrument import InstrumentId
from quant_trading.model.market import Bar
from quant_trading.strategy.base import BarSeriesStrategy


class MACDStrategy(BarSeriesStrategy):
    """MACD 趋势跟踪策略。

    MACD（Moving Average Convergence Divergence，移动平均收敛发散指标）
    是最常用的技术分析指标之一。

    计算方法：
        - 快线 DIF = EMA(close, fast) - EMA(close, slow)
        - 信号线 DEA = EMA(DIF, signal)
        - 柱状图 MACD = 2 × (DIF - DEA)

    交易规则：
        - DIF 上穿 DEA（金叉） → 买入做多
        - DIF 下穿 DEA（死叉） → 卖出平仓
        - 柱状图由负转正 → 趋势转强
        - 柱状图由正转负 → 趋势转弱

    参数：
        fast_period: 快线 EMA 周期（默认12天）
        slow_period: 慢线 EMA 周期（默认26天）
        signal_period: 信号线 EMA 周期（默认9天）
        quantity: 每次交易的下单数量（默认100股）
        instrument_id: 目标交易标的
    """

    def __init__(self, params: dict | None = None, **kwargs) -> None:
        params = params or {}
        params.setdefault("fast_period", 12)
        params.setdefault("slow_period", 26)
        params.setdefault("signal_period", 9)
        params.setdefault("quantity", 100)
        super().__init__(strategy_id="MACD", params=params, **kwargs)
        self._instrument_id: InstrumentId | None = None
        self._ema_fast: Decimal | None = None
        self._ema_slow: Decimal | None = None
        self._ema_signal: Decimal | None = None
        self._prev_dif: Decimal | None = None
        self._prev_dea: Decimal | None = None
        self._bar_count: int = 0

    def on_init(self) -> None:
        instrument_str = self._params.get("instrument_id")
        if instrument_str:
            self._instrument_id = InstrumentId.from_str(instrument_str)

    def on_bar_update(self, bar: Bar) -> None:
        if self._instrument_id and bar.instrument_id != self._instrument_id:
            return

        instrument_id = bar.instrument_id
        price = bar.close
        self._bar_count += 1

        fast_period = self._params["fast_period"]
        slow_period = self._params["slow_period"]
        signal_period = self._params["signal_period"]

        # 计算 EMA（指数移动平均线）
        if self._ema_fast is None:
            self._ema_fast = price
            self._ema_slow = price
            return

        fast_k = Decimal(str(2.0 / (fast_period + 1)))
        slow_k = Decimal(str(2.0 / (slow_period + 1)))
        signal_k = Decimal(str(2.0 / (signal_period + 1)))

        self._ema_fast = price * fast_k + self._ema_fast * (1 - fast_k)
        self._ema_slow = price * slow_k + self._ema_slow * (1 - slow_k)

        # DIF = 快线EMA - 慢线EMA
        dif = self._ema_fast - self._ema_slow

        # DEA = DIF 的 EMA（信号线）
        if self._ema_signal is None:
            self._ema_signal = dif
            self._prev_dif = dif
            self._prev_dea = dif
            return

        dea = dif * signal_k + self._ema_signal * (1 - signal_k)
        self._ema_signal = dea

        # 需要等待足够的数据后才开始交易
        if self._bar_count < slow_period:
            self._prev_dif = dif
            self._prev_dea = dea
            return

        quantity = self._params["quantity"]
        position = self.ctx.get_position(instrument_id)

        # 金叉：DIF 上穿 DEA
        if self._prev_dif is not None and self._prev_dif <= self._prev_dea and dif > dea:
            if position.quantity <= 0:
                if position.quantity < 0:
                    self.ctx.buy_market(instrument_id, abs(position.quantity))
                self.ctx.buy_market(instrument_id, quantity)

        # 死叉：DIF 下穿 DEA
        elif self._prev_dif is not None and self._prev_dif >= self._prev_dea and dif < dea:
            if position.quantity > 0:
                self.ctx.close_position(instrument_id)

        self._prev_dif = dif
        self._prev_dea = dea
