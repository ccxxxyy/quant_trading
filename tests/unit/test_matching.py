"""撮合引擎的单元测试。"""

from datetime import datetime
from decimal import Decimal

from quant_trading.backtest.matching import MatchingEngine
from quant_trading.model.instrument import Exchange, InstrumentId
from quant_trading.model.market import Bar, BarInterval
from quant_trading.model.order import Order, OrderSide, OrderType


def make_bar(price: float = 100.0) -> Bar:
    return Bar(
        instrument_id=InstrumentId("TEST", Exchange.SSE),
        timestamp=datetime.now(),
        interval=BarInterval.DAILY,
        open=Decimal(str(price)),
        high=Decimal(str(price + 2)),
        low=Decimal(str(price - 2)),
        close=Decimal(str(price + 1)),
        volume=10000,
    )


class TestMatchingEngine:
    def test_market_order_fills_at_open(self):
        engine = MatchingEngine(commission_rate=Decimal("0"), slippage_rate=Decimal("0"))
        iid = InstrumentId("TEST", Exchange.SSE)

        order = Order(
            instrument_id=iid,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
        )
        engine.submit_order(order)

        bar = make_bar(100.0)
        fills = engine.match_bar(bar)

        assert len(fills) == 1
        assert fills[0].price == Decimal("100.0")
        assert fills[0].quantity == 100

    def test_limit_buy_fills_when_price_drops(self):
        engine = MatchingEngine(commission_rate=Decimal("0"), slippage_rate=Decimal("0"))
        iid = InstrumentId("TEST", Exchange.SSE)

        order = Order(
            instrument_id=iid,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=50,
            price=Decimal("99.0"),
        )
        engine.submit_order(order)

        bar = make_bar(100.0)  # 最低价98，低于限价99，可以成交
        fills = engine.match_bar(bar)

        assert len(fills) == 1
        assert fills[0].price <= Decimal("99.0")

    def test_limit_buy_no_fill_when_price_high(self):
        engine = MatchingEngine(commission_rate=Decimal("0"), slippage_rate=Decimal("0"))
        iid = InstrumentId("TEST", Exchange.SSE)

        order = Order(
            instrument_id=iid,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=50,
            price=Decimal("90.0"),
        )
        engine.submit_order(order)

        bar = make_bar(100.0)  # 最低价98，高于限价90，不成交
        fills = engine.match_bar(bar)

        assert len(fills) == 0
        assert engine.pending_count == 1

    def test_cancel_order(self):
        engine = MatchingEngine()
        iid = InstrumentId("TEST", Exchange.SSE)

        order = Order(
            instrument_id=iid,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=50,
            price=Decimal("90.0"),
        )
        engine.submit_order(order)
        assert engine.pending_count == 1

        result = engine.cancel_order(order.order_id)
        assert result is True
        assert engine.pending_count == 0

    def test_commission_applied(self):
        rate = Decimal("0.001")
        engine = MatchingEngine(
            commission_rate=rate, slippage_rate=Decimal("0"), transfer_fee_rate=Decimal("0")
        )
        iid = InstrumentId("TEST", Exchange.SSE)

        order = Order(
            instrument_id=iid,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=100,
        )
        engine.submit_order(order)

        bar = make_bar(100.0)
        fills = engine.match_bar(bar)

        expected_commission = Decimal("100.0") * 100 * rate
        assert fills[0].commission == expected_commission
