"""模拟盘网关 - 使用真实行情但不花真钱的仿真交易。"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from quant_trading.gateway.base import BaseGateway
from quant_trading.model.account import Account
from quant_trading.model.instrument import Currency, InstrumentId
from quant_trading.model.order import Fill, Order, OrderSide, OrderStatus, OrderType
from quant_trading.model.position import Position

logger = logging.getLogger(__name__)


class PaperTradingGateway(BaseGateway):
    """模拟盘交易网关，使用真实行情数据在虚拟环境中执行交易。

    适合在实盘之前验证策略的实际表现。
    """

    def __init__(
        self,
        initial_capital: float = 1_000_000.0,
        commission_rate: float = 0.0003,
        slippage_rate: float = 0.0001,
    ) -> None:
        super().__init__(name="paper")
        self._commission_rate = Decimal(str(commission_rate))
        self._slippage_rate = Decimal(str(slippage_rate))
        self._account = Account(
            account_id="paper",
            currency=Currency.CNY,
            balance=Decimal(str(initial_capital)),
            available=Decimal(str(initial_capital)),
        )
        self._positions: dict[str, Position] = {}
        self._pending_orders: list[Order] = []
        self._latest_prices: dict[str, Decimal] = {}
        self._trailing_best: dict[str, Decimal] = {}

    async def connect(self) -> None:
        self._connected = True
        logger.info("Paper trading gateway connected")

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("Paper trading gateway disconnected")

    async def subscribe_market_data(self, instruments: list[InstrumentId]) -> None:
        logger.info(f"Paper gateway subscribing to {len(instruments)} instruments")

    def on_price_update(self, instrument_id: InstrumentId, price: Decimal) -> None:
        """收到最新价格时更新，并检查是否有挂单可以成交。"""
        self._latest_prices[str(instrument_id)] = price
        self._check_pending_orders(instrument_id, price)

    async def submit_order(self, order: Order) -> str:
        """提交订单 - 市价单立即成交，限价单挂起等待。"""
        order.status = OrderStatus.SUBMITTED
        key = str(order.instrument_id)

        if order.order_type == OrderType.MARKET:
            price = self._latest_prices.get(key)
            if price:
                fill_price = self._apply_slippage(price, order.side)
                self._execute_fill(order, fill_price)
            else:
                self._pending_orders.append(order)
        else:
            self._pending_orders.append(order)

        return order.order_id

    async def cancel_order(self, order_id: str) -> bool:
        for order in self._pending_orders:
            if order.order_id == order_id:
                order.status = OrderStatus.CANCELLED
                self._pending_orders.remove(order)
                return True
        return False

    async def query_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if not p.is_flat]

    async def query_account(self) -> Account:
        return self._account

    def _check_pending_orders(self, instrument_id: InstrumentId, price: Decimal) -> None:
        """检查是否有挂单可以在当前价格成交。"""
        to_remove = []
        for order in self._pending_orders:
            if order.instrument_id != instrument_id:
                continue
            if order.order_type == OrderType.LIMIT:
                if order.side == OrderSide.BUY and price <= order.price:
                    self._execute_fill(order, order.price)
                    to_remove.append(order)
                elif order.side == OrderSide.SELL and price >= order.price:
                    self._execute_fill(order, order.price)
                    to_remove.append(order)
            elif order.order_type == OrderType.MARKET:
                fill_price = self._apply_slippage(price, order.side)
                self._execute_fill(order, fill_price)
                to_remove.append(order)
            elif order.order_type == OrderType.TRAILING_STOP:
                if self._try_trailing_stop(order, price):
                    to_remove.append(order)
            elif order.order_type == OrderType.CONDITIONAL:
                if self._try_conditional(order, price):
                    to_remove.append(order)

        for order in to_remove:
            self._pending_orders.remove(order)

    def _try_trailing_stop(self, order: Order, price: Decimal) -> bool:
        """追踪止损：按绝对偏移量跟踪最优价并触发。"""
        offset = order.stop_price if order.stop_price > 0 else Decimal("1")
        oid = order.order_id
        if order.side == OrderSide.SELL:
            best = self._trailing_best.get(oid, price)
            if price > best:
                best = price
            self._trailing_best[oid] = best
            if price <= best - offset:
                self._execute_fill(order, self._apply_slippage(price, order.side))
                self._trailing_best.pop(oid, None)
                return True
        else:
            best = self._trailing_best.get(oid, price)
            if price < best:
                best = price
            self._trailing_best[oid] = best
            if price >= best + offset:
                self._execute_fill(order, self._apply_slippage(price, order.side))
                self._trailing_best.pop(oid, None)
                return True
        return False

    def _try_conditional(self, order: Order, price: Decimal) -> bool:
        """条件单：表达式满足后以市价成交。"""
        if not order.condition_expr:
            return False
        ns = {"close": float(price), "price": float(price)}
        try:
            triggered = bool(eval(order.condition_expr, {"__builtins__": {}}, ns))  # noqa: S307
        except Exception:
            return False
        if triggered:
            order.condition_met = True
            self._execute_fill(order, self._apply_slippage(price, order.side))
            return True
        return False

    def _execute_fill(self, order: Order, price: Decimal) -> None:
        """执行成交并更新持仓和账户。"""
        commission = price * order.quantity * self._commission_rate
        fill = Fill(
            order_id=order.order_id,
            instrument_id=order.instrument_id,
            side=order.side,
            price=price,
            quantity=order.quantity,
            commission=commission,
            timestamp=datetime.now(),
        )

        order.status = OrderStatus.FILLED
        order.filled_quantity = order.quantity
        order.avg_fill_price = price
        order.commission = commission

        # 更新持仓
        key = str(order.instrument_id)
        if key not in self._positions:
            self._positions[key] = Position(instrument_id=order.instrument_id)
        self._positions[key].apply_fill(fill)

        # 更新账户资金
        if order.side == OrderSide.BUY:
            self._account.available -= price * order.quantity + commission
        else:
            self._account.available += price * order.quantity - commission
        self._account.commission += commission

        # 通知回调
        if self._on_fill:
            self._on_fill(fill)

    def _apply_slippage(self, price: Decimal, side: OrderSide) -> Decimal:
        slippage = price * self._slippage_rate
        if side == OrderSide.BUY:
            return price + slippage
        return price - slippage
