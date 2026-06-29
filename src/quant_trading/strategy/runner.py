"""实时策略运行器 - 连接行情源、策略和执行引擎，驱动策略在实时/模拟环境中运行。

回测只在历史数据上跑一次；本模块提供一个持续运行的循环，
接收实时（或模拟）行情，调用策略的 on_bar/on_tick，再将订单路由到执行引擎。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from quant_trading.core.event import AsyncEventBus
from quant_trading.model.account import Account
from quant_trading.model.instrument import Currency, InstrumentId
from quant_trading.model.market import Bar
from quant_trading.model.order import Fill, Order, OrderSide
from quant_trading.model.position import Position
from quant_trading.risk.engine import RiskCheckResult, RiskEngine
from quant_trading.strategy.base import BaseStrategy
from quant_trading.strategy.context import StrategyContext

logger = logging.getLogger(__name__)


class LiveStrategyRunner:
    """实时策略运行器。

    职责：
        1. 管理策略生命周期（init → run → stop）
        2. 接收行情事件并分发给策略
        3. 拦截策略产生的订单，经风控检查后转发到网关
        4. 维护账户和持仓状态

    使用方式：
        runner = LiveStrategyRunner(gateway=paper_gw)
        runner.add_strategy(my_strategy, ["600519.SSE"])
        await runner.start()
        # 外部推送行情：
        runner.on_bar(bar)
        # 停止：
        await runner.stop()
    """

    def __init__(
        self,
        gateway: Any = None,
        risk_engine: RiskEngine | None = None,
        initial_capital: float = 1_000_000.0,
    ) -> None:
        self._gateway = gateway
        self._risk_engine = risk_engine or RiskEngine()
        self._event_bus = AsyncEventBus()
        self._account = Account(
            account_id="live",
            currency=Currency.CNY,
            balance=Decimal(str(initial_capital)),
            available=Decimal(str(initial_capital)),
        )
        self._positions: dict[str, Position] = {}
        self._current_prices: dict[str, Decimal] = {}
        self._strategies: list[tuple[BaseStrategy, list[str]]] = []
        self._running = False
        self._bar_count = 0

    @property
    def running(self) -> bool:
        return self._running

    @property
    def account(self) -> Account:
        return self._account

    @property
    def positions(self) -> dict[str, Position]:
        return dict(self._positions)

    @property
    def bar_count(self) -> int:
        return self._bar_count

    @property
    def clock_now(self) -> datetime:
        return datetime.now()

    def get_position(self, instrument_id: InstrumentId) -> Position:
        key = str(instrument_id)
        if key not in self._positions:
            self._positions[key] = Position(instrument_id=instrument_id)
        return self._positions[key]

    def add_strategy(
        self,
        strategy: BaseStrategy,
        instruments: list[str],
    ) -> None:
        """注册策略及其关注的标的。"""
        ctx = StrategyContext(engine=self, strategy_id=strategy.strategy_id)
        strategy.attach(ctx)
        self._strategies.append((strategy, instruments))
        logger.info(f"Registered strategy {strategy.strategy_id} for {instruments}")

    async def start(self) -> None:
        """启动运行器，初始化所有策略。"""
        if self._running:
            return

        if self._gateway and not self._gateway.is_connected:
            await self._gateway.connect()
            account = await self._gateway.query_account()
            self._account = account

        for strategy, _ in self._strategies:
            strategy.on_init()

        self._running = True
        logger.info(f"LiveStrategyRunner started with {len(self._strategies)} strategies")

    async def stop(self) -> None:
        """停止运行器，通知所有策略清理。"""
        if not self._running:
            return

        for strategy, _ in self._strategies:
            strategy.on_stop()

        self._running = False
        logger.info(f"LiveStrategyRunner stopped after {self._bar_count} bars")

    def on_bar(self, bar: Bar) -> None:
        """接收一根新K线并分发给相关策略。

        这是外部行情源调用的主入口（WebSocket、定时轮询等）。
        """
        if not self._running:
            return

        if self._risk_engine.strategies_halted:
            logger.debug("Strategies halted, skipping bar")
            return

        key = str(bar.instrument_id)
        self._current_prices[key] = bar.close
        self._bar_count += 1

        for strategy, instruments in self._strategies:
            if key in instruments or not instruments:
                strategy.on_bar(bar)

    def submit_order(self, order: Order) -> str:
        """策略调用的下单接口（经风控检查）。"""
        decision = self._risk_engine.pre_trade_check(
            order=order,
            account=self._account,
            positions=self._positions,
            current_prices=self._current_prices,
        )

        if decision.result == RiskCheckResult.REJECTED:
            from quant_trading.model.order import OrderStatus

            order.status = OrderStatus.REJECTED
            order.reject_reason = decision.reason
            logger.warning(f"Order rejected: {decision.reason}")
            return order.order_id

        self._risk_engine.record_order()

        if self._gateway:
            asyncio.ensure_future(self._submit_to_gateway(order))
        else:
            logger.info(
                f"Order (no gateway): {order.side.value} {order.quantity} "
                f"{order.instrument_id} @ {order.price}"
            )

        return order.order_id

    def cancel_order(self, order_id: str) -> bool:
        """撤销订单。"""
        if self._gateway:
            asyncio.ensure_future(self._gateway.cancel_order(order_id))
            return True
        return False

    async def _submit_to_gateway(self, order: Order) -> None:
        """将订单异步提交到网关。"""
        try:
            key = str(order.instrument_id)
            if key in self._current_prices:
                self._gateway.on_price_update(order.instrument_id, self._current_prices[key])
            order_id = await self._gateway.submit_order(order)
            logger.info(f"Order submitted to gateway: {order_id}")

            # 成交后更新持仓
            account = await self._gateway.query_account()
            self._account = account
        except Exception as e:
            logger.error(f"Failed to submit order to gateway: {e}")

    def on_fill(self, fill: Fill) -> None:
        """处理来自网关的成交回报。"""
        position = self.get_position(fill.instrument_id)
        position.apply_fill(fill)

        if fill.side == OrderSide.BUY:
            cost = fill.price * fill.quantity + fill.commission
            self._account.available -= cost
        else:
            proceeds = fill.price * fill.quantity - fill.commission
            self._account.available += proceeds

        self._account.commission += fill.commission

        for strategy, _ in self._strategies:
            strategy.on_fill(fill)

    def get_status(self) -> dict:
        """返回运行器状态摘要。"""
        return {
            "running": self._running,
            "bar_count": self._bar_count,
            "strategy_count": len(self._strategies),
            "strategies": [
                {
                    "id": s.strategy_id,
                    "instruments": insts,
                }
                for s, insts in self._strategies
            ],
            "positions": {
                k: {
                    "quantity": p.quantity,
                    "avg_cost": float(p.avg_cost),
                    "side": p.side,
                }
                for k, p in self._positions.items()
                if not p.is_flat
            },
            "account": {
                "balance": float(self._account.balance),
                "available": float(self._account.available),
            },
            "risk": self._risk_engine.get_status(),
        }
