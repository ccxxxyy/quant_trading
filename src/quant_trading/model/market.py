"""行情数据模型 - Tick 逐笔行情、Bar K线数据、OrderBook 盘口委托簿。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from quant_trading.model.instrument import InstrumentId


class BarInterval(Enum):
    """支持的K线时间周期。"""

    TICK = "tick"  # 逐笔
    SECOND_1 = "1s"  # 1秒
    MINUTE_1 = "1m"  # 1分钟
    MINUTE_5 = "5m"  # 5分钟
    MINUTE_15 = "15m"  # 15分钟
    MINUTE_30 = "30m"  # 30分钟
    HOUR_1 = "1h"  # 1小时
    HOUR_4 = "4h"  # 4小时
    DAILY = "1d"  # 日线
    WEEKLY = "1w"  # 周线


@dataclass(frozen=True, slots=True)
class Tick:
    """单条逐笔行情快照，包含最优买卖价。"""

    instrument_id: InstrumentId
    timestamp: datetime
    last_price: Decimal  # 最新成交价
    last_volume: int  # 最新成交量
    bid_price: Decimal  # 买一价（最优买入价）
    ask_price: Decimal  # 卖一价（最优卖出价）
    bid_volume: int  # 买一量
    ask_volume: int  # 卖一量
    open_interest: int = 0  # 持仓量（期货专用）
    turnover: Decimal = Decimal(0)  # 成交额

    @property
    def mid_price(self) -> Decimal:
        """中间价 = (买一价 + 卖一价) / 2"""
        return (self.bid_price + self.ask_price) / 2

    @property
    def spread(self) -> Decimal:
        """买卖价差 = 卖一价 - 买一价"""
        return self.ask_price - self.bid_price


@dataclass(frozen=True, slots=True)
class Bar:
    """指定时间周期的 OHLCV K线数据。"""

    instrument_id: InstrumentId
    timestamp: datetime
    interval: BarInterval
    open: Decimal  # 开盘价
    high: Decimal  # 最高价
    low: Decimal  # 最低价
    close: Decimal  # 收盘价
    volume: int  # 成交量
    turnover: Decimal = Decimal(0)  # 成交额
    open_interest: int = 0  # 持仓量（期货专用）

    @property
    def mid(self) -> Decimal:
        """K线中价 = (最高价 + 最低价) / 2"""
        return (self.high + self.low) / 2

    @property
    def body(self) -> Decimal:
        """K线实体长度 = |收盘价 - 开盘价|"""
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        """是否为阳线（收盘价 >= 开盘价，即上涨）。"""
        return self.close >= self.open


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    """盘口委托簿中的单个价格档位。"""

    price: Decimal
    volume: int


@dataclass(frozen=True, slots=True)
class OrderBook:
    """某一时刻的盘口委托簿快照。"""

    instrument_id: InstrumentId
    timestamp: datetime
    bids: tuple[OrderBookLevel, ...]  # 买方挂单（从高到低排列）
    asks: tuple[OrderBookLevel, ...]  # 卖方挂单（从低到高排列）

    @property
    def best_bid(self) -> Decimal | None:
        """最优买入价（买一价）。"""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Decimal | None:
        """最优卖出价（卖一价）。"""
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> Decimal | None:
        """买卖价差。"""
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None
