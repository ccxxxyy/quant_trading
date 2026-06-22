"""数据源抽象基类 - 所有行情数据源的统一接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from quant_trading.model.instrument import InstrumentId
from quant_trading.model.market import Bar, BarInterval, Tick


class DataFeed(ABC):
    """行情数据提供者的抽象基类。

    每个数据源（AkShare、yfinance、IB、CTP 等）都需要实现此接口，
    以提供统一的数据访问层。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """数据源名称标识符。"""
        ...

    @abstractmethod
    async def get_bars(
        self,
        instrument_id: InstrumentId,
        interval: BarInterval,
        start: datetime,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[Bar]:
        """获取历史K线数据。"""
        ...

    async def get_ticks(
        self,
        instrument_id: InstrumentId,
        start: datetime,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[Tick]:
        """获取历史逐笔数据（并非所有数据源都支持）。"""
        raise NotImplementedError(f"{self.name} does not support tick data")

    async def subscribe_bars(
        self,
        instrument_id: InstrumentId,
        interval: BarInterval,
    ) -> None:
        """订阅实时K线推送（仅实盘模式）。"""
        raise NotImplementedError(f"{self.name} does not support real-time bars")

    async def subscribe_ticks(
        self,
        instrument_id: InstrumentId,
    ) -> None:
        """订阅实时逐笔行情推送（仅实盘模式）。"""
        raise NotImplementedError(f"{self.name} does not support real-time ticks")

    async def unsubscribe(self, instrument_id: InstrumentId) -> None:
        """取消实时行情订阅。"""
        pass
