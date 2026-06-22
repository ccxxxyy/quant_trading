"""风控引擎 - 交易前置检查和实时风险管理。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

from quant_trading.model.account import Account
from quant_trading.model.order import Order, OrderSide
from quant_trading.model.position import Position

logger = logging.getLogger(__name__)


class RiskCheckResult(Enum):
    PASSED = "passed"  # 通过
    REJECTED = "rejected"  # 拒绝
    WARNING = "warning"  # 警告


@dataclass
class RiskDecision:
    result: RiskCheckResult
    reason: str = ""
    order: Order | None = None


class RiskEngine:
    """交易前置检查和实时风险管理引擎。

    对以下维度执行限额控制：
    - 单标的持仓占总权益的比例上限
    - 单笔订单金额上限
    - 当日累计亏损上限
    - 下单频率上限
    - 持仓集中度
    """

    def __init__(
        self,
        max_position_pct: float = 0.25,
        max_single_order_pct: float = 0.10,
        max_daily_loss_pct: float = 0.05,
        max_order_frequency: int = 100,
    ) -> None:
        self._max_position_pct = Decimal(str(max_position_pct))
        self._max_single_order_pct = Decimal(str(max_single_order_pct))
        self._max_daily_loss_pct = Decimal(str(max_daily_loss_pct))
        self._max_order_frequency = max_order_frequency

        # 追踪状态
        self._daily_orders: list[datetime] = []
        self._daily_pnl: Decimal = Decimal(0)
        self._last_reset_date: datetime | None = None
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False
        logger.warning("Risk engine DISABLED")

    def pre_trade_check(
        self,
        order: Order,
        account: Account,
        positions: dict[str, Position],
        current_prices: dict[str, Decimal] | None = None,
    ) -> RiskDecision:
        """对订单执行所有前置风控检查。"""
        if not self._enabled:
            return RiskDecision(result=RiskCheckResult.PASSED, order=order)

        self._maybe_reset_daily(datetime.now())

        checks = [
            self._check_order_size(order, account),
            self._check_position_limit(order, account, positions, current_prices),
            self._check_daily_loss(account),
            self._check_order_frequency(),
        ]

        for decision in checks:
            if decision.result == RiskCheckResult.REJECTED:
                logger.warning(f"Order rejected by risk: {decision.reason}")
                return decision

        return RiskDecision(result=RiskCheckResult.PASSED, order=order)

    def record_order(self) -> None:
        """记录一次下单（用于频率追踪）。"""
        self._daily_orders.append(datetime.now())

    def update_daily_pnl(self, pnl: Decimal) -> None:
        """更新当日累计盈亏。"""
        self._daily_pnl += pnl

    def _check_order_size(self, order: Order, account: Account) -> RiskDecision:
        """检查单笔订单金额是否超出上限。"""
        if account.equity == 0:
            return RiskDecision(RiskCheckResult.REJECTED, "Zero equity")

        order_value = order.price * order.quantity if order.price > 0 else Decimal(0)
        if order_value > 0:
            order_pct = order_value / account.equity
            if order_pct > self._max_single_order_pct:
                return RiskDecision(
                    RiskCheckResult.REJECTED,
                    f"Order size {float(order_pct) * 100:.1f}% exceeds limit "
                    f"{float(self._max_single_order_pct) * 100:.1f}%",
                )

        return RiskDecision(RiskCheckResult.PASSED)

    def _check_position_limit(
        self,
        order: Order,
        account: Account,
        positions: dict[str, Position],
        current_prices: dict[str, Decimal] | None,
    ) -> RiskDecision:
        """检查成交后的持仓集中度是否超出上限。"""
        if account.equity == 0:
            return RiskDecision(RiskCheckResult.REJECTED, "Zero equity")

        key = str(order.instrument_id)
        current_pos = positions.get(key)
        current_qty = current_pos.quantity if current_pos else 0

        if order.side == OrderSide.BUY:
            new_qty = current_qty + order.quantity
        else:
            new_qty = current_qty - order.quantity

        # 估算持仓市值
        price = (
            order.price
            if order.price > 0
            else (current_prices.get(key, Decimal(0)) if current_prices else Decimal(0))
        )
        if price > 0:
            position_value = price * abs(new_qty)
            position_pct = position_value / account.equity
            if position_pct > self._max_position_pct:
                return RiskDecision(
                    RiskCheckResult.REJECTED,
                    f"Position concentration {float(position_pct) * 100:.1f}% exceeds "
                    f"limit {float(self._max_position_pct) * 100:.1f}%",
                )

        return RiskDecision(RiskCheckResult.PASSED)

    def _check_daily_loss(self, account: Account) -> RiskDecision:
        """检查当日累计亏损是否超出上限。"""
        if account.equity == 0:
            return RiskDecision(RiskCheckResult.REJECTED, "Zero equity")

        if self._daily_pnl < 0:
            loss_pct = abs(self._daily_pnl) / account.equity
            if loss_pct > self._max_daily_loss_pct:
                return RiskDecision(
                    RiskCheckResult.REJECTED,
                    f"Daily loss {float(loss_pct) * 100:.2f}% exceeds limit "
                    f"{float(self._max_daily_loss_pct) * 100:.1f}%",
                )

        return RiskDecision(RiskCheckResult.PASSED)

    def _check_order_frequency(self) -> RiskDecision:
        """检查下单频率是否超出上限。"""
        now = datetime.now()
        cutoff = now - timedelta(hours=1)
        recent = [t for t in self._daily_orders if t > cutoff]

        if len(recent) >= self._max_order_frequency:
            return RiskDecision(
                RiskCheckResult.REJECTED,
                f"Order frequency {len(recent)}/hr exceeds limit {self._max_order_frequency}/hr",
            )

        return RiskDecision(RiskCheckResult.PASSED)

    def _maybe_reset_daily(self, now: datetime) -> None:
        """在每个交易日开始时重置日内计数器。"""
        if self._last_reset_date is None or now.date() != self._last_reset_date.date():
            self._daily_orders.clear()
            self._daily_pnl = Decimal(0)
            self._last_reset_date = now
