"""回测引擎 - 事件驱动的历史回测，支持模拟撮合执行。"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from quant_trading.backtest.analyzer import BacktestAnalyzer, PerformanceMetrics, TradeRecord
from quant_trading.backtest.matching import MatchingEngine
from quant_trading.core.clock import SimulatedClock
from quant_trading.core.config import BacktestConfig, Settings
from quant_trading.core.event import Event, EventBus, EventType
from quant_trading.model.account import Account
from quant_trading.model.instrument import Currency, InstrumentId
from quant_trading.model.market import Bar
from quant_trading.model.order import Fill, Order, OrderSide
from quant_trading.model.position import Position

logger = logging.getLogger(__name__)


class BacktestEngine:
    """事件驱动回测引擎。

    按时间顺序回放历史K线数据，通过事件总线分发行情事件，
    使用模拟撮合引擎执行订单，支持可配置的手续费和滑点模型。
    """

    def __init__(
        self,
        initial_capital: float = 1_000_000.0,
        commission_rate: float = 0.0003,
        slippage_rate: float = 0.0001,
        settings: Settings | None = None,
    ) -> None:
        config = settings.backtest if settings else BacktestConfig()
        self._initial_capital = initial_capital or config.initial_capital
        self._commission_rate = Decimal(str(commission_rate or config.default_commission))
        self._slippage_rate = Decimal(str(slippage_rate or config.default_slippage))

        # 核心组件
        self._event_bus = EventBus()
        self._clock = SimulatedClock()
        self._matching = MatchingEngine(self._commission_rate, self._slippage_rate)
        self._analyzer = BacktestAnalyzer()

        # 状态数据
        self._account = Account(
            account_id="backtest",
            currency=Currency.CNY,
            balance=Decimal(str(self._initial_capital)),
            available=Decimal(str(self._initial_capital)),
        )
        self._positions: dict[str, Position] = {}
        self._fills: list[Fill] = []
        self._orders: list[Order] = []
        self._equity_curve: list[tuple[datetime, float]] = []
        self._trade_records: list[TradeRecord] = []
        self._strategies: list = []
        self._bar_data: dict[str, list[Bar]] = {}
        self._current_prices: dict[str, Decimal] = {}

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def clock(self) -> SimulatedClock:
        return self._clock

    @property
    def account(self) -> Account:
        return self._account

    @property
    def positions(self) -> dict[str, Position]:
        return self._positions

    @property
    def clock_now(self) -> datetime:
        return self._clock.now()

    @property
    def equity_curve(self) -> list[tuple[datetime, float]]:
        return list(self._equity_curve)

    @property
    def trade_records(self) -> list[TradeRecord]:
        return list(self._trade_records)

    def add_bar_data(self, instrument_id: InstrumentId, bars: list[Bar]) -> None:
        """添加用于回测的历史K线数据。"""
        key = str(instrument_id)
        self._bar_data[key] = sorted(bars, key=lambda b: b.timestamp)
        logger.info(f"Added {len(bars)} bars for {instrument_id}")

    def add_strategy(self, strategy) -> None:
        """注册一个策略参与回测。"""
        self._strategies.append(strategy)

    def submit_order(self, order: Order) -> str:
        """将订单提交到模拟撮合引擎。"""
        self._orders.append(order)
        self._matching.submit_order(order)
        event = Event(type=EventType.ORDER, data=order, timestamp=self._clock.now())
        self._event_bus.publish(event)
        return order.order_id

    def cancel_order(self, order_id: str) -> bool:
        return self._matching.cancel_order(order_id)

    def get_position(self, instrument_id: InstrumentId) -> Position:
        """获取或创建某标的的持仓对象。"""
        key = str(instrument_id)
        if key not in self._positions:
            self._positions[key] = Position(instrument_id=instrument_id)
        return self._positions[key]

    def run(self) -> PerformanceMetrics:
        """执行回测主流程。"""
        logger.info("Starting backtest...")

        # 合并所有标的的K线并按时间排序
        all_bars: list[tuple[str, Bar]] = []
        for key, bars in self._bar_data.items():
            for bar in bars:
                all_bars.append((key, bar))
        all_bars.sort(key=lambda x: x[1].timestamp)

        if not all_bars:
            logger.warning("No bar data to backtest")
            return PerformanceMetrics(initial_capital=self._initial_capital)

        # 初始化策略
        for strategy in self._strategies:
            strategy.on_init()

        # 记录初始权益
        self._equity_curve.append((all_bars[0][1].timestamp, self._initial_capital))

        # 主回测循环
        for key, bar in all_bars:
            self._clock.advance(bar.timestamp)
            self._current_prices[key] = bar.close

            # 用当前K线尝试撮合挂起的订单
            fills = self._matching.match_bar(bar)
            for fill in fills:
                self._process_fill(fill)

            # 向事件总线发送K线事件
            self._event_bus.publish(Event(type=EventType.BAR, data=bar, timestamp=bar.timestamp))

            # 通知所有策略处理新K线
            for strategy in self._strategies:
                strategy.on_bar(bar)

            # 记录当前权益
            equity = self._calculate_equity()
            self._equity_curve.append((bar.timestamp, equity))

        # 计算绩效指标
        metrics = self._analyzer.compute_metrics(
            equity_curve=self._equity_curve,
            trades=self._trade_records,
            initial_capital=self._initial_capital,
        )

        logger.info(
            f"Backtest complete: {metrics.total_trades} trades, "
            f"return={metrics.total_return * 100:.2f}%"
        )
        return metrics

    def get_report(self) -> str:
        """生成格式化的绩效报告文本。"""
        metrics = self._analyzer.compute_metrics(
            equity_curve=self._equity_curve,
            trades=self._trade_records,
            initial_capital=self._initial_capital,
        )
        return self._analyzer.format_report(metrics)

    def _process_fill(self, fill: Fill) -> None:
        """处理成交回报 - 更新持仓、账户资金、记录交易。"""
        self._fills.append(fill)

        # 更新持仓
        position = self.get_position(fill.instrument_id)
        prev_quantity = position.quantity
        position.apply_fill(fill)

        # 更新账户资金
        if fill.side == OrderSide.BUY:
            cost = fill.price * fill.quantity + fill.commission
            self._account.available -= cost
        else:
            proceeds = fill.price * fill.quantity - fill.commission
            self._account.available += proceeds

        self._account.commission += fill.commission

        # 如果持仓完全平仓，记录一笔完整交易
        if prev_quantity != 0 and position.quantity == 0:
            self._record_trade_close(fill, prev_quantity)

        # 发送成交事件
        self._event_bus.publish(Event(type=EventType.FILL, data=fill, timestamp=fill.timestamp))

    def _record_trade_close(self, closing_fill: Fill, prev_quantity: int) -> None:
        """记录一笔完整的开仓→平仓交易。"""
        position = self.get_position(closing_fill.instrument_id)
        pnl = float(position.realized_pnl)
        self._trade_records.append(
            TradeRecord(
                instrument_id=str(closing_fill.instrument_id),
                side="long" if prev_quantity > 0 else "short",
                entry_time=position.opened_at or closing_fill.timestamp,
                exit_time=closing_fill.timestamp,
                entry_price=float(position.avg_cost) if position.avg_cost else 0,
                exit_price=float(closing_fill.price),
                quantity=abs(prev_quantity),
                pnl=pnl,
                commission=float(position.commission),
                return_pct=pnl / float(self._initial_capital) if self._initial_capital else 0,
            )
        )

    def _calculate_equity(self) -> float:
        """计算当前总权益（可用资金 + 持仓市值）。"""
        equity = float(self._account.available)
        for key, position in self._positions.items():
            if not position.is_flat and key in self._current_prices:
                price = self._current_prices[key]
                equity += float(price * position.quantity)
        return equity
