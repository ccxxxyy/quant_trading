"""VWAP 执行算法 - 按成交量加权均价拆单。

VWAP（Volume Weighted Average Price，成交量加权平均价）算法
根据历史成交量分布，将大单按各时间段的成交量占比拆分为多个子订单，
使最终成交均价尽可能接近市场 VWAP。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from quant_trading.model.instrument import InstrumentId
from quant_trading.model.order import Order, OrderSide, OrderType

logger = logging.getLogger(__name__)


@dataclass
class VWAPSlice:
    """VWAP 时间切片。"""

    slice_index: int
    volume_pct: float  # 该时段成交量占全天比例
    quantity: int  # 该时段应下单数量
    order: Order | None = None


class VWAPAlgorithm:
    """VWAP 拆单算法。

    根据历史成交量的日内分布（volume profile），
    将目标数量按各时段的成交量占比分配。

    典型日内成交量分布（A股示例）：
        - 09:30-10:00: 高（开盘活跃）
        - 10:00-11:30: 中
        - 13:00-14:00: 中低
        - 14:00-15:00: 高（尾盘活跃）

    参数：
        instrument_id: 交易标的
        side: 买/卖方向
        total_quantity: 总下单数量
        num_slices: 拆分切片数（默认10）
        volume_profile: 各切片的成交量权重，长度需等于 num_slices
                        如果不提供则使用均匀分配
        min_quantity: 每个切片的最小下单量（默认1）
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        side: OrderSide,
        total_quantity: int,
        num_slices: int = 10,
        volume_profile: list[float] | None = None,
        min_quantity: int = 1,
    ) -> None:
        self._instrument_id = instrument_id
        self._side = side
        self._total_quantity = total_quantity
        self._num_slices = num_slices
        self._min_quantity = min_quantity

        if volume_profile:
            if len(volume_profile) != num_slices:
                raise ValueError(
                    f"volume_profile length ({len(volume_profile)}) "
                    f"must equal num_slices ({num_slices})"
                )
            total_weight = sum(volume_profile)
            self._weights = [w / total_weight for w in volume_profile]
        else:
            self._weights = [1.0 / num_slices] * num_slices

        self._slices = self._compute_slices()
        self._current_slice = 0

    def _compute_slices(self) -> list[VWAPSlice]:
        """按成交量权重计算各切片的下单数量。"""
        slices = []
        allocated = 0

        for i, weight in enumerate(self._weights):
            if i == len(self._weights) - 1:
                qty = self._total_quantity - allocated
            else:
                qty = max(self._min_quantity, round(self._total_quantity * weight))

            allocated += qty
            slices.append(
                VWAPSlice(
                    slice_index=i,
                    volume_pct=weight,
                    quantity=qty,
                )
            )

        # 修正溢出
        if allocated > self._total_quantity:
            excess = allocated - self._total_quantity
            for s in reversed(slices):
                reduce = min(excess, s.quantity - self._min_quantity)
                s.quantity -= reduce
                excess -= reduce
                if excess <= 0:
                    break

        return slices

    def next_order(self) -> Order | None:
        """获取下一个切片的订单。"""
        if self._current_slice >= len(self._slices):
            return None

        sl = self._slices[self._current_slice]
        if sl.quantity <= 0:
            self._current_slice += 1
            return self.next_order()

        order = Order(
            instrument_id=self._instrument_id,
            side=self._side,
            order_type=OrderType.MARKET,
            quantity=sl.quantity,
            strategy_id="VWAP",
        )
        sl.order = order
        self._current_slice += 1

        logger.debug(
            f"VWAP slice {sl.slice_index + 1}/{self._num_slices}: "
            f"qty={sl.quantity} ({sl.volume_pct:.1%})"
        )
        return order

    def get_all_orders(self) -> list[Order]:
        """一次性生成所有切片的订单列表。"""
        orders = []
        while True:
            order = self.next_order()
            if order is None:
                break
            orders.append(order)
        return orders

    @property
    def slices(self) -> list[VWAPSlice]:
        return self._slices

    @property
    def is_complete(self) -> bool:
        return self._current_slice >= len(self._slices)

    @property
    def filled_quantity(self) -> int:
        return sum(s.quantity for s in self._slices if s.order is not None)

    @property
    def remaining_quantity(self) -> int:
        return self._total_quantity - self.filled_quantity


# 常用的日内成交量分布模板
A_SHARE_VOLUME_PROFILE = [
    0.15,  # 09:30-09:54（开盘活跃）
    0.10,  # 09:54-10:18
    0.08,  # 10:18-10:42
    0.07,  # 10:42-11:06
    0.06,  # 11:06-11:30
    0.06,  # 13:00-13:24
    0.08,  # 13:24-13:48
    0.10,  # 13:48-14:12
    0.12,  # 14:12-14:36
    0.18,  # 14:36-15:00（尾盘活跃）
]
