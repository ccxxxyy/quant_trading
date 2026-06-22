"""领域模型的单元测试。"""

from datetime import datetime
from decimal import Decimal

from quant_trading.model.instrument import Exchange, InstrumentId
from quant_trading.model.market import Bar, BarInterval
from quant_trading.model.order import Fill, Order, OrderSide, OrderStatus, OrderType
from quant_trading.model.position import Position


class TestInstrumentId:
    def test_from_str(self):
        iid = InstrumentId.from_str("600519.SSE")
        assert iid.symbol == "600519"
        assert iid.exchange == Exchange.SSE

    def test_to_str(self):
        iid = InstrumentId(symbol="AAPL", exchange=Exchange.NASDAQ)
        assert str(iid) == "AAPL.NASDAQ"

    def test_roundtrip(self):
        original = "IF2401.CFFEX"
        iid = InstrumentId.from_str(original)
        assert str(iid) == original


class TestBar:
    def test_is_bullish(self):
        bar = Bar(
            instrument_id=InstrumentId("TEST", Exchange.SSE),
            timestamp=datetime.now(),
            interval=BarInterval.DAILY,
            open=Decimal("10.0"),
            high=Decimal("11.0"),
            low=Decimal("9.5"),
            close=Decimal("10.5"),
            volume=1000,
        )
        assert bar.is_bullish is True

    def test_is_bearish(self):
        bar = Bar(
            instrument_id=InstrumentId("TEST", Exchange.SSE),
            timestamp=datetime.now(),
            interval=BarInterval.DAILY,
            open=Decimal("10.5"),
            high=Decimal("11.0"),
            low=Decimal("9.5"),
            close=Decimal("10.0"),
            volume=1000,
        )
        assert bar.is_bullish is False


class TestPosition:
    def test_open_long(self):
        iid = InstrumentId("600519", Exchange.SSE)
        pos = Position(instrument_id=iid)

        fill = Fill(
            order_id="1",
            instrument_id=iid,
            side=OrderSide.BUY,
            price=Decimal("1800"),
            quantity=100,
            commission=Decimal("54"),
            timestamp=datetime.now(),
        )
        pos.apply_fill(fill)

        assert pos.quantity == 100
        assert pos.avg_cost == Decimal("1800")
        assert pos.side == "long"

    def test_close_long(self):
        iid = InstrumentId("600519", Exchange.SSE)
        pos = Position(instrument_id=iid)

        # 开仓
        buy_fill = Fill(
            order_id="1",
            instrument_id=iid,
            side=OrderSide.BUY,
            price=Decimal("1800"),
            quantity=100,
            commission=Decimal("54"),
            timestamp=datetime.now(),
        )
        pos.apply_fill(buy_fill)

        # 平仓
        sell_fill = Fill(
            order_id="2",
            instrument_id=iid,
            side=OrderSide.SELL,
            price=Decimal("1900"),
            quantity=100,
            commission=Decimal("57"),
            timestamp=datetime.now(),
        )
        pos.apply_fill(sell_fill)

        assert pos.is_flat
        assert pos.realized_pnl == Decimal("10000")  # (1900-1800)*100

    def test_unrealized_pnl(self):
        iid = InstrumentId("AAPL", Exchange.NASDAQ)
        pos = Position(instrument_id=iid)

        fill = Fill(
            order_id="1",
            instrument_id=iid,
            side=OrderSide.BUY,
            price=Decimal("150"),
            quantity=50,
            commission=Decimal("2.25"),
            timestamp=datetime.now(),
        )
        pos.apply_fill(fill)

        assert pos.unrealized_pnl(Decimal("160")) == Decimal("500")
        assert pos.unrealized_pnl(Decimal("140")) == Decimal("-500")


class TestOrder:
    def test_order_lifecycle(self):
        iid = InstrumentId("600519", Exchange.SSE)
        order = Order(
            instrument_id=iid,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            price=Decimal("1800"),
        )

        assert order.is_active
        assert order.remaining_quantity == 100

        order.status = OrderStatus.FILLED
        order.filled_quantity = 100
        assert order.is_completed
        assert order.remaining_quantity == 0
