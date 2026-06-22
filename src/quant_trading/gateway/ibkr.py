"""盈透证券(IB)网关 - 美股及多市场实盘交易。

通过 ib_insync 库连接 IB TWS 或 IB Gateway 客户端，
实现订单提交、行情订阅和账户查询。
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from quant_trading.gateway.base import BaseGateway
from quant_trading.model.account import Account
from quant_trading.model.instrument import Currency, InstrumentId
from quant_trading.model.market import Bar, BarInterval
from quant_trading.model.order import Fill, Order, OrderSide, OrderStatus, OrderType
from quant_trading.model.position import Position

logger = logging.getLogger(__name__)


class IBGateway(BaseGateway):
    """盈透证券网关，支持美股、期权和期货交易。

    使用前提：
        1. 安装 ib_insync: pip install ib_insync
        2. 运行 IB TWS 或 IB Gateway 客户端
        3. 在 TWS/Gateway 中启用 API 连接（默认端口: TWS=7497, Gateway=4001）
        4. 配置 host, port, client_id

    支持市场：NYSE, NASDAQ, AMEX, LSE, HKEX 等 IB 覆盖的 150+ 交易所
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        readonly: bool = False,
        timeout: int = 30,
    ) -> None:
        super().__init__(name="ib")
        self._host = host
        self._port = port
        self._client_id = client_id
        self._readonly = readonly
        self._timeout = timeout
        self._ib: Any = None
        self._order_map: dict[str, Any] = {}  # order_id -> IB Trade 对象

    async def connect(self) -> None:
        """连接到 IB TWS/Gateway。"""
        try:
            from ib_insync import IB
        except ImportError:
            raise ImportError("ib_insync is required for IB gateway: pip install ib_insync")

        self._ib = IB()
        try:
            await self._ib.connectAsync(
                host=self._host,
                port=self._port,
                clientId=self._client_id,
                readonly=self._readonly,
                timeout=self._timeout,
            )
            self._connected = True
            logger.info(f"IB Gateway connected to {self._host}:{self._port}")

            # 注册成交回调
            self._ib.orderStatusEvent += self._on_order_status
            self._ib.newOrderEvent += self._on_new_order

        except Exception as e:
            logger.error(f"IB connection failed: {e}")
            raise

    async def disconnect(self) -> None:
        """断开 IB 连接。"""
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
        self._connected = False
        logger.info("IB Gateway disconnected")

    async def subscribe_market_data(self, instruments: list[InstrumentId]) -> None:
        """订阅实时行情。"""
        if not self._ib:
            raise RuntimeError("IB Gateway not connected")

        for inst_id in instruments:
            contract = self._to_ib_contract(inst_id)
            self._ib.reqMktData(contract)
            logger.info(f"IB subscribed to {inst_id}")

    async def submit_order(self, order: Order) -> str:
        """提交订单到 IB。"""
        if not self._ib:
            raise RuntimeError("IB Gateway not connected")
        if self._readonly:
            raise RuntimeError("IB Gateway is in readonly mode")

        from ib_insync import LimitOrder, MarketOrder, StopOrder

        contract = self._to_ib_contract(order.instrument_id)
        action = "BUY" if order.side == OrderSide.BUY else "SELL"

        if order.order_type == OrderType.MARKET:
            ib_order = MarketOrder(action, order.quantity)
        elif order.order_type == OrderType.LIMIT:
            ib_order = LimitOrder(action, order.quantity, float(order.price))
        elif order.order_type == OrderType.STOP:
            ib_order = StopOrder(action, order.quantity, float(order.stop_price))
        else:
            raise ValueError(f"Unsupported order type for IB: {order.order_type}")

        trade = self._ib.placeOrder(contract, ib_order)
        order.status = OrderStatus.SUBMITTED
        order.broker_order_id = str(trade.order.orderId)
        self._order_map[order.order_id] = trade

        logger.info(f"IB order submitted: {order.order_id} -> IB#{trade.order.orderId}")
        return order.order_id

    async def cancel_order(self, order_id: str) -> bool:
        """撤销 IB 订单。"""
        trade = self._order_map.get(order_id)
        if trade and self._ib:
            self._ib.cancelOrder(trade.order)
            logger.info(f"IB order cancel requested: {order_id}")
            return True
        return False

    async def query_positions(self) -> list[Position]:
        """查询 IB 持仓。"""
        if not self._ib:
            return []

        ib_positions = self._ib.positions()
        positions = []
        for ib_pos in ib_positions:
            inst_id = self._from_ib_contract(ib_pos.contract)
            if inst_id:
                pos = Position(
                    instrument_id=inst_id,
                    quantity=int(ib_pos.position),
                    avg_cost=Decimal(str(ib_pos.avgCost)),
                )
                positions.append(pos)
        return positions

    async def query_account(self) -> Account:
        """查询 IB 账户信息。"""
        if not self._ib:
            raise RuntimeError("IB Gateway not connected")

        summary = self._ib.accountSummary()
        account = Account(account_id="ib", currency=Currency.USD)

        for item in summary:
            if item.tag == "NetLiquidation":
                account.balance = Decimal(item.value)
            elif item.tag == "AvailableFunds":
                account.available = Decimal(item.value)
            elif item.tag == "InitMarginReq":
                account.margin = Decimal(item.value)
            elif item.tag == "UnrealizedPnL":
                account.unrealized_pnl = Decimal(item.value)
            elif item.tag == "RealizedPnL":
                account.realized_pnl = Decimal(item.value)

        return account

    async def get_historical_bars(
        self,
        instrument_id: InstrumentId,
        interval: BarInterval = BarInterval.DAILY,
        duration: str = "1 Y",
    ) -> list[Bar]:
        """获取 IB 历史K线数据。"""
        if not self._ib:
            raise RuntimeError("IB Gateway not connected")

        contract = self._to_ib_contract(instrument_id)

        bar_size_map = {
            BarInterval.MINUTE_1: "1 min",
            BarInterval.MINUTE_5: "5 mins",
            BarInterval.MINUTE_15: "15 mins",
            BarInterval.MINUTE_30: "30 mins",
            BarInterval.HOUR_1: "1 hour",
            BarInterval.DAILY: "1 day",
        }
        bar_size = bar_size_map.get(interval, "1 day")

        ib_bars = self._ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,
        )

        bars = []
        for ib_bar in ib_bars:
            bars.append(
                Bar(
                    instrument_id=instrument_id,
                    timestamp=(
                        ib_bar.date
                        if isinstance(ib_bar.date, datetime)
                        else datetime.combine(ib_bar.date, datetime.min.time())
                    ),
                    interval=interval,
                    open=Decimal(str(ib_bar.open)),
                    high=Decimal(str(ib_bar.high)),
                    low=Decimal(str(ib_bar.low)),
                    close=Decimal(str(ib_bar.close)),
                    volume=int(ib_bar.volume),
                )
            )
        return bars

    def _to_ib_contract(self, instrument_id: InstrumentId) -> Any:
        """将本系统标的ID转换为 IB 合约对象。"""
        from ib_insync import Future, Stock

        from quant_trading.model.instrument import Exchange

        exchange_map = {
            Exchange.NYSE: "NYSE",
            Exchange.NASDAQ: "NASDAQ",
            Exchange.SSE: "SEHK",  # IB 不直接支持 A 股，可通过沪港通
            Exchange.IB: "SMART",
        }

        exchange = exchange_map.get(instrument_id.exchange, "SMART")

        if instrument_id.exchange in (Exchange.SHFE, Exchange.DCE, Exchange.CZCE, Exchange.CFFEX):
            return Future(symbol=instrument_id.symbol, exchange=exchange)

        return Stock(symbol=instrument_id.symbol, exchange=exchange, currency="USD")

    def _from_ib_contract(self, contract: Any) -> InstrumentId | None:
        """将 IB 合约对象转换为本系统标的ID。"""
        from quant_trading.model.instrument import Exchange

        ib_to_exchange = {
            "NYSE": Exchange.NYSE,
            "NASDAQ": Exchange.NASDAQ,
            "SMART": Exchange.IB,
        }

        exchange = ib_to_exchange.get(contract.exchange, Exchange.IB)
        return InstrumentId(symbol=contract.symbol, exchange=exchange)

    def _on_order_status(self, trade: Any) -> None:
        """IB 订单状态变化回调。"""
        for order_id, t in self._order_map.items():
            if t is trade and trade.orderStatus.status == "Filled":
                fill = Fill(
                    order_id=order_id,
                    instrument_id=self._from_ib_contract(trade.contract),
                    side=OrderSide.BUY if trade.order.action == "BUY" else OrderSide.SELL,
                    price=Decimal(str(trade.orderStatus.avgFillPrice)),
                    quantity=int(trade.orderStatus.filled),
                    commission=Decimal(str(trade.orderStatus.commission or 0)),
                    timestamp=datetime.now(),
                )
                if self._on_fill:
                    self._on_fill(fill)

    def _on_new_order(self, trade: Any) -> None:
        """IB 新订单事件回调。"""
        logger.debug(f"IB new order event: {trade.order.orderId}")
