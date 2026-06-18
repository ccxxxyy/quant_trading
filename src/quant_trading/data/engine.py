"""数据引擎 - 协调行情数据的获取、存储和分发。"""

from __future__ import annotations

import logging
from datetime import datetime

from quant_trading.core.event import Event, EventBus, EventType
from quant_trading.data.feed import DataFeed
from quant_trading.data.store import DataStore
from quant_trading.model.instrument import InstrumentId
from quant_trading.model.market import Bar, BarInterval, Tick

logger = logging.getLogger(__name__)


class DataEngine:
    """行情数据管理中心。

    职责：
    - 从数据源获取历史数据并缓存到本地
    - 通过事件总线向订阅者分发行情事件
    - 管理数据源和存储的生命周期
    """

    def __init__(self, event_bus: EventBus, store: DataStore | None = None) -> None:
        self._event_bus = event_bus
        self._store = store or DataStore()
        self._feeds: dict[str, DataFeed] = {}
        self._bar_cache: dict[str, list[Bar]] = {}

    def add_feed(self, feed: DataFeed) -> None:
        """注册一个数据源。"""
        self._feeds[feed.name] = feed
        logger.info(f"Added data feed: {feed.name}")

    def get_feed(self, name: str) -> DataFeed | None:
        return self._feeds.get(name)

    @property
    def store(self) -> DataStore:
        return self._store

    async def fetch_bars(
        self,
        instrument_id: InstrumentId,
        interval: BarInterval,
        start: datetime,
        end: datetime | None = None,
        feed_name: str | None = None,
        save: bool = True,
    ) -> list[Bar]:
        """从数据源获取K线数据，可选择是否保存到本地。"""
        feed = self._resolve_feed(feed_name)
        bars = await feed.get_bars(instrument_id, interval, start, end)

        if save and bars:
            self._store.save_bars(instrument_id, bars)

        return bars

    def load_bars(
        self,
        instrument_id: InstrumentId,
        interval: BarInterval,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bar]:
        """从本地存储加载K线数据。"""
        return self._store.load_bars(instrument_id, interval, start, end)

    def emit_bar(self, bar: Bar) -> None:
        """向事件总线发送K线事件。"""
        event = Event(type=EventType.BAR, data=bar, timestamp=bar.timestamp)
        self._event_bus.publish(event)

    def emit_tick(self, tick: Tick) -> None:
        """向事件总线发送逐笔行情事件。"""
        event = Event(type=EventType.TICK, data=tick, timestamp=tick.timestamp)
        self._event_bus.publish(event)

    def _resolve_feed(self, name: str | None) -> DataFeed:
        """按名称获取数据源，或返回第一个可用的数据源。"""
        if name:
            feed = self._feeds.get(name)
            if not feed:
                raise ValueError(f"Data feed not found: {name}")
            return feed
        if not self._feeds:
            raise RuntimeError("No data feeds registered")
        return next(iter(self._feeds.values()))

    def close(self) -> None:
        self._store.close()
