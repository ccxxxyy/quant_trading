"""绩效指标计算函数集。"""

from __future__ import annotations

import math


def sharpe_ratio(returns: list[float], risk_free_rate: float = 0.03, periods: int = 252) -> float:
    """计算年化夏普比率（衡量风险调整后的收益）。"""
    if not returns or len(returns) < 2:
        return 0.0
    daily_rf = risk_free_rate / periods
    excess = [r - daily_rf for r in returns]
    avg = sum(excess) / len(excess)
    std = math.sqrt(sum((r - avg) ** 2 for r in excess) / (len(excess) - 1))
    if std == 0:
        return 0.0
    return (avg / std) * math.sqrt(periods)


def sortino_ratio(returns: list[float], risk_free_rate: float = 0.03, periods: int = 252) -> float:
    """计算年化索提诺比率（只考虑下行风险的版本）。"""
    if not returns or len(returns) < 2:
        return 0.0
    daily_rf = risk_free_rate / periods
    excess = [r - daily_rf for r in returns]
    avg = sum(excess) / len(excess)
    downside = [r for r in excess if r < 0]
    if not downside:
        return float("inf") if avg > 0 else 0.0
    downside_std = math.sqrt(sum(r**2 for r in downside) / len(downside))
    if downside_std == 0:
        return 0.0
    return (avg / downside_std) * math.sqrt(periods)


def max_drawdown(equity_curve: list[float]) -> tuple[float, int, int]:
    """计算最大回撤及其起止位置。

    返回：(最大回撤百分比, 峰值索引, 谷值索引)
    """
    if not equity_curve:
        return 0.0, 0, 0

    peak = equity_curve[0]
    peak_idx = 0
    max_dd = 0.0
    max_dd_peak_idx = 0
    max_dd_trough_idx = 0

    for i, value in enumerate(equity_curve):
        if value > peak:
            peak = value
            peak_idx = i
        dd = (peak - value) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
            max_dd_peak_idx = peak_idx
            max_dd_trough_idx = i

    return max_dd, max_dd_peak_idx, max_dd_trough_idx


def calmar_ratio(annual_return: float, max_dd: float) -> float:
    """卡尔马比率 = 年化收益率 / 最大回撤。"""
    if max_dd == 0:
        return 0.0
    return annual_return / max_dd


def win_rate(pnl_list: list[float]) -> float:
    """胜率 = 盈利笔数 / 总交易笔数。"""
    if not pnl_list:
        return 0.0
    wins = sum(1 for p in pnl_list if p > 0)
    return wins / len(pnl_list)


def profit_factor(pnl_list: list[float]) -> float:
    """盈亏比 = 总盈利 / 总亏损。"""
    gross_profit = sum(p for p in pnl_list if p > 0)
    gross_loss = abs(sum(p for p in pnl_list if p < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def information_ratio(
    returns: list[float], benchmark_returns: list[float], periods: int = 252
) -> float:
    """信息比率 - 衡量策略相对于基准的超额收益稳定性。"""
    if len(returns) != len(benchmark_returns) or len(returns) < 2:
        return 0.0
    active = [r - b for r, b in zip(returns, benchmark_returns)]
    avg = sum(active) / len(active)
    std = math.sqrt(sum((r - avg) ** 2 for r in active) / (len(active) - 1))
    if std == 0:
        return 0.0
    return (avg / std) * math.sqrt(periods)
