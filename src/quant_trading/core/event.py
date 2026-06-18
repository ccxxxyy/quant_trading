"""事件总线 - 交易平台的中枢神经系统。

采用发布-订阅模式实现组件间松耦合通信。
支持同步分发（回测模式）和异步分发（实盘模式）。
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class EventType(Enum):
    """系统中流转的核心事件类型。"""

    TICK = "tick"
    BAR = "bar"
    ORDER = "order"
    TRADE = "trade"
    FILL = "fill"
    POSITION = "position"
    ACCOUNT = "account"
    SIGNAL = "signal"
    RISK_ALERT = "risk_alert"
    TIMER = "timer"
    LOG = "log"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class Event:
    """在事件总线中流转的不可变事件对象。"""

    type: EventType
    data: Any
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""


HandlerType = Callable[[Event], None]
AsyncHandlerType = Callable[[Event], Any]


class EventBus:
    """同步事件总线 - 用于回测模式，按确定性顺序处理事件。"""

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[HandlerType]] = defaultdict(list)
        self._general_handlers: list[HandlerType] = []
        self._event_count: int = 0

    def subscribe(self, event_type: EventType, handler: HandlerType) -> None:
        """订阅指定类型的事件。"""
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: HandlerType) -> None:
        """订阅所有类型的事件。"""
        if handler not in self._general_handlers:
            self._general_handlers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: HandlerType) -> None:
        """取消事件订阅。"""
        handlers = self._handlers[event_type]
        if handler in handlers:
            handlers.remove(handler)

    def publish(self, event: Event) -> None:
        """发布事件给所有已订阅的处理器（同步执行）。"""
        self._event_count += 1
        for handler in self._handlers[event.type]:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Handler error: {handler.__name__} - {e}", exc_info=True)
        for handler in self._general_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"General handler error: {handler.__name__} - {e}", exc_info=True)

    def reset(self) -> None:
        """清除所有处理器并重置状态。"""
        self._handlers.clear()
        self._general_handlers.clear()
        self._event_count = 0

    @property
    def event_count(self) -> int:
        return self._event_count


class AsyncEventBus:
    """异步事件总线 - 用于实盘交易模式。"""

    def __init__(self, max_queue_size: int = 10000) -> None:
        self._handlers: dict[EventType, list[AsyncHandlerType]] = defaultdict(list)
        self._general_handlers: list[AsyncHandlerType] = []
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=max_queue_size)
        self._running: bool = False
        self._event_count: int = 0

    def subscribe(self, event_type: EventType, handler: AsyncHandlerType) -> None:
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: AsyncHandlerType) -> None:
        if handler not in self._general_handlers:
            self._general_handlers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: AsyncHandlerType) -> None:
        handlers = self._handlers[event_type]
        if handler in handlers:
            handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        """将事件放入异步队列等待处理。"""
        await self._queue.put(event)

    def publish_nowait(self, event: Event) -> None:
        """非阻塞发布，队列满时丢弃事件。"""
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(f"Event queue full, dropping event: {event.type}")

    async def start(self) -> None:
        """启动事件处理循环。"""
        self._running = True
        logger.info("AsyncEventBus started")
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except TimeoutError:
                continue
            self._event_count += 1
            await self._dispatch(event)

    async def stop(self) -> None:
        """停止事件处理循环并处理完队列中剩余的事件。"""
        self._running = False
        while not self._queue.empty():
            event = self._queue.get_nowait()
            await self._dispatch(event)
        logger.info("AsyncEventBus stopped")

    async def _dispatch(self, event: Event) -> None:
        """将事件分发给所有已订阅的处理器。"""
        for handler in self._handlers[event.type]:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Async handler error: {handler.__name__} - {e}", exc_info=True)
        for handler in self._general_handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Async general handler error: {e}", exc_info=True)

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()
