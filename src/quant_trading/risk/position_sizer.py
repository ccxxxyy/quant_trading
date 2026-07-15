"""仓位管理模块 - 多种仓位计算模式。

支持模式：
    - 等权分配（EqualWeight）：资金均分到各标的
    - 风险平价（RiskParity）：按波动率倒数分配权重
    - 凯利公式（Kelly）：根据胜率和盈亏比计算最优仓位
    - 固定金额（FixedAmount）：每笔交易固定金额
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SizingMode(Enum):
    EQUAL_WEIGHT = "equal_weight"
    RISK_PARITY = "risk_parity"
    KELLY = "kelly"
    FIXED_AMOUNT = "fixed_amount"


@dataclass
class SizingResult:
    """仓位计算结果。"""

    instrument_key: str
    weight: float
    target_value: float
    target_quantity: int
    mode: SizingMode


class PositionSizer:
    """多模式仓位管理器。"""

    def __init__(self, mode: SizingMode = SizingMode.EQUAL_WEIGHT) -> None:
        self._mode = mode
        self._kelly_cap: float = 0.25  # 凯利公式仓位上限
        self._fixed_amount: float = 100_000.0

    @property
    def mode(self) -> SizingMode:
        return self._mode

    @mode.setter
    def mode(self, value: SizingMode) -> None:
        self._mode = value

    def set_kelly_cap(self, cap: float) -> None:
        self._kelly_cap = max(0.01, min(cap, 1.0))

    def set_fixed_amount(self, amount: float) -> None:
        self._fixed_amount = max(0, amount)

    def calculate(
        self,
        total_equity: float,
        instruments: list[str],
        current_prices: dict[str, float],
        volatilities: dict[str, float] | None = None,
        win_rates: dict[str, float] | None = None,
        payoff_ratios: dict[str, float] | None = None,
    ) -> list[SizingResult]:
        """根据当前模式计算各标的的目标仓位。"""
        if not instruments or total_equity <= 0:
            return []

        if self._mode == SizingMode.EQUAL_WEIGHT:
            return self._equal_weight(total_equity, instruments, current_prices)
        elif self._mode == SizingMode.RISK_PARITY:
            return self._risk_parity(total_equity, instruments, current_prices, volatilities or {})
        elif self._mode == SizingMode.KELLY:
            return self._kelly(
                total_equity,
                instruments,
                current_prices,
                win_rates or {},
                payoff_ratios or {},
            )
        elif self._mode == SizingMode.FIXED_AMOUNT:
            return self._fixed(instruments, current_prices)
        return []

    def _equal_weight(
        self,
        total_equity: float,
        instruments: list[str],
        prices: dict[str, float],
    ) -> list[SizingResult]:
        n = len(instruments)
        per_instrument = total_equity / n
        results = []
        for key in instruments:
            price = prices.get(key, 0)
            qty = int(per_instrument / price) if price > 0 else 0
            # A 股最低 1 手 = 100 股
            qty = (qty // 100) * 100
            results.append(
                SizingResult(
                    instrument_key=key,
                    weight=1.0 / n,
                    target_value=per_instrument,
                    target_quantity=qty,
                    mode=self._mode,
                )
            )
        return results

    def _risk_parity(
        self,
        total_equity: float,
        instruments: list[str],
        prices: dict[str, float],
        volatilities: dict[str, float],
    ) -> list[SizingResult]:
        inv_vols: dict[str, float] = {}
        for key in instruments:
            vol = volatilities.get(key, 0.0)
            inv_vols[key] = 1.0 / vol if vol > 0 else 0.0

        total_inv = sum(inv_vols.values())
        if total_inv == 0:
            return self._equal_weight(total_equity, instruments, prices)

        results = []
        for key in instruments:
            weight = inv_vols[key] / total_inv
            target_value = total_equity * weight
            price = prices.get(key, 0)
            qty = int(target_value / price) if price > 0 else 0
            qty = (qty // 100) * 100
            results.append(
                SizingResult(
                    instrument_key=key,
                    weight=weight,
                    target_value=target_value,
                    target_quantity=qty,
                    mode=self._mode,
                )
            )
        return results

    def _kelly(
        self,
        total_equity: float,
        instruments: list[str],
        prices: dict[str, float],
        win_rates: dict[str, float],
        payoff_ratios: dict[str, float],
    ) -> list[SizingResult]:
        results = []
        for key in instruments:
            p = win_rates.get(key, 0.5)
            b = payoff_ratios.get(key, 1.0)
            # Kelly fraction: f* = (p * b - (1-p)) / b
            if b > 0:
                kelly_f = (p * b - (1 - p)) / b
            else:
                kelly_f = 0.0
            kelly_f = max(0.0, min(kelly_f, self._kelly_cap))

            target_value = total_equity * kelly_f
            price = prices.get(key, 0)
            qty = int(target_value / price) if price > 0 else 0
            qty = (qty // 100) * 100
            results.append(
                SizingResult(
                    instrument_key=key,
                    weight=kelly_f,
                    target_value=target_value,
                    target_quantity=qty,
                    mode=self._mode,
                )
            )
        return results

    def _fixed(
        self,
        instruments: list[str],
        prices: dict[str, float],
    ) -> list[SizingResult]:
        results = []
        for key in instruments:
            price = prices.get(key, 0)
            qty = int(self._fixed_amount / price) if price > 0 else 0
            qty = (qty // 100) * 100
            results.append(
                SizingResult(
                    instrument_key=key,
                    weight=0.0,
                    target_value=self._fixed_amount,
                    target_quantity=qty,
                    mode=self._mode,
                )
            )
        return results

    def get_config(self) -> dict:
        return {
            "mode": self._mode.value,
            "kelly_cap": self._kelly_cap,
            "fixed_amount": self._fixed_amount,
        }
