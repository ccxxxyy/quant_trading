"""时钟抽象 - 回测和实盘统一的时间管理。

SimulatedClock（模拟时钟）：回测时按确定性方式推进时间。
LiveClock（真实时钟）：实盘时使用系统真实时间。
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone

TimerCallback = Callable[[datetime], None]


class Clock(ABC):
    """抽象时钟，在不同运行环境中提供统一的时间接口。"""

    @abstractmethod
    def now(self) -> datetime:
        """获取当前时间戳。"""
        ...

    @abstractmethod
    def timestamp_ns(self) -> int:
        """获取当前时间的纳秒级 Unix 时间戳。"""
        ...

    @abstractmethod
    def set_timer(self, name: str, interval: timedelta, callback: TimerCallback) -> None:
        """注册一个周期性定时器。"""
        ...

    @abstractmethod
    def cancel_timer(self, name: str) -> None:
        """取消已注册的定时器。"""
        ...


class SimulatedClock(Clock):
    """确定性模拟时钟 - 用于回测，时间仅在显式设置时推进。"""

    def __init__(self, start_time: datetime | None = None) -> None:
        self._current_time: datetime = start_time or datetime(2020, 1, 1)
        self._timers: dict[str, tuple[timedelta, TimerCallback, datetime]] = {}

    def now(self) -> datetime:
        return self._current_time

    def timestamp_ns(self) -> int:
        return int(self._current_time.timestamp() * 1_000_000_000)

    def advance(self, to_time: datetime) -> None:
        """将时钟推进到指定时间，触发期间到期的所有定时器。"""
        if to_time < self._current_time:
            raise ValueError(f"Cannot go back in time: {to_time} < {self._current_time}")

        fired: list[str] = []
        for name, (interval, callback, next_fire) in list(self._timers.items()):
            while next_fire <= to_time:
                self._current_time = next_fire
                callback(self._current_time)
                next_fire += interval
                self._timers[name] = (interval, callback, next_fire)
            if name not in fired:
                fired.append(name)

        self._current_time = to_time

    def set_timer(self, name: str, interval: timedelta, callback: TimerCallback) -> None:
        next_fire = self._current_time + interval
        self._timers[name] = (interval, callback, next_fire)

    def cancel_timer(self, name: str) -> None:
        self._timers.pop(name, None)

    def reset(self, start_time: datetime | None = None) -> None:
        self._current_time = start_time or datetime(2020, 1, 1)
        self._timers.clear()


class LiveClock(Clock):
    """真实时钟 - 用于实盘交易。"""

    def __init__(self, tz: timezone = UTC) -> None:
        self._tz = tz
        self._timers: dict[str, asyncio.Task] = {}

    def now(self) -> datetime:
        return datetime.now(self._tz)

    def timestamp_ns(self) -> int:
        return time.time_ns()

    def set_timer(self, name: str, interval: timedelta, callback: TimerCallback) -> None:
        if name in self._timers:
            self._timers[name].cancel()

        async def _timer_loop():
            while True:
                await asyncio.sleep(interval.total_seconds())
                callback(self.now())

        loop = asyncio.get_event_loop()
        self._timers[name] = loop.create_task(_timer_loop())

    def cancel_timer(self, name: str) -> None:
        task = self._timers.pop(name, None)
        if task:
            task.cancel()
