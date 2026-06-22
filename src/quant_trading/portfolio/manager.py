"""组合管理器 - 跟踪持仓状态，计算组合层面的指标。"""

from __future__ import annotations

import logging
from decimal import Decimal

from quant_trading.model.account import Account
from quant_trading.model.instrument import InstrumentId
from quant_trading.model.position import Position

logger = logging.getLogger(__name__)


class PortfolioManager:
    """管理所有交易标的的整体持仓状态。

    提供：
    - 持仓跟踪与汇总
    - 组合层面的盈亏计算
    - 敞口和集中度分析
    """

    def __init__(self, account: Account) -> None:
        self._account = account
        self._positions: dict[str, Position] = {}
        self._current_prices: dict[str, Decimal] = {}

    @property
    def account(self) -> Account:
        return self._account

    @property
    def positions(self) -> dict[str, Position]:
        return self._positions

    def update_price(self, instrument_id: InstrumentId, price: Decimal) -> None:
        """更新某标的的最新市场价格。"""
        self._current_prices[str(instrument_id)] = price

    def get_position(self, instrument_id: InstrumentId) -> Position:
        key = str(instrument_id)
        if key not in self._positions:
            self._positions[key] = Position(instrument_id=instrument_id)
        return self._positions[key]

    @property
    def total_equity(self) -> Decimal:
        """总权益 = 现金 + 持仓按市价计算的市值。"""
        equity = self._account.available + self._account.frozen
        for key, pos in self._positions.items():
            if not pos.is_flat:
                price = self._current_prices.get(key, pos.avg_cost)
                equity += price * pos.quantity
        return equity

    @property
    def total_unrealized_pnl(self) -> Decimal:
        """所有持仓的未实现盈亏（浮盈浮亏）之和。"""
        total = Decimal(0)
        for key, pos in self._positions.items():
            if not pos.is_flat:
                price = self._current_prices.get(key, pos.avg_cost)
                total += pos.unrealized_pnl(price)
        return total

    @property
    def total_realized_pnl(self) -> Decimal:
        return sum((p.realized_pnl for p in self._positions.values()), Decimal(0))

    @property
    def gross_exposure(self) -> Decimal:
        """总敞口（所有持仓市值的绝对值之和）。"""
        total = Decimal(0)
        for key, pos in self._positions.items():
            if not pos.is_flat:
                price = self._current_prices.get(key, pos.avg_cost)
                total += abs(price * pos.quantity)
        return total

    @property
    def net_exposure(self) -> Decimal:
        """净敞口（多头市值 - 空头市值）。"""
        total = Decimal(0)
        for key, pos in self._positions.items():
            if not pos.is_flat:
                price = self._current_prices.get(key, pos.avg_cost)
                total += price * pos.quantity
        return total

    @property
    def num_positions(self) -> int:
        return sum(1 for p in self._positions.values() if not p.is_flat)

    def get_concentration(self) -> dict[str, float]:
        """获取持仓集中度（各标的占总权益的百分比）。"""
        equity = self.total_equity
        if equity == 0:
            return {}
        concentration = {}
        for key, pos in self._positions.items():
            if not pos.is_flat:
                price = self._current_prices.get(key, pos.avg_cost)
                value = abs(price * pos.quantity)
                concentration[key] = float(value / equity)
        return concentration

    def summary(self) -> dict:
        """获取投资组合状态摘要。"""
        return {
            "equity": float(self.total_equity),
            "cash": float(self._account.available),
            "unrealized_pnl": float(self.total_unrealized_pnl),
            "realized_pnl": float(self.total_realized_pnl),
            "gross_exposure": float(self.gross_exposure),
            "net_exposure": float(self.net_exposure),
            "num_positions": self.num_positions,
        }
