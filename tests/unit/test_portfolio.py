"""组合管理器的单元测试。"""

from datetime import datetime
from decimal import Decimal

from quant_trading.model.account import Account
from quant_trading.model.instrument import Currency, Exchange, InstrumentId
from quant_trading.model.order import Fill, OrderSide
from quant_trading.portfolio.manager import PortfolioManager

IID_A = InstrumentId("600519", Exchange.SSE)
IID_B = InstrumentId("000001", Exchange.SZSE)


def make_account(balance: float = 1_000_000.0) -> Account:
    return Account(
        account_id="test",
        currency=Currency.CNY,
        balance=Decimal(str(balance)),
        available=Decimal(str(balance)),
    )


class TestPortfolioManager:
    def test_initial_equity(self):
        pm = PortfolioManager(make_account(500_000.0))
        assert pm.total_equity == Decimal("500000.0")
        assert pm.num_positions == 0

    def test_add_position_and_equity(self):
        pm = PortfolioManager(make_account(1_000_000.0))
        pos = pm.get_position(IID_A)
        fill = Fill(
            order_id="1",
            instrument_id=IID_A,
            side=OrderSide.BUY,
            price=Decimal("1800"),
            quantity=100,
            commission=Decimal("54"),
            timestamp=datetime.now(),
        )
        pos.apply_fill(fill)
        pm.update_price(IID_A, Decimal("1900"))

        assert pm.num_positions == 1
        assert pm.total_unrealized_pnl == Decimal("10000")  # (1900-1800)*100

    def test_concentration(self):
        pm = PortfolioManager(make_account(100_000.0))
        pos = pm.get_position(IID_A)
        fill = Fill(
            order_id="1",
            instrument_id=IID_A,
            side=OrderSide.BUY,
            price=Decimal("100"),
            quantity=500,
            commission=Decimal("15"),
            timestamp=datetime.now(),
        )
        pos.apply_fill(fill)
        pm.update_price(IID_A, Decimal("100"))

        concentration = pm.get_concentration()
        assert str(IID_A) in concentration
        assert concentration[str(IID_A)] > 0

    def test_summary(self):
        pm = PortfolioManager(make_account(100_000.0))
        summary = pm.summary()
        assert "equity" in summary
        assert "cash" in summary
        assert "num_positions" in summary
        assert summary["num_positions"] == 0

    def test_net_exposure_long_short(self):
        pm = PortfolioManager(make_account(200_000.0))

        pos_a = pm.get_position(IID_A)
        fill_a = Fill(
            order_id="1",
            instrument_id=IID_A,
            side=OrderSide.BUY,
            price=Decimal("100"),
            quantity=100,
            commission=Decimal("3"),
            timestamp=datetime.now(),
        )
        pos_a.apply_fill(fill_a)
        pm.update_price(IID_A, Decimal("100"))

        pos_b = pm.get_position(IID_B)
        fill_b = Fill(
            order_id="2",
            instrument_id=IID_B,
            side=OrderSide.SELL,
            price=Decimal("50"),
            quantity=100,
            commission=Decimal("1.5"),
            timestamp=datetime.now(),
        )
        pos_b.apply_fill(fill_b)
        pm.update_price(IID_B, Decimal("50"))

        # 多头10000 + 空头-5000 = 净敞口5000
        assert pm.net_exposure == Decimal("5000")
        # 总敞口 = |10000| + |-5000| = 15000
        assert pm.gross_exposure == Decimal("15000")
