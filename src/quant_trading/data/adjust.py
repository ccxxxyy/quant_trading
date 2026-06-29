"""复权处理 - 对K线数据进行前复权/后复权调整，消除除权除息造成的价格跳变。

A股除权除息后，历史价格会出现不连续跳变，导致均线/MACD等指标在除权日全部失真。
复权处理通过调整因子将价格序列修复为连续可比的序列。

支持三种模式：
    - NONE：不做任何调整，使用原始价格
    - FORWARD（前复权）：以最新价格为基准向前调整历史价格（默认推荐）
    - BACKWARD（后复权）：以最早价格为基准向后调整后续价格
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from quant_trading.model.market import Bar

logger = logging.getLogger(__name__)


class AdjustType(Enum):
    """复权类型。"""

    NONE = "none"
    FORWARD = "forward"  # 前复权：以最新收盘价为基准
    BACKWARD = "backward"  # 后复权：以最早收盘价为基准


@dataclass(frozen=True, slots=True)
class AdjustFactor:
    """单次除权除息的调整因子。

    adjust_factor = (收盘价 - 每股现金红利 + 配股价 × 配股比例)
                    / (收盘价 × (1 + 送股比例 + 配股比例))
    简化场景只用 price_factor 表示。
    """

    date: str  # YYYY-MM-DD
    price_factor: Decimal  # 累积复权因子（相邻日收盘价比值）


def detect_adjust_factors(bars: list[Bar], threshold: float = 0.08) -> list[AdjustFactor]:
    """从K线数据自动检测疑似除权除息日。

    原理：相邻两日收盘价变动超过 threshold 但非涨跌停时，
    大概率是除权除息导致的价格跳变而非正常波动。

    Args:
        bars: 按时间排序的K线列表
        threshold: 相邻收盘价变动率阈值，超过此值视为疑似除权

    Returns:
        检测到的调整因子列表
    """
    if len(bars) < 2:
        return []

    factors: list[AdjustFactor] = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        curr_open = bars[i].open
        if prev_close == 0:
            continue

        gap_ratio = float((curr_open - prev_close) / prev_close)
        if abs(gap_ratio) > threshold:
            factor = curr_open / prev_close
            factors.append(
                AdjustFactor(
                    date=bars[i].timestamp.strftime("%Y-%m-%d"),
                    price_factor=factor,
                )
            )
            logger.info(
                f"Detected adjustment at {bars[i].timestamp.date()}: "
                f"prev_close={prev_close}, open={curr_open}, factor={float(factor):.4f}"
            )
    return factors


def compute_cumulative_factors(
    bars: list[Bar],
    factors: list[AdjustFactor],
    adjust_type: AdjustType,
) -> list[Decimal]:
    """计算每根K线对应的累积复权因子。

    前复权：最后一根K线因子=1，向前累乘（历史价格被调低）
    后复权：第一根K线因子=1，向后累乘（后续价格被调高）
    """
    n = len(bars)
    cum = [Decimal(1)] * n

    factor_map: dict[str, Decimal] = {f.date: f.price_factor for f in factors}

    if adjust_type == AdjustType.FORWARD:
        # 从后往前累乘：最新日因子=1
        for i in range(n - 2, -1, -1):
            next_date = bars[i + 1].timestamp.strftime("%Y-%m-%d")
            if next_date in factor_map:
                cum[i] = cum[i + 1] * factor_map[next_date]
            else:
                cum[i] = cum[i + 1]
    elif adjust_type == AdjustType.BACKWARD:
        # 从前往后累乘：最早日因子=1
        for i in range(1, n):
            curr_date = bars[i].timestamp.strftime("%Y-%m-%d")
            if curr_date in factor_map:
                cum[i] = cum[i - 1] / factor_map[curr_date]
            else:
                cum[i] = cum[i - 1]

    return cum


def adjust_bars(
    bars: list[Bar],
    adjust_type: AdjustType = AdjustType.NONE,
    factors: list[AdjustFactor] | None = None,
    auto_detect: bool = True,
    detection_threshold: float = 0.08,
) -> list[Bar]:
    """对K线数据执行复权调整。

    Args:
        bars: 按时间排序的原始K线列表
        adjust_type: 复权类型
        factors: 手动提供的调整因子列表；为 None 且 auto_detect=True 时自动检测
        auto_detect: 是否自动从价格跳变中检测除权事件
        detection_threshold: 自动检测的价格跳变阈值

    Returns:
        复权后的K线列表（新对象，不修改原始数据）
    """
    if adjust_type == AdjustType.NONE or not bars:
        return list(bars)

    if factors is None and auto_detect:
        factors = detect_adjust_factors(bars, threshold=detection_threshold)

    if not factors:
        logger.debug("No adjustment factors found, returning original bars")
        return list(bars)

    cum_factors = compute_cumulative_factors(bars, factors, adjust_type)

    adjusted: list[Bar] = []
    for bar, factor in zip(bars, cum_factors):
        if factor == Decimal(1):
            adjusted.append(bar)
            continue

        adjusted.append(
            Bar(
                instrument_id=bar.instrument_id,
                timestamp=bar.timestamp,
                interval=bar.interval,
                open=_round_price(bar.open * factor),
                high=_round_price(bar.high * factor),
                low=_round_price(bar.low * factor),
                close=_round_price(bar.close * factor),
                volume=bar.volume,
                turnover=bar.turnover,
                open_interest=bar.open_interest,
            )
        )

    adj_count = sum(1 for f in cum_factors if f != Decimal(1))
    logger.info(
        f"Adjusted {adj_count}/{len(bars)} bars using {adjust_type.value} method "
        f"({len(factors)} adjustment events)"
    )
    return adjusted


def _round_price(price: Decimal, ndigits: int = 2) -> Decimal:
    """将价格四舍五入到指定小数位。"""
    return price.quantize(Decimal(10) ** -ndigits)
