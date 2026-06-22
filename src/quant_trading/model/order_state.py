"""订单状态机 - 管理订单生命周期的合法状态流转。

订单状态流转图：
    PENDING → SUBMITTED → PARTIALLY_FILLED → FILLED
                       → CANCELLED
                       → REJECTED
    PENDING → REJECTED（前置风控拒绝）

任何终态（FILLED, CANCELLED, REJECTED）不可再变更。
"""

from __future__ import annotations

import logging

from quant_trading.model.order import Order, OrderStatus

logger = logging.getLogger(__name__)

# 合法状态转换表：当前状态 -> 允许转到的状态集合
VALID_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {
        OrderStatus.SUBMITTED,
        OrderStatus.REJECTED,
    },
    OrderStatus.SUBMITTED: {
        OrderStatus.PARTIAL_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
    },
    OrderStatus.PARTIAL_FILLED: {
        OrderStatus.PARTIAL_FILLED,  # 继续部分成交
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.FILLED: set(),  # 终态
    OrderStatus.CANCELLED: set(),  # 终态
    OrderStatus.REJECTED: set(),  # 终态
}


class OrderStateMachine:
    """订单状态机，确保状态流转合法。"""

    @staticmethod
    def can_transition(order: Order, target: OrderStatus) -> bool:
        """检查订单是否可以从当前状态转到目标状态。"""
        current = order.status
        valid = VALID_TRANSITIONS.get(current, set())
        return target in valid

    @staticmethod
    def transition(order: Order, target: OrderStatus, reason: str = "") -> bool:
        """执行状态转换。如果转换合法则更新订单状态并返回 True，否则返回 False。"""
        current = order.status

        if not OrderStateMachine.can_transition(order, target):
            logger.warning(
                f"Order {order.order_id}: illegal transition {current.value} -> {target.value}"
            )
            return False

        order.status = target
        if target == OrderStatus.REJECTED and reason:
            order.reject_reason = reason

        logger.debug(
            f"Order {order.order_id}: {current.value} -> {target.value}"
            + (f" ({reason})" if reason else "")
        )
        return True

    @staticmethod
    def is_terminal(order: Order) -> bool:
        """检查订单是否处于终态。"""
        return order.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        )

    @staticmethod
    def is_active(order: Order) -> bool:
        """检查订单是否处于活跃状态（可操作）。"""
        return order.status in (
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIAL_FILLED,
        )
