"""模拟撮合引擎 - 在回测中模拟交易所的订单撮合过程。

支持 A 股交易规则：
    - T+1 约束：当日买入的股票不能当日卖出
    - 涨跌停过滤：触及涨跌停板时限制成交
    - 印花税：仅卖出时收取（默认万分之五）
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from quant_trading.model.market import Bar, Tick
from quant_trading.model.order import Fill, Order, OrderSide, OrderStatus, OrderType

logger = logging.getLogger(__name__)


class MatchingEngine:
    """模拟订单撮合，支持可配置的滑点和手续费。

    支持市价单、限价单和止损单，基于K线数据进行撮合。
    滑点模型为价格的固定百分比。

    A 股规则（enable_t1=True）：
        - 当日买入的股票不能当日卖出
        - 涨跌停时无法买入/卖出
        - 卖出额外收取印花税
    """

    def __init__(
        self,
        commission_rate: Decimal = Decimal("0.0003"),
        slippage_rate: Decimal = Decimal("0.0001"),
        stamp_tax_rate: Decimal = Decimal("0.0005"),
        enable_t1: bool = False,
        price_limit_pct: float = 0.10,
    ) -> None:
        self._commission_rate = commission_rate
        self._slippage_rate = slippage_rate
        self._stamp_tax_rate = stamp_tax_rate
        self._enable_t1 = enable_t1
        self._price_limit_pct = Decimal(str(price_limit_pct))
        self._pending_orders: list[Order] = []
        # T+1 追踪：instrument_key -> {date -> 当日买入数量}
        self._buy_date_qty: dict[str, dict[str, int]] = {}
        # 上一日收盘价：用于计算涨跌停板
        self._prev_close: dict[str, Decimal] = {}

    def submit_order(self, order: Order) -> None:
        """将订单提交到撮合引擎。"""
        order.status = OrderStatus.SUBMITTED
        self._pending_orders.append(order)

    def cancel_order(self, order_id: str) -> bool:
        """撤销一个挂起的订单。"""
        for order in self._pending_orders:
            if order.order_id == order_id and order.is_active:
                order.status = OrderStatus.CANCELLED
                order.updated_at = datetime.now()
                self._pending_orders.remove(order)
                return True
        return False

    def update_prev_close(self, instrument_key: str, close: Decimal) -> None:
        """更新某标的的上一日收盘价（用于计算涨跌停板）。"""
        self._prev_close[instrument_key] = close

    def get_sellable_quantity(self, instrument_key: str, date_str: str, held_qty: int) -> int:
        """获取 T+1 规则下可卖出的数量。

        可卖数量 = 总持仓 - 当日买入数量
        """
        if not self._enable_t1:
            return held_qty
        today_bought = self._buy_date_qty.get(instrument_key, {}).get(date_str, 0)
        return max(0, held_qty - today_bought)

    def _is_limit_up(self, bar: Bar) -> bool:
        """判断是否涨停（收盘价 = 最高价 = 涨停价，且成交量极低表示封板）。"""
        key = str(bar.instrument_id)
        prev = self._prev_close.get(key)
        if prev is None or prev == 0:
            return False
        limit_price = _round_limit(prev * (1 + self._price_limit_pct))
        return bar.close >= limit_price and bar.high == bar.low == limit_price

    def _is_limit_down(self, bar: Bar) -> bool:
        """判断是否跌停。"""
        key = str(bar.instrument_id)
        prev = self._prev_close.get(key)
        if prev is None or prev == 0:
            return False
        limit_price = _round_limit(prev * (1 - self._price_limit_pct))
        return bar.close <= limit_price and bar.high == bar.low == limit_price

    def match_bar(self, bar: Bar) -> list[Fill]:
        """尝试用一根K线撮合所有挂起的订单，返回成交列表。"""
        fills: list[Fill] = []
        remaining: list[Order] = []

        for order in self._pending_orders:
            rejected_reason = self._check_trade_rules(order, bar)
            if rejected_reason:
                order.status = OrderStatus.REJECTED
                order.reject_reason = rejected_reason
                order.updated_at = bar.timestamp
                logger.info(f"Order rejected: {rejected_reason}")
                continue

            fill = self._try_match(order, bar)
            if fill:
                fills.append(fill)
                self._record_buy(fill)
            elif order.is_active:
                remaining.append(order)

        self._pending_orders = remaining
        # 更新上一日收盘价
        self._prev_close[str(bar.instrument_id)] = bar.close
        return fills

    def _check_trade_rules(self, order: Order, bar: Bar) -> str | None:
        """检查 A 股交易规则，返回拒绝原因或 None。"""
        key = str(order.instrument_id)

        # 涨停时不能买入（涨停封板无卖盘）
        if order.side == OrderSide.BUY and self._is_limit_up(bar):
            return f"Limit up: cannot buy {key}"

        # 跌停时不能卖出（跌停封板无买盘）
        if order.side == OrderSide.SELL and self._is_limit_down(bar):
            return f"Limit down: cannot sell {key}"

        return None

    def _record_buy(self, fill: Fill) -> None:
        """记录买入成交（用于 T+1 追踪）。"""
        if not self._enable_t1 or fill.side != OrderSide.BUY:
            return
        key = str(fill.instrument_id)
        date_str = fill.timestamp.strftime("%Y-%m-%d")
        if key not in self._buy_date_qty:
            self._buy_date_qty[key] = {}
        self._buy_date_qty[key][date_str] = (
            self._buy_date_qty[key].get(date_str, 0) + fill.quantity
        )

    def match_tick(self, tick: Tick) -> list[Fill]:
        """尝试用一个逐笔行情撮合所有挂起的订单。"""
        fills: list[Fill] = []
        remaining: list[Order] = []

        for order in self._pending_orders:
            fill = self._try_match_tick(order, tick)
            if fill:
                fills.append(fill)
            elif order.is_active:
                remaining.append(order)

        self._pending_orders = remaining
        return fills

    def _try_match(self, order: Order, bar: Bar) -> Fill | None:
        """尝试基于K线数据撮合一个订单。"""
        if order.order_type == OrderType.MARKET:
            fill_price = self._apply_slippage(bar.open, order.side)
            return self._create_fill(order, fill_price, bar.timestamp)

        elif order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY and bar.low <= order.price:
                fill_price = min(order.price, bar.open)
                fill_price = self._apply_slippage(fill_price, order.side)
                return self._create_fill(order, fill_price, bar.timestamp)
            elif order.side == OrderSide.SELL and bar.high >= order.price:
                fill_price = max(order.price, bar.open)
                fill_price = self._apply_slippage(fill_price, order.side)
                return self._create_fill(order, fill_price, bar.timestamp)

        elif order.order_type == OrderType.STOP:
            if order.side == OrderSide.BUY and bar.high >= order.stop_price:
                fill_price = self._apply_slippage(order.stop_price, order.side)
                return self._create_fill(order, fill_price, bar.timestamp)
            elif order.side == OrderSide.SELL and bar.low <= order.stop_price:
                fill_price = self._apply_slippage(order.stop_price, order.side)
                return self._create_fill(order, fill_price, bar.timestamp)

        return None

    def _try_match_tick(self, order: Order, tick: Tick) -> Fill | None:
        """尝试基于逐笔行情撮合一个订单。"""
        if order.order_type == OrderType.MARKET:
            price = tick.ask_price if order.side == OrderSide.BUY else tick.bid_price
            fill_price = self._apply_slippage(price, order.side)
            return self._create_fill(order, fill_price, tick.timestamp)

        elif order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY and tick.ask_price <= order.price:
                return self._create_fill(order, order.price, tick.timestamp)
            elif order.side == OrderSide.SELL and tick.bid_price >= order.price:
                return self._create_fill(order, order.price, tick.timestamp)

        return None

    def _apply_slippage(self, price: Decimal, side: OrderSide) -> Decimal:
        """对成交价格施加滑点。"""
        slippage = price * self._slippage_rate
        if side == OrderSide.BUY:
            return price + slippage  # 买入时滑点使价格略高
        return price - slippage  # 卖出时滑点使价格略低

    def _create_fill(self, order: Order, price: Decimal, timestamp: datetime) -> Fill:
        """创建成交回报并更新订单状态。"""
        quantity = order.remaining_quantity
        commission = price * quantity * self._commission_rate
        # A 股卖出额外收取印花税
        if order.side == OrderSide.SELL and self._stamp_tax_rate > 0:
            commission += price * quantity * self._stamp_tax_rate

        fill = Fill(
            order_id=order.order_id,
            instrument_id=order.instrument_id,
            side=order.side,
            price=price,
            quantity=quantity,
            commission=commission,
            timestamp=timestamp,
        )

        # 更新订单状态
        order.filled_quantity += quantity
        order.avg_fill_price = price
        order.commission += commission
        order.status = OrderStatus.FILLED
        order.updated_at = timestamp

        return fill

    @property
    def pending_count(self) -> int:
        return len(self._pending_orders)

    def reset(self) -> None:
        self._pending_orders.clear()
        self._buy_date_qty.clear()
        self._prev_close.clear()


def _round_limit(price: Decimal, tick: Decimal = Decimal("0.01")) -> Decimal:
    """将涨跌停价格对齐到最小变动单位。"""
    return (price / tick).quantize(Decimal(1)) * tick
