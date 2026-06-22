"""模拟撮合引擎 - 在回测中模拟交易所的订单撮合过程。"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from quant_trading.model.market import Bar, Tick
from quant_trading.model.order import Fill, Order, OrderSide, OrderStatus, OrderType

logger = logging.getLogger(__name__)


class MatchingEngine:
    """模拟订单撮合，支持可配置的滑点和手续费。

    支持市价单、限价单和止损单，基于K线数据进行撮合。
    滑点模型为价格的固定百分比。
    """

    def __init__(
        self,
        commission_rate: Decimal = Decimal("0.0003"),
        slippage_rate: Decimal = Decimal("0.0001"),
    ) -> None:
        self._commission_rate = commission_rate
        self._slippage_rate = slippage_rate
        self._pending_orders: list[Order] = []

    def submit_order(self, order: Order) -> None:
        """将订单提交到撮合引擎。"""
        order.status = OrderStatus.SUBMITTED
        self._pending_orders.append(order)

    def cancel_order(self, order_id: str) -> bool:
        """撤销一个挂起的订单。"""
        for order in self._pending_orders:
            if order.order_id == order_id and order.is_active:
                order.status = OrderStatus.CANCELLED
                order.updated_at = datetime.now()
                self._pending_orders.remove(order)
                return True
        return False

    def match_bar(self, bar: Bar) -> list[Fill]:
        """尝试用一根K线撮合所有挂起的订单，返回成交列表。"""
        fills: list[Fill] = []
        remaining: list[Order] = []

        for order in self._pending_orders:
            fill = self._try_match(order, bar)
            if fill:
                fills.append(fill)
            elif order.is_active:
                remaining.append(order)

        self._pending_orders = remaining
        return fills

    def match_tick(self, tick: Tick) -> list[Fill]:
        """尝试用一个逐笔行情撮合所有挂起的订单。"""
        fills: list[Fill] = []
        remaining: list[Order] = []

        for order in self._pending_orders:
            fill = self._try_match_tick(order, tick)
            if fill:
                fills.append(fill)
            elif order.is_active:
                remaining.append(order)

        self._pending_orders = remaining
        return fills

    def _try_match(self, order: Order, bar: Bar) -> Fill | None:
        """尝试基于K线数据撮合一个订单。"""
        if order.order_type == OrderType.MARKET:
            fill_price = self._apply_slippage(bar.open, order.side)
            return self._create_fill(order, fill_price, bar.timestamp)

        elif order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY and bar.low <= order.price:
                fill_price = min(order.price, bar.open)
                fill_price = self._apply_slippage(fill_price, order.side)
                return self._create_fill(order, fill_price, bar.timestamp)
            elif order.side == OrderSide.SELL and bar.high >= order.price:
                fill_price = max(order.price, bar.open)
                fill_price = self._apply_slippage(fill_price, order.side)
                return self._create_fill(order, fill_price, bar.timestamp)

        elif order.order_type == OrderType.STOP:
            if order.side == OrderSide.BUY and bar.high >= order.stop_price:
                fill_price = self._apply_slippage(order.stop_price, order.side)
                return self._create_fill(order, fill_price, bar.timestamp)
            elif order.side == OrderSide.SELL and bar.low <= order.stop_price:
                fill_price = self._apply_slippage(order.stop_price, order.side)
                return self._create_fill(order, fill_price, bar.timestamp)

        return None

    def _try_match_tick(self, order: Order, tick: Tick) -> Fill | None:
        """尝试基于逐笔行情撮合一个订单。"""
        if order.order_type == OrderType.MARKET:
            price = tick.ask_price if order.side == OrderSide.BUY else tick.bid_price
            fill_price = self._apply_slippage(price, order.side)
            return self._create_fill(order, fill_price, tick.timestamp)

        elif order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY and tick.ask_price <= order.price:
                return self._create_fill(order, order.price, tick.timestamp)
            elif order.side == OrderSide.SELL and tick.bid_price >= order.price:
                return self._create_fill(order, order.price, tick.timestamp)

        return None

    def _apply_slippage(self, price: Decimal, side: OrderSide) -> Decimal:
        """对成交价格施加滑点。"""
        slippage = price * self._slippage_rate
        if side == OrderSide.BUY:
            return price + slippage  # 买入时滑点使价格略高
        return price - slippage  # 卖出时滑点使价格略低

    def _create_fill(self, order: Order, price: Decimal, timestamp: datetime) -> Fill:
        """创建成交回报并更新订单状态。"""
        quantity = order.remaining_quantity
        commission = price * quantity * self._commission_rate

        fill = Fill(
            order_id=order.order_id,
            instrument_id=order.instrument_id,
            side=order.side,
            price=price,
            quantity=quantity,
            commission=commission,
            timestamp=timestamp,
        )

        # 更新订单状态
        order.filled_quantity += quantity
        order.avg_fill_price = price
        order.commission += commission
        order.status = OrderStatus.FILLED
        order.updated_at = timestamp

        return fill

    @property
    def pending_count(self) -> int:
        return len(self._pending_orders)

    def reset(self) -> None:
        self._pending_orders.clear()
