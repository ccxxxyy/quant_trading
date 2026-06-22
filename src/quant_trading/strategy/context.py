"""策略上下文 - 策略与交易引擎之间的统一桥梁。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

from quant_trading.model.instrument import InstrumentId
from quant_trading.model.order import Order, OrderSide, OrderType
from quant_trading.model.position import Position

if TYPE_CHECKING:
    pass


class TradingContext(Protocol):
    """定义策略可以执行的操作的协议。"""

    def submit_order(self, order: Order) -> str: ...
    def cancel_order(self, order_id: str) -> bool: ...
    def get_position(self, instrument_id: InstrumentId) -> Position: ...
    @property
    def clock_now(self) -> datetime: ...


class StrategyContext:
    """连接策略逻辑与交易引擎（回测或实盘）的桥梁。

    提供常用交易操作的便捷方法。
    """

    def __init__(self, engine: TradingContext, strategy_id: str = "") -> None:
        self._engine = engine
        self._strategy_id = strategy_id

    @property
    def now(self) -> datetime:
        return self._engine.clock_now

    def get_position(self, instrument_id: InstrumentId) -> Position:
        return self._engine.get_position(instrument_id)

    def buy_market(self, instrument_id: InstrumentId, quantity: int) -> str:
        """提交市价买入订单。"""
        order = Order(
            instrument_id=instrument_id,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=quantity,
            strategy_id=self._strategy_id,
        )
        return self._engine.submit_order(order)

    def sell_market(self, instrument_id: InstrumentId, quantity: int) -> str:
        """提交市价卖出订单。"""
        order = Order(
            instrument_id=instrument_id,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=quantity,
            strategy_id=self._strategy_id,
        )
        return self._engine.submit_order(order)

    def buy_limit(self, instrument_id: InstrumentId, quantity: int, price: Decimal) -> str:
        """提交限价买入订单。"""
        order = Order(
            instrument_id=instrument_id,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=price,
            strategy_id=self._strategy_id,
        )
        return self._engine.submit_order(order)

    def sell_limit(self, instrument_id: InstrumentId, quantity: int, price: Decimal) -> str:
        """提交限价卖出订单。"""
        order = Order(
            instrument_id=instrument_id,
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=price,
            strategy_id=self._strategy_id,
        )
        return self._engine.submit_order(order)

    def buy_stop(self, instrument_id: InstrumentId, quantity: int, stop_price: Decimal) -> str:
        """提交止损买入订单（用于突破入场）。"""
        order = Order(
            instrument_id=instrument_id,
            side=OrderSide.BUY,
            order_type=OrderType.STOP,
            quantity=quantity,
            stop_price=stop_price,
            strategy_id=self._strategy_id,
        )
        return self._engine.submit_order(order)

    def sell_stop(self, instrument_id: InstrumentId, quantity: int, stop_price: Decimal) -> str:
        """提交止损卖出订单（用于止损出场）。"""
        order = Order(
            instrument_id=instrument_id,
            side=OrderSide.SELL,
            order_type=OrderType.STOP,
            quantity=quantity,
            stop_price=stop_price,
            strategy_id=self._strategy_id,
        )
        return self._engine.submit_order(order)

    def cancel(self, order_id: str) -> bool:
        return self._engine.cancel_order(order_id)

    def close_position(self, instrument_id: InstrumentId) -> str | None:
        """一键平仓 - 关闭某标的的全部持仓。"""
        pos = self.get_position(instrument_id)
        if pos.is_flat:
            return None
        if pos.quantity > 0:
            return self.sell_market(instrument_id, pos.quantity)
        else:
            return self.buy_market(instrument_id, abs(pos.quantity))
