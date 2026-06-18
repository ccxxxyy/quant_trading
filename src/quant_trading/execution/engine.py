"""执行引擎 - 将订单经过风控检查后路由到交易网关。"""

from __future__ import annotations

import logging
from decimal import Decimal

from quant_trading.core.event import Event, EventBus, EventType
from quant_trading.model.account import Account
from quant_trading.model.order import Fill, Order, OrderStatus
from quant_trading.model.position import Position
from quant_trading.risk.engine import RiskCheckResult, RiskEngine

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """将订单经过风控检查后转发到对应的交易网关。

    回测模式下订单直接发送到模拟撮合引擎，
    实盘模式下订单路由到对应的券商网关。
    """

    def __init__(
        self,
        event_bus: EventBus,
        risk_engine: RiskEngine,
        account: Account,
        positions: dict[str, Position],
    ) -> None:
        self._event_bus = event_bus
        self._risk_engine = risk_engine
        self._account = account
        self._positions = positions
        self._active_orders: dict[str, Order] = {}
        self._order_history: list[Order] = []

    def submit_order(self, order: Order) -> str:
        """提交订单（含风控检查）。"""
        # 前置风控检查
        decision = self._risk_engine.pre_trade_check(
            order=order,
            account=self._account,
            positions=self._positions,
        )

        if decision.result == RiskCheckResult.REJECTED:
            order.status = OrderStatus.REJECTED
            order.reject_reason = decision.reason
            self._event_bus.publish(
                Event(type=EventType.ORDER, data=order, timestamp=order.created_at)
            )
            logger.warning(f"Order rejected: {decision.reason}")
            return order.order_id

        # 记录并发送
        self._active_orders[order.order_id] = order
        self._order_history.append(order)
        self._risk_engine.record_order()

        self._event_bus.publish(Event(type=EventType.ORDER, data=order, timestamp=order.created_at))
        return order.order_id

    def on_fill(self, fill: Fill) -> None:
        """处理来自网关的成交回报。"""
        order = self._active_orders.get(fill.order_id)
        if order and order.is_completed:
            del self._active_orders[fill.order_id]

        # 更新持仓
        key = str(fill.instrument_id)
        if key not in self._positions:
            self._positions[key] = Position(instrument_id=fill.instrument_id)
        self._positions[key].apply_fill(fill)

        # 更新风控盈亏追踪
        self._risk_engine.update_daily_pnl(Decimal(str(self._positions[key].realized_pnl)))

        # 发送成交事件
        self._event_bus.publish(Event(type=EventType.FILL, data=fill, timestamp=fill.timestamp))

    def cancel_order(self, order_id: str) -> bool:
        """撤销一个活跃的订单。"""
        order = self._active_orders.get(order_id)
        if order and order.is_active:
            order.status = OrderStatus.CANCELLED
            del self._active_orders[order_id]
            return True
        return False

    @property
    def active_orders(self) -> dict[str, Order]:
        return dict(self._active_orders)

    @property
    def order_count(self) -> int:
        return len(self._order_history)
