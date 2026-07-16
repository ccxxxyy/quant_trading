"""海龟交易策略模板 - 经典的突破跟踪系统。"""

from __future__ import annotations

from collections import deque
from decimal import Decimal

from quant_trading.model.instrument import InstrumentId
from quant_trading.model.market import Bar
from quant_trading.strategy.base import BarSeriesStrategy


class TurtleTradingStrategy(BarSeriesStrategy):
    """海龟交易策略（Turtle Trading）。

    海龟交易法是 1980 年代由理查德·丹尼斯（Richard Dennis）发明的经典趋势跟踪系统。
    核心思想：价格突破N日最高价时做多入场，跌破M日最低价时止损出场。

    规则：
        1. 入场信号：价格突破过去 entry_period 天的最高价 → 买入做多
        2. 出场信号：价格跌破过去 exit_period 天的最低价 → 卖出平仓
        3. 仓位管理：基于 ATR（真实波幅均值）动态调整下单数量
        4. 止损：持仓亏损超过 2 × ATR 时强制止损

    参数：
        entry_period: 入场通道周期（默认20天，即唐奇安通道上轨）
        exit_period: 出场通道周期（默认10天，即唐奇安通道下轨）
        atr_period: ATR 计算周期（默认20天）
        risk_pct: 每笔交易风险占总资金的比例（默认1%）
        max_units: 同方向最大加仓次数（默认4次）
        quantity: 基础下单数量（默认100股）
        instrument_id: 目标交易标的
    """

    def __init__(self, params: dict | None = None, **kwargs) -> None:
        params = params or {}
        params.setdefault("entry_period", 20)
        params.setdefault("exit_period", 10)
        params.setdefault("atr_period", 20)
        params.setdefault("risk_pct", 0.01)
        params.setdefault("max_units", 4)
        params.setdefault("quantity", 100)
        super().__init__(strategy_id="TurtleTrading", params=params, **kwargs)
        self._instrument_id: InstrumentId | None = None
        self._highs: deque[Decimal] = deque(maxlen=params["entry_period"])
        self._lows: deque[Decimal] = deque(maxlen=params["entry_period"])
        self._tr_values: deque[Decimal] = deque(maxlen=params["atr_period"])
        self._prev_close: Decimal | None = None
        self._entry_price: Decimal | None = None
        self._units_held: int = 0

    def on_init(self) -> None:
        instrument_str = self._params.get("instrument_id")
        if instrument_str:
            self._instrument_id = InstrumentId.from_str(instrument_str)

    def on_bar_update(self, bar: Bar) -> None:
        if self._instrument_id and bar.instrument_id != self._instrument_id:
            return

        instrument_id = bar.instrument_id
        entry_period = self._params["entry_period"]
        exit_period = self._params["exit_period"]

        # 计算真实波幅（True Range）
        if self._prev_close is not None:
            tr = max(
                bar.high - bar.low,
                abs(bar.high - self._prev_close),
                abs(bar.low - self._prev_close),
            )
            self._tr_values.append(tr)

        # 先用历史数据计算通道（不含当前 bar），再追加当前 bar
        can_trade = (
            len(self._highs) >= entry_period
            and len(self._tr_values) >= self._params["atr_period"]
        )

        if can_trade:
            # 计算 ATR
            atr = sum(self._tr_values) / len(self._tr_values)

            # 唐奇安通道：用前 N 日数据（不含当前 bar）
            channel_high = max(list(self._highs)[-entry_period:])
            exit_lows = list(self._lows)[-exit_period:]
            channel_low = min(exit_lows) if exit_lows else bar.low

            # 追加当前 bar 的高低价
            self._highs.append(bar.high)
            self._lows.append(bar.low)
            self._prev_close = bar.close

            if atr == 0:
                return

            position = self.ctx.get_position(instrument_id)
            quantity = self._params["quantity"]
            max_units = self._params["max_units"]

            if position.is_flat:
                # 空仓：价格突破上轨 → 做多入场
                if bar.close > channel_high:
                    self.ctx.buy_market(instrument_id, quantity)
                    self._entry_price = bar.close
                    self._units_held = 1
            elif position.quantity > 0:
                # 止损检查：跌破出场下轨 或 亏损超过 2×ATR
                stop_price = self._entry_price - 2 * atr if self._entry_price else channel_low
                if bar.close < channel_low or bar.close < stop_price:
                    self.ctx.close_position(instrument_id)
                    self._entry_price = None
                    self._units_held = 0
                # 加仓：价格在入场价基础上每上涨 0.5×ATR 加仓一次
                elif (
                    self._entry_price
                    and self._units_held < max_units
                    and bar.close > self._entry_price + Decimal("0.5") * atr * self._units_held
                ):
                    self.ctx.buy_market(instrument_id, quantity)
                    self._units_held += 1
        else:
            # 数据不足时仅追加历史数据
            self._highs.append(bar.high)
            self._lows.append(bar.low)
            self._prev_close = bar.close

    def on_stop(self) -> None:
        self._highs.clear()
        self._lows.clear()
        self._tr_values.clear()
