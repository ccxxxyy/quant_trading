"""模拟盘网关 - 使用真实行情但不花真钱的仿真交易。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from quant_trading.gateway.base import BaseGateway
from quant_trading.model.account import Account
from quant_trading.model.instrument import Currency, InstrumentId
from quant_trading.model.order import Fill, Order, OrderSide, OrderStatus, OrderType
from quant_trading.model.position import Position

logger = logging.getLogger(__name__)

_PERSIST_DIR = Path("data/paper_trading")


class PaperTradingGateway(BaseGateway):
    """模拟盘交易网关，使用真实行情数据在虚拟环境中执行交易。

    适合在实盘之前验证策略的实际表现。
    数据会持久化到磁盘，重启后自动恢复订单/持仓/资金状态。
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        commission_rate: float = 0.0003,
        slippage_rate: float = 0.0001,
        account_name: str = "default",
    ) -> None:
        super().__init__(name="paper")
        self._account_name = account_name
        self._initial_capital = initial_capital
        self._commission_rate = Decimal(str(commission_rate))
        self._slippage_rate = Decimal(str(slippage_rate))
        self._account = Account(
            account_id=account_name,
            currency=Currency.CNY,
            balance=Decimal(str(initial_capital)),
            available=Decimal(str(initial_capital)),
        )
        self._positions: dict[str, Position] = {}
        self._pending_orders: list[Order] = []
        self._order_history: list[dict] = []
        self._latest_prices: dict[str, Decimal] = {}
        self._trailing_best: dict[str, Decimal] = {}
        self._load_state()

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
                self._save_state()
        else:
            self._pending_orders.append(order)
            self._save_state()

        return order.order_id

    async def cancel_order(self, order_id: str) -> bool:
        for order in self._pending_orders:
            if order.order_id == order_id:
                order.status = OrderStatus.CANCELLED
                self._pending_orders.remove(order)
                self._save_state()
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

        self._order_history.append(
            {
                "order_id": order.order_id,
                "instrument_id": str(order.instrument_id),
                "side": order.side.value,
                "order_type": order.order_type.value,
                "quantity": int(order.quantity),
                "price": float(price),
                "commission": float(commission),
                "status": order.status.value,
                "timestamp": fill.timestamp.isoformat(),
            }
        )

        if self._on_fill:
            self._on_fill(fill)

        self._save_state()

    def _apply_slippage(self, price: Decimal, side: OrderSide) -> Decimal:
        slippage = price * self._slippage_rate
        if side == OrderSide.BUY:
            return price + slippage
        return price - slippage

    # ── 持久化 ──────────────────────────────────────────────

    @property
    def _state_file(self) -> Path:
        return _PERSIST_DIR / f"{self._account_name}.json"

    def _save_state(self) -> None:
        """将账户/持仓/订单历史写入 JSON 文件。"""
        _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        positions = {}
        for k, p in self._positions.items():
            if not p.is_flat:
                positions[k] = {
                    "quantity": int(p.quantity),
                    "avg_cost": float(p.avg_cost),
                    "realized_pnl": float(p.realized_pnl),
                }
        pending = [
            {
                "order_id": o.order_id,
                "instrument_id": str(o.instrument_id),
                "side": o.side.value,
                "order_type": o.order_type.value,
                "quantity": int(o.quantity),
                "price": float(o.price) if o.price else 0,
                "stop_price": float(o.stop_price) if o.stop_price else 0,
                "condition_expr": o.condition_expr or "",
            }
            for o in self._pending_orders
        ]
        state = {
            "account": {
                "balance": float(self._account.balance),
                "available": float(self._account.available),
                "commission": float(self._account.commission),
            },
            "positions": positions,
            "pending_orders": pending,
            "order_history": self._order_history[-500:],
            "latest_prices": {k: float(v) for k, v in self._latest_prices.items()},
        }
        self._state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    def _load_state(self) -> None:
        """从磁盘恢复状态。"""
        if not self._state_file.exists():
            return
        try:
            state = json.loads(self._state_file.read_text())
            acc = state.get("account", {})
            self._account.balance = Decimal(str(acc.get("balance", self._initial_capital)))
            self._account.available = Decimal(str(acc.get("available", self._initial_capital)))
            self._account.commission = Decimal(str(acc.get("commission", 0)))

            for sym, pdata in state.get("positions", {}).items():
                iid = InstrumentId.from_str(sym)
                pos = Position(instrument_id=iid)
                qty = pdata["quantity"]
                cost = Decimal(str(pdata["avg_cost"]))
                if qty > 0:
                    fake_fill = Fill(
                        order_id="restore",
                        instrument_id=iid,
                        side=OrderSide.BUY,
                        price=cost,
                        quantity=abs(qty),
                        commission=Decimal(0),
                        timestamp=datetime.now(),
                    )
                    pos.apply_fill(fake_fill)
                elif qty < 0:
                    fake_fill = Fill(
                        order_id="restore",
                        instrument_id=iid,
                        side=OrderSide.SELL,
                        price=cost,
                        quantity=abs(qty),
                        commission=Decimal(0),
                        timestamp=datetime.now(),
                    )
                    pos.apply_fill(fake_fill)
                pos.realized_pnl = Decimal(str(pdata.get("realized_pnl", 0)))
                self._positions[sym] = pos

            for pod in state.get("pending_orders", []):
                o = Order(
                    instrument_id=InstrumentId.from_str(pod["instrument_id"]),
                    side=OrderSide.BUY if pod["side"] == "buy" else OrderSide.SELL,
                    order_type=OrderType(pod["order_type"]),
                    quantity=pod["quantity"],
                    price=Decimal(str(pod.get("price", 0))),
                )
                o.order_id = pod.get("order_id", o.order_id)
                o.status = OrderStatus.SUBMITTED
                if pod.get("stop_price"):
                    o.stop_price = Decimal(str(pod["stop_price"]))
                if pod.get("condition_expr"):
                    o.condition_expr = pod["condition_expr"]
                self._pending_orders.append(o)

            self._order_history = state.get("order_history", [])
            for sym, px in state.get("latest_prices", {}).items():
                self._latest_prices[sym] = Decimal(str(px))

            logger.info(
                f"Restored paper account '{self._account_name}': "
                f"balance={self._account.balance}, "
                f"{len(self._positions)} positions, "
                f"{len(self._pending_orders)} pending, "
                f"{len(self._order_history)} historical orders"
            )
        except Exception as e:
            logger.warning(f"Failed to load paper state: {e}")

    def reset(self) -> None:
        """重置账户到初始状态并清除持久化文件。"""
        self._account.balance = Decimal(str(self._initial_capital))
        self._account.available = Decimal(str(self._initial_capital))
        self._account.commission = Decimal(0)
        self._positions.clear()
        self._pending_orders.clear()
        self._order_history.clear()
        self._latest_prices.clear()
        self._trailing_best.clear()
        if self._state_file.exists():
            self._state_file.unlink()
        logger.info(f"Paper account '{self._account_name}' reset")
