"""网关基类 - 所有交易网关的抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from quant_trading.model.account import Account
from quant_trading.model.instrument import InstrumentId
from quant_trading.model.market import Bar, Tick
from quant_trading.model.order import Fill, Order
from quant_trading.model.position import Position


class BaseGateway(ABC):
    """所有交易网关的抽象基类。

    网关负责将本系统连接到具体的券商或交易所，
    处理订单提交、行情接收和账户查询。
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._connected = False
        self._on_tick: Callable[[Tick], None] | None = None
        self._on_bar: Callable[[Bar], None] | None = None
        self._on_fill: Callable[[Fill], None] | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_connected(self) -> bool:
        return self._connected

    def set_callbacks(
        self,
        on_tick: Callable[[Tick], None] | None = None,
        on_bar: Callable[[Bar], None] | None = None,
        on_fill: Callable[[Fill], None] | None = None,
    ) -> None:
        """设置数据和成交事件的回调函数。"""
        self._on_tick = on_tick
        self._on_bar = on_bar
        self._on_fill = on_fill

    @abstractmethod
    async def connect(self) -> None:
        """建立与券商/交易所的连接。"""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """断开与券商/交易所的连接。"""
        ...

    @abstractmethod
    async def subscribe_market_data(self, instruments: list[InstrumentId]) -> None:
        """订阅指定标的的实时行情。"""
        ...

    @abstractmethod
    async def submit_order(self, order: Order) -> str:
        """提交订单，返回券商订单ID。"""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """撤销一个已提交的订单。"""
        ...

    @abstractmethod
    async def query_positions(self) -> list[Position]:
        """查询当前持仓。"""
        ...

    @abstractmethod
    async def query_account(self) -> Account:
        """查询账户资金和保证金信息。"""
        ...
