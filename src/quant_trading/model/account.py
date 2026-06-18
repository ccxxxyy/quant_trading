"""账户模型 - 跟踪资金、权益和保证金。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from quant_trading.model.instrument import Currency


@dataclass(slots=True)
class Account:
    """交易账户状态。"""

    account_id: str
    currency: Currency = Currency.CNY
    balance: Decimal = Decimal(0)  # 账户余额
    available: Decimal = Decimal(0)  # 可用资金
    frozen: Decimal = Decimal(0)  # 冻结资金（已下单未成交部分）
    margin: Decimal = Decimal(0)  # 已使用保证金
    unrealized_pnl: Decimal = Decimal(0)  # 未实现盈亏（浮盈浮亏）
    realized_pnl: Decimal = Decimal(0)  # 已实现盈亏
    commission: Decimal = Decimal(0)  # 累计手续费
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def equity(self) -> Decimal:
        """净清算价值（总权益）= 账户余额 + 浮盈浮亏。"""
        return self.balance + self.unrealized_pnl

    @property
    def margin_ratio(self) -> Decimal:
        """当前保证金使用率 = 已用保证金 / 总权益。"""
        if self.equity == 0:
            return Decimal(0)
        return self.margin / self.equity

    def freeze(self, amount: Decimal) -> bool:
        """冻结资金（用于提交订单时预扣资金）。"""
        if amount > self.available:
            return False
        self.available -= amount
        self.frozen += amount
        return True

    def unfreeze(self, amount: Decimal) -> None:
        """解冻资金（订单撤销时释放冻结的资金）。"""
        self.frozen -= amount
        self.available += amount

    def settle(self, pnl: Decimal, commission: Decimal) -> None:
        """结算已完成的交易（更新余额、盈亏和手续费）。"""
        self.realized_pnl += pnl
        self.commission += commission
        self.balance += pnl - commission
        self.available += pnl - commission
        self.updated_at = datetime.now()
