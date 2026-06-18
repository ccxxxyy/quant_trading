"""TWAP 执行算法 - 时间加权平均价格。"""

from __future__ import annotations

from datetime import datetime, timedelta

from quant_trading.model.instrument import InstrumentId
from quant_trading.model.order import Order, OrderSide, OrderType


class TWAPAlgorithm:
    """TWAP（时间加权平均价格）执行算法。

    将一个大订单拆分成多个等量的小订单，
    在一段时间内按固定间隔均匀执行，
    以减少大额交易对市场价格的冲击。
    """

    def __init__(
        self,
        instrument_id: InstrumentId,
        side: OrderSide,
        total_quantity: int,
        duration_minutes: int = 30,
        num_slices: int = 10,
    ) -> None:
        self._instrument_id = instrument_id
        self._side = side
        self._total_quantity = total_quantity
        self._duration = timedelta(minutes=duration_minutes)
        self._num_slices = num_slices
        self._slice_quantity = total_quantity // num_slices
        self._remainder = total_quantity % num_slices
        self._interval = self._duration / num_slices
        self._slices_sent = 0
        self._filled_quantity = 0
        self._start_time: datetime | None = None
        self._completed = False

    def start(self, current_time: datetime) -> None:
        self._start_time = current_time

    def get_next_order(self, current_time: datetime) -> Order | None:
        """如果到了发送时间，返回下一个子订单。"""
        if self._completed or self._start_time is None:
            return None

        elapsed = current_time - self._start_time
        expected_slices = min(
            int(elapsed / self._interval) + 1,
            self._num_slices,
        )

        if self._slices_sent >= expected_slices:
            return None

        # 计算本次子订单的数量
        quantity = self._slice_quantity
        if self._slices_sent == self._num_slices - 1:
            quantity += self._remainder  # 最后一片包含余数

        self._slices_sent += 1
        if self._slices_sent >= self._num_slices:
            self._completed = True

        return Order(
            instrument_id=self._instrument_id,
            side=self._side,
            order_type=OrderType.MARKET,
            quantity=quantity,
        )

    def on_fill(self, quantity: int) -> None:
        self._filled_quantity += quantity

    @property
    def is_completed(self) -> bool:
        return self._completed

    @property
    def progress(self) -> float:
        """执行进度（0.0 ~ 1.0）。"""
        if self._total_quantity == 0:
            return 1.0
        return self._filled_quantity / self._total_quantity
