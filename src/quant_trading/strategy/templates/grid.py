"""网格交易策略模板 - 适用于震荡行情的自动化交易策略。"""

from __future__ import annotations

from decimal import Decimal

from quant_trading.model.instrument import InstrumentId
from quant_trading.model.market import Bar
from quant_trading.strategy.base import BarSeriesStrategy


class GridTradingStrategy(BarSeriesStrategy):
    """网格交易策略（Grid Trading）。

    在指定价格区间内按固定间距设置多个网格线，
    价格每下穿一条网格线则买入，每上穿一条网格线则卖出。
    适合在震荡市（价格在一定范围内反复波动）中使用。

    原理：
        - 设定价格上界和下界
        - 在区间内等距划分 N 条网格线
        - 价格从上方穿越某网格线到下方 → 在该网格线价位买入
        - 价格从下方穿越某网格线到上方 → 在该网格线价位卖出
        - 不断低买高卖赚取差价

    参数：
        upper_price: 网格上界价格
        lower_price: 网格下界价格
        grid_count: 网格线数量（默认10条）
        quantity_per_grid: 每格下单数量（默认100股）
        instrument_id: 目标交易标的
    """

    def __init__(self, params: dict | None = None, **kwargs) -> None:
        params = params or {}
        params.setdefault("upper_price", 110.0)
        params.setdefault("lower_price", 90.0)
        params.setdefault("grid_count", 10)
        params.setdefault("quantity_per_grid", 100)
        super().__init__(strategy_id="GridTrading", params=params, **kwargs)
        self._instrument_id: InstrumentId | None = None
        self._grid_levels: list[Decimal] = []
        self._prev_price: Decimal | None = None
        self._grid_positions: dict[int, bool] = {}  # grid_idx -> 是否已在该格位持仓

    def on_init(self) -> None:
        instrument_str = self._params.get("instrument_id")
        if instrument_str:
            self._instrument_id = InstrumentId.from_str(instrument_str)

        # 计算网格线位置
        upper = Decimal(str(self._params["upper_price"]))
        lower = Decimal(str(self._params["lower_price"]))
        count = self._params["grid_count"]
        step = (upper - lower) / count

        self._grid_levels = [lower + step * i for i in range(count + 1)]
        self._grid_positions = {i: False for i in range(len(self._grid_levels))}

    def on_bar_update(self, bar: Bar) -> None:
        if self._instrument_id and bar.instrument_id != self._instrument_id:
            return

        instrument_id = bar.instrument_id
        price = bar.close

        if self._prev_price is None:
            self._prev_price = price
            return

        quantity = self._params["quantity_per_grid"]

        # 检查价格是否穿越了某条网格线
        for i, level in enumerate(self._grid_levels):
            # 价格从上方穿到下方（下穿） → 买入信号
            if self._prev_price >= level and price < level:
                if not self._grid_positions.get(i, False):
                    self.ctx.buy_market(instrument_id, quantity)
                    self._grid_positions[i] = True

            # 价格从下方穿到上方（上穿） → 卖出信号
            elif self._prev_price <= level and price > level:
                if self._grid_positions.get(i, False):
                    self.ctx.sell_market(instrument_id, quantity)
                    self._grid_positions[i] = False

        self._prev_price = price
