"""订单模型 - 订单完整生命周期的表示。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from quant_trading.model.instrument import InstrumentId


class OrderSide(Enum):
    BUY = "buy"  # 买入
    SELL = "sell"  # 卖出


class OrderType(Enum):
    MARKET = "market"  # 市价单（以当前市价立即成交）
    LIMIT = "limit"  # 限价单（指定价格，到价才成交）
    STOP = "stop"  # 止损单（价格触及止损价时触发）
    STOP_LIMIT = "stop_limit"  # 止损限价单（触及止损价后以限价挂单）


class OrderStatus(Enum):
    PENDING = "pending"  # 待提交
    SUBMITTED = "submitted"  # 已提交
    PARTIAL_FILLED = "partial_filled"  # 部分成交
    FILLED = "filled"  # 全部成交
    CANCELLED = "cancelled"  # 已撤销
    REJECTED = "rejected"  # 被拒绝


class TimeInForce(Enum):
    GTC = "gtc"  # 撤单前一直有效（Good Till Cancelled）
    IOC = "ioc"  # 立即成交否则撤销（Immediate Or Cancel）
    FOK = "fok"  # 全部成交否则全部撤销（Fill Or Kill）
    DAY = "day"  # 当日有效


@dataclass(slots=True)
class Order:
    """可变的订单对象，跟踪其从创建到成交的完整生命周期。"""

    instrument_id: InstrumentId
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: Decimal = Decimal(0)  # 限价单的价格
    stop_price: Decimal = Decimal(0)  # 止损价
    time_in_force: TimeInForce = TimeInForce.GTC
    order_id: str = field(default_factory=lambda: str(uuid4()))
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0  # 已成交数量
    avg_fill_price: Decimal = Decimal(0)  # 平均成交价格
    commission: Decimal = Decimal(0)  # 累计手续费
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    strategy_id: str = ""  # 发出订单的策略ID
    broker_order_id: str = ""  # 券商返回的订单ID
    reject_reason: str = ""  # 拒绝原因

    @property
    def remaining_quantity(self) -> int:
        """剩余未成交数量。"""
        return self.quantity - self.filled_quantity

    @property
    def is_active(self) -> bool:
        """订单是否仍处于活跃状态（尚未完成）。"""
        return self.status in (
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIAL_FILLED,
        )

    @property
    def is_completed(self) -> bool:
        """订单是否已完成（成交/撤销/拒绝）。"""
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        )

    @property
    def notional(self) -> Decimal:
        """订单的名义价值（价格 × 数量）。"""
        price = self.avg_fill_price if self.avg_fill_price > 0 else self.price
        return price * self.quantity


@dataclass(frozen=True, slots=True)
class Fill:
    """订单的成交回报（不可变）。"""

    order_id: str
    instrument_id: InstrumentId
    side: OrderSide
    price: Decimal  # 成交价格
    quantity: int  # 成交数量
    commission: Decimal  # 本次成交的手续费
    timestamp: datetime
    fill_id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def notional(self) -> Decimal:
        """本次成交的名义价值。"""
        return self.price * self.quantity
