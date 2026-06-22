"""持仓模型 - 跟踪交易标的的持有数量和盈亏。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from quant_trading.model.instrument import InstrumentId
from quant_trading.model.order import Fill, OrderSide


class PositionSide:
    LONG = "long"  # 做多（持有正数量）
    SHORT = "short"  # 做空（持有负数量）
    FLAT = "flat"  # 空仓（不持有任何数量）


@dataclass(slots=True)
class Position:
    """跟踪单个交易标的的持仓状态。"""

    instrument_id: InstrumentId
    quantity: int = 0  # 持仓数量（正=做多，负=做空）
    avg_cost: Decimal = Decimal(0)  # 持仓均价
    realized_pnl: Decimal = Decimal(0)  # 已实现盈亏（已平仓部分的利润）
    commission: Decimal = Decimal(0)  # 累计手续费
    opened_at: datetime | None = None  # 开仓时间
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def side(self) -> str:
        if self.quantity > 0:
            return PositionSide.LONG
        elif self.quantity < 0:
            return PositionSide.SHORT
        return PositionSide.FLAT

    @property
    def is_flat(self) -> bool:
        """是否为空仓。"""
        return self.quantity == 0

    @property
    def abs_quantity(self) -> int:
        """持仓数量的绝对值。"""
        return abs(self.quantity)

    @property
    def market_value(self) -> Decimal:
        """持仓市值 = 均价 × 数量。"""
        return self.avg_cost * self.quantity

    def unrealized_pnl(self, current_price: Decimal) -> Decimal:
        """计算未实现盈亏（浮盈浮亏）= (当前价 - 均价) × 持仓数量。"""
        if self.quantity == 0:
            return Decimal(0)
        return (current_price - self.avg_cost) * self.quantity

    def total_pnl(self, current_price: Decimal) -> Decimal:
        """计算总盈亏 = 已实现盈亏 + 未实现盈亏 - 手续费。"""
        return self.realized_pnl + self.unrealized_pnl(current_price) - self.commission

    def apply_fill(self, fill: Fill) -> None:
        """用新的成交回报更新持仓。"""
        self.commission += fill.commission
        self.updated_at = fill.timestamp

        if fill.side == OrderSide.BUY:
            new_quantity = self.quantity + fill.quantity
        else:
            new_quantity = self.quantity - fill.quantity

        # 判断是开仓还是平仓
        if fill.side == OrderSide.BUY:
            if self.quantity >= 0:
                # 加仓做多 或 新开多仓
                total_cost = self.avg_cost * self.quantity + fill.price * fill.quantity
                self.quantity = new_quantity
                self.avg_cost = total_cost / self.quantity if self.quantity != 0 else Decimal(0)
            else:
                # 买入平空仓
                closed_qty = min(fill.quantity, abs(self.quantity))
                self.realized_pnl += (self.avg_cost - fill.price) * closed_qty
                remaining_buy = fill.quantity - closed_qty
                if remaining_buy > 0:
                    self.avg_cost = fill.price
                self.quantity = new_quantity
        else:
            if self.quantity <= 0:
                # 加仓做空 或 新开空仓
                total_cost = abs(self.avg_cost * self.quantity) + fill.price * fill.quantity
                self.quantity = new_quantity
                self.avg_cost = (
                    total_cost / abs(self.quantity) if self.quantity != 0 else Decimal(0)
                )
            else:
                # 卖出平多仓
                closed_qty = min(fill.quantity, self.quantity)
                self.realized_pnl += (fill.price - self.avg_cost) * closed_qty
                remaining_sell = fill.quantity - closed_qty
                if remaining_sell > 0:
                    self.avg_cost = fill.price
                self.quantity = new_quantity

        if self.opened_at is None and not self.is_flat:
            self.opened_at = fill.timestamp
        elif self.is_flat:
            self.avg_cost = Decimal(0)
