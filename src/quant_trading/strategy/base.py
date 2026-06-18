"""策略基类 - 定义所有策略必须实现的接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from decimal import Decimal

from quant_trading.model.instrument import InstrumentId
from quant_trading.model.market import Bar, Tick
from quant_trading.model.order import Fill
from quant_trading.strategy.context import StrategyContext


class BaseStrategy(ABC):
    """所有交易策略的抽象基类。

    策略通过 StrategyContext 与交易引擎交互，
    该上下文在回测和实盘环境中提供相同的接口。
    """

    def __init__(self, strategy_id: str = "", params: dict | None = None) -> None:
        self._strategy_id = strategy_id or self.__class__.__name__
        self._params = params or {}
        self._ctx: StrategyContext | None = None
        self._initialized = False

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def ctx(self) -> StrategyContext:
        if self._ctx is None:
            raise RuntimeError("Strategy not attached to a context")
        return self._ctx

    @property
    def params(self) -> dict:
        return self._params

    def attach(self, ctx: StrategyContext) -> None:
        """将策略绑定到一个交易上下文。"""
        self._ctx = ctx

    @abstractmethod
    def on_init(self) -> None:
        """策略初始化回调，在交易开始前调用一次。可在此设置指标、订阅数据等。"""
        ...

    @abstractmethod
    def on_bar(self, bar: Bar) -> None:
        """收到新K线时的回调，核心策略逻辑写在这里。"""
        ...

    def on_tick(self, tick: Tick) -> None:
        """收到新逐笔行情时的回调（可选，不是所有策略都需要逐笔数据）。"""
        pass

    def on_fill(self, fill: Fill) -> None:
        """订单成交时的回调。"""
        pass

    def on_stop(self) -> None:
        """策略停止时的回调，用于清理资源。"""
        pass


class BarSeriesStrategy(BaseStrategy):
    """自带K线序列管理的策略基类。

    自动维护每个标的最近N根K线的滑动窗口，
    方便策略直接获取历史K线来计算指标。
    """

    def __init__(
        self,
        strategy_id: str = "",
        params: dict | None = None,
        max_bars: int = 500,
    ) -> None:
        super().__init__(strategy_id, params)
        self._max_bars = max_bars
        self._bars: dict[str, deque[Bar]] = {}

    def get_bars(self, instrument_id: InstrumentId) -> list[Bar]:
        """获取某标的的K线历史。"""
        key = str(instrument_id)
        return list(self._bars.get(key, []))

    def get_closes(self, instrument_id: InstrumentId) -> list[Decimal]:
        """获取某标的的收盘价序列。"""
        return [bar.close for bar in self.get_bars(instrument_id)]

    def on_bar(self, bar: Bar) -> None:
        key = str(bar.instrument_id)
        if key not in self._bars:
            self._bars[key] = deque(maxlen=self._max_bars)
        self._bars[key].append(bar)
        self.on_bar_update(bar)

    @abstractmethod
    def on_bar_update(self, bar: Bar) -> None:
        """在K线序列更新后执行策略逻辑（子类实现）。"""
        ...
