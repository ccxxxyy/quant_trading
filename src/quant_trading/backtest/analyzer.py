"""绩效分析 - 策略回测结果的指标计算。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import polars as pl


@dataclass
class PerformanceMetrics:
    """回测的综合绩效指标。"""

    total_return: float = 0.0  # 总收益率
    annual_return: float = 0.0  # 年化收益率
    sharpe_ratio: float = 0.0  # 夏普比率（风险调整后收益）
    sortino_ratio: float = 0.0  # 索提诺比率（只考虑下行风险）
    max_drawdown: float = 0.0  # 最大回撤
    max_drawdown_duration_days: int = 0  # 最大回撤持续天数
    calmar_ratio: float = 0.0  # 卡尔马比率（年化收益/最大回撤）
    win_rate: float = 0.0  # 胜率
    profit_factor: float = 0.0  # 盈亏比（总盈利/总亏损）
    total_trades: int = 0  # 总交易笔数
    winning_trades: int = 0  # 盈利笔数
    losing_trades: int = 0  # 亏损笔数
    avg_win: float = 0.0  # 平均盈利金额
    avg_loss: float = 0.0  # 平均亏损金额
    avg_trade_duration_days: float = 0.0  # 平均持仓天数
    volatility: float = 0.0  # 年化波动率
    start_date: datetime | None = None  # 回测起始日期
    end_date: datetime | None = None  # 回测结束日期
    initial_capital: float = 0.0  # 初始资金
    final_capital: float = 0.0  # 最终资金


@dataclass
class TradeRecord:
    """一笔完整交易的记录（从开仓到平仓为一笔）。"""

    instrument_id: str  # 标的代码
    side: str  # 方向（long=做多, short=做空）
    entry_time: datetime  # 开仓时间
    exit_time: datetime  # 平仓时间
    entry_price: float  # 开仓价格
    exit_price: float  # 平仓价格
    quantity: int  # 数量
    pnl: float  # 盈亏金额
    commission: float  # 手续费
    return_pct: float  # 收益率


class BacktestAnalyzer:
    """回测结果分析器，计算各项绩效指标。"""

    def __init__(self, risk_free_rate: float = 0.03, trading_days: int = 252) -> None:
        self._risk_free_rate = risk_free_rate  # 无风险利率（默认3%，通常用国债收益率）
        self._trading_days = trading_days  # 年交易日数（A股约为252天）

    def compute_metrics(
        self,
        equity_curve: list[tuple[datetime, float]],
        trades: list[TradeRecord] | None = None,
        initial_capital: float = 1_000_000.0,
    ) -> PerformanceMetrics:
        """根据权益曲线和交易记录计算完整的绩效指标。"""
        if len(equity_curve) < 2:
            return PerformanceMetrics(initial_capital=initial_capital)

        timestamps, values = zip(*equity_curve)
        df = pl.DataFrame({"timestamp": list(timestamps), "equity": list(values)})

        returns = df.select(pl.col("equity").pct_change().alias("return")).drop_nulls()
        returns_list = returns["return"].to_list()

        metrics = PerformanceMetrics()
        metrics.initial_capital = initial_capital
        metrics.final_capital = values[-1]
        metrics.start_date = timestamps[0]
        metrics.end_date = timestamps[-1]

        # 总收益率和年化收益率
        metrics.total_return = (values[-1] - initial_capital) / initial_capital
        days = (timestamps[-1] - timestamps[0]).days
        if days > 0:
            metrics.annual_return = (1 + metrics.total_return) ** (365.0 / days) - 1

        # 波动率
        if returns_list:
            avg_ret = sum(returns_list) / len(returns_list)
            variance = sum((r - avg_ret) ** 2 for r in returns_list) / max(len(returns_list) - 1, 1)
            daily_vol = math.sqrt(variance)
            metrics.volatility = daily_vol * math.sqrt(self._trading_days)

            # 夏普比率
            daily_rf = self._risk_free_rate / self._trading_days
            excess_returns = [r - daily_rf for r in returns_list]
            avg_excess = sum(excess_returns) / len(excess_returns)
            if daily_vol > 0:
                metrics.sharpe_ratio = (avg_excess / daily_vol) * math.sqrt(self._trading_days)

            # 索提诺比率
            downside_returns = [r for r in excess_returns if r < 0]
            if downside_returns:
                downside_var = sum(r**2 for r in downside_returns) / len(downside_returns)
                downside_vol = math.sqrt(downside_var)
                if downside_vol > 0:
                    metrics.sortino_ratio = (avg_excess / downside_vol) * math.sqrt(
                        self._trading_days
                    )

        # 最大回撤
        peak = values[0]
        max_dd = 0.0
        max_dd_duration = 0
        current_dd_start = timestamps[0]

        for i, v in enumerate(values):
            if v > peak:
                duration = (timestamps[i] - current_dd_start).days
                max_dd_duration = max(max_dd_duration, duration)
                peak = v
                current_dd_start = timestamps[i]
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd

        metrics.max_drawdown = max_dd
        metrics.max_drawdown_duration_days = max_dd_duration

        # 卡尔马比率
        if max_dd > 0:
            metrics.calmar_ratio = metrics.annual_return / max_dd

        # 交易统计
        if trades:
            metrics.total_trades = len(trades)
            winning = [t for t in trades if t.pnl > 0]
            losing = [t for t in trades if t.pnl <= 0]
            metrics.winning_trades = len(winning)
            metrics.losing_trades = len(losing)

            if metrics.total_trades > 0:
                metrics.win_rate = len(winning) / metrics.total_trades

            if winning:
                metrics.avg_win = sum(t.pnl for t in winning) / len(winning)
            if losing:
                metrics.avg_loss = sum(t.pnl for t in losing) / len(losing)

            total_profit = sum(t.pnl for t in winning)
            total_loss = abs(sum(t.pnl for t in losing))
            if total_loss > 0:
                metrics.profit_factor = total_profit / total_loss

            durations = [(t.exit_time - t.entry_time).days for t in trades]
            if durations:
                metrics.avg_trade_duration_days = sum(durations) / len(durations)

        return metrics

    def format_report(self, metrics: PerformanceMetrics) -> str:
        """将绩效指标格式化为可读的文本报告。"""
        lines = [
            "=" * 60,
            "回测绩效报告",
            "=" * 60,
            f"回测区间:      {metrics.start_date} -> {metrics.end_date}",
            f"初始资金:      {metrics.initial_capital:,.2f}",
            f"最终资金:      {metrics.final_capital:,.2f}",
            "-" * 60,
            f"总收益率:      {metrics.total_return * 100:.2f}%",
            f"年化收益率:    {metrics.annual_return * 100:.2f}%",
            f"年化波动率:    {metrics.volatility * 100:.2f}%",
            f"夏普比率:      {metrics.sharpe_ratio:.3f}",
            f"索提诺比率:    {metrics.sortino_ratio:.3f}",
            f"卡尔马比率:    {metrics.calmar_ratio:.3f}",
            f"最大回撤:      {metrics.max_drawdown * 100:.2f}%",
            f"最大回撤持续:  {metrics.max_drawdown_duration_days} 天",
            "-" * 60,
            f"总交易笔数:    {metrics.total_trades}",
            f"胜率:          {metrics.win_rate * 100:.1f}%",
            f"盈亏比:        {metrics.profit_factor:.2f}",
            f"平均盈利:      {metrics.avg_win:,.2f}",
            f"平均亏损:      {metrics.avg_loss:,.2f}",
            f"平均持仓天数:  {metrics.avg_trade_duration_days:.1f} 天",
            "=" * 60,
        ]
        return "\n".join(lines)
