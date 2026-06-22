"""模拟网关 - 使用本地撮合引擎进行回测。"""

from __future__ import annotations

import logging
from decimal import Decimal

from quant_trading.backtest.matching import MatchingEngine
from quant_trading.gateway.base import BaseGateway
from quant_trading.model.account import Account
from quant_trading.model.instrument import Currency, InstrumentId
from quant_trading.model.order import Order
from quant_trading.model.position import Position

logger = logging.getLogger(__name__)


class SimulatedGateway(BaseGateway):
    """基于本地撮合引擎的模拟网关，用于回测和模拟交易。"""

    def __init__(
        self,
        initial_capital: float = 1_000_000.0,
        commission_rate: float = 0.0003,
        slippage_rate: float = 0.0001,
    ) -> None:
        super().__init__(name="simulated")
        self._matching = MatchingEngine(
            commission_rate=Decimal(str(commission_rate)),
            slippage_rate=Decimal(str(slippage_rate)),
        )
        self._account = Account(
            account_id="simulated",
            currency=Currency.CNY,
            balance=Decimal(str(initial_capital)),
            available=Decimal(str(initial_capital)),
        )
        self._positions: dict[str, Position] = {}

    @property
    def matching_engine(self) -> MatchingEngine:
        return self._matching

    async def connect(self) -> None:
        self._connected = True
        logger.info("Simulated gateway connected")

    async def disconnect(self) -> None:
        self._connected = False

    async def subscribe_market_data(self, instruments: list[InstrumentId]) -> None:
        pass  # 模拟网关直接接收数据，无需订阅

    async def submit_order(self, order: Order) -> str:
        self._matching.submit_order(order)
        return order.order_id

    async def cancel_order(self, order_id: str) -> bool:
        return self._matching.cancel_order(order_id)

    async def query_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if not p.is_flat]

    async def query_account(self) -> Account:
        return self._account
