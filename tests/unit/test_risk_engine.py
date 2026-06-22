"""风控引擎的单元测试。"""

from decimal import Decimal

from quant_trading.model.account import Account
from quant_trading.model.instrument import Currency, Exchange, InstrumentId
from quant_trading.model.order import Order, OrderSide, OrderType
from quant_trading.risk.engine import RiskCheckResult, RiskEngine


def make_account(balance: float = 100_000.0) -> Account:
    return Account(
        account_id="test",
        currency=Currency.CNY,
        balance=Decimal(str(balance)),
        available=Decimal(str(balance)),
    )


def make_order(
    price: float = 100.0,
    quantity: int = 100,
    side: OrderSide = OrderSide.BUY,
) -> Order:
    return Order(
        instrument_id=InstrumentId("TEST", Exchange.SSE),
        side=side,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        price=Decimal(str(price)),
    )


class TestRiskEngine:
    def test_order_passes_normal_check(self):
        engine = RiskEngine(
            max_position_pct=0.25,
            max_single_order_pct=0.10,
        )
        account = make_account(100_000.0)
        order = make_order(price=50.0, quantity=100)  # 5000元，占比5%
        decision = engine.pre_trade_check(order, account, {})
        assert decision.result == RiskCheckResult.PASSED

    def test_order_rejected_exceeds_size_limit(self):
        engine = RiskEngine(max_single_order_pct=0.05)
        account = make_account(100_000.0)
        order = make_order(price=100.0, quantity=100)  # 10000元，占比10%，超过5%限制
        decision = engine.pre_trade_check(order, account, {})
        assert decision.result == RiskCheckResult.REJECTED

    def test_order_rejected_position_concentration(self):
        engine = RiskEngine(max_position_pct=0.10, max_single_order_pct=0.50)
        account = make_account(100_000.0)
        order = make_order(price=200.0, quantity=100)  # 20000元，占比20%，超过10%限制
        decision = engine.pre_trade_check(order, account, {})
        assert decision.result == RiskCheckResult.REJECTED

    def test_disabled_engine_passes_all(self):
        engine = RiskEngine(max_single_order_pct=0.01)
        engine.disable()
        account = make_account(100_000.0)
        order = make_order(price=1000.0, quantity=100)
        decision = engine.pre_trade_check(order, account, {})
        assert decision.result == RiskCheckResult.PASSED

    def test_order_frequency_limit(self):
        engine = RiskEngine(max_order_frequency=3)
        account = make_account(100_000.0)
        order = make_order(price=10.0, quantity=10)

        # 先触发一次检查初始化日期，防止 _maybe_reset_daily 清空记录
        engine.pre_trade_check(order, account, {})

        for _ in range(3):
            engine.record_order()

        decision = engine.pre_trade_check(order, account, {})
        assert decision.result == RiskCheckResult.REJECTED
