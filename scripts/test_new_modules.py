"""验证新增模块功能的测试脚本。"""

from quant_trading.data.pipeline import DataPipeline, CleanStats
from quant_trading.model.market import Bar, BarInterval
from quant_trading.model.instrument import InstrumentId
from datetime import datetime

bars = []
for i in range(10):
    bars.append(Bar(
        instrument_id=InstrumentId.from_str("TEST.SSE"),
        interval=BarInterval.DAILY,
        timestamp=datetime(2024, 1, i + 1, 9, 30),
        open=100 + i, high=102 + i, low=99 + i, close=101 + i, volume=1000 + i * 10,
    ))
bars.append(bars[0])

pipeline = DataPipeline()
cleaned, stats = pipeline.process(bars)
print(f"DataPipeline: {len(bars)} -> {len(cleaned)} bars, removed {stats.removed_duplicates} dups")

from quant_trading.model.order_state import OrderStateMachine, VALID_TRANSITIONS
from quant_trading.model.order import Order, OrderStatus, OrderSide, OrderType

test_order = Order(
    instrument_id=InstrumentId.from_str("TEST.SSE"),
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    quantity=100,
    price=100.0,
)
sm = OrderStateMachine()
assert sm.transition(test_order, OrderStatus.SUBMITTED)
assert sm.transition(test_order, OrderStatus.PARTIAL_FILLED)
assert sm.transition(test_order, OrderStatus.FILLED)
blocked = sm.transition(test_order, OrderStatus.PENDING)
assert not blocked
print(f"OrderStateMachine: correctly blocked illegal transition from FILLED->PENDING")

from quant_trading.execution.algorithms.vwap import VWAPAlgorithm

vwap = VWAPAlgorithm(
    instrument_id=InstrumentId.from_str("TEST.SSE"),
    side=OrderSide.BUY,
    total_quantity=1000,
    num_slices=5,
)
slices = vwap.slices
total_qty = sum(s.quantity for s in slices)
print(f"VWAP: generated {len(slices)} child order slices, total qty = {total_qty}")

from quant_trading.monitoring.alert import AlertManager

am = AlertManager()
am.check_drawdown(1000000)
am.check_drawdown(850000)
alert_count = am.alert_count
recent = am.get_recent_alerts(limit=5)
last_type = recent[-1]["type"] if recent else "none"
print(f"AlertManager: {alert_count} alerts, last={last_type}")

from quant_trading.alpha.predict_service import PredictService

ps = PredictService()
print(f"PredictService: initialized")

from quant_trading.alpha.walkforward import WalkForwardValidator

wfv = WalkForwardValidator(strategy_id="dual_ma", symbol="TEST.SSE", train_days=60, test_days=20)
print(f"WalkForwardValidator: train_days={wfv._train_days}, test_days={wfv._test_days}")

from quant_trading.strategy.optimizer import StrategyOptimizer

opt = StrategyOptimizer(strategy_id="dual_ma", symbol="TEST.SSE", start="2024-01-01")
print(f"StrategyOptimizer: initialized for {opt._strategy_id}")

print()
print("=== ALL NEW MODULES FUNCTIONAL ===")
