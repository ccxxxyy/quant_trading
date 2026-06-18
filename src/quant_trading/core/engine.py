"""主引擎 - 交易系统的中央调度器。

管理所有网关、引擎和应用模块。
为回测和实盘环境提供统一的接口。
"""

from __future__ import annotations

import logging
from pathlib import Path

import structlog

from quant_trading.core.clock import Clock, LiveClock, SimulatedClock
from quant_trading.core.config import Settings
from quant_trading.core.event import AsyncEventBus, EventBus
from quant_trading.core.registry import ComponentRegistry

logger = logging.getLogger(__name__)


def setup_logging(level: str = "INFO") -> None:
    """配置结构化日志。"""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(),
    )


class MainEngine:
    """交易系统的中央调度器。

    职责：
    - 初始化并管理所有子引擎
    - 提供事件总线用于组件间通信
    - 管理系统时钟
    - 加载配置
    """

    def __init__(
        self,
        settings: Settings | None = None,
        config_dir: str | Path = "config",
        mode: str = "backtest",
    ) -> None:
        self._settings = settings or Settings.load(config_dir)
        self._mode = mode
        self._registry = ComponentRegistry()

        # 配置日志
        setup_logging(self._settings.system.log_level)

        # 根据运行模式初始化时钟
        if mode == "backtest":
            self._clock: Clock = SimulatedClock()
            self._event_bus: EventBus | AsyncEventBus = EventBus()
        else:
            self._clock = LiveClock()
            self._event_bus = AsyncEventBus()

        # 注册核心组件
        self._registry.register("clock", self._clock)
        self._registry.register("event_bus", self._event_bus)

        self._started = False
        logger.info(f"MainEngine initialized in {mode} mode")

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def clock(self) -> Clock:
        return self._clock

    @property
    def event_bus(self) -> EventBus | AsyncEventBus:
        return self._event_bus

    @property
    def registry(self) -> ComponentRegistry:
        return self._registry

    @property
    def mode(self) -> str:
        return self._mode

    def add_component(self, name: str, component: object) -> None:
        """向引擎注册一个组件。"""
        self._registry.register(name, component)

    def get_component(self, name: str) -> object:
        """获取已注册的组件。"""
        return self._registry.get(name)

    def start(self) -> None:
        """启动引擎和所有已注册的组件。"""
        if self._started:
            return
        self._registry.start_all()
        self._started = True
        logger.info("MainEngine started")

    def stop(self) -> None:
        """停止引擎和所有已注册的组件。"""
        if not self._started:
            return
        self._registry.stop_all()
        self._started = False
        logger.info("MainEngine stopped")

    async def start_async(self) -> None:
        """以异步模式启动引擎（用于实盘交易）。"""
        if self._started:
            return
        self._registry.start_all()
        if isinstance(self._event_bus, AsyncEventBus):
            import asyncio

            asyncio.create_task(self._event_bus.start())
        self._started = True
        logger.info("MainEngine started (async)")

    async def stop_async(self) -> None:
        """以异步模式停止引擎。"""
        if not self._started:
            return
        if isinstance(self._event_bus, AsyncEventBus):
            await self._event_bus.stop()
        self._registry.stop_all()
        self._started = False
        logger.info("MainEngine stopped (async)")
