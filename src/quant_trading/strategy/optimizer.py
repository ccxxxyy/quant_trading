"""策略参数优化工具 - 网格搜索与结果排序。"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from quant_trading.interface.services import run_backtest

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """单次参数组合的回测结果。"""

    params: dict[str, Any]
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    calmar_ratio: float
    total_trades: int
    win_rate: float
    final_capital: float

    def __repr__(self) -> str:
        params_str = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return (
            f"OptResult({params_str}) "
            f"return={self.total_return * 100:+.2f}% "
            f"sharpe={self.sharpe_ratio:.3f} "
            f"maxdd={self.max_drawdown * 100:.2f}%"
        )


class StrategyOptimizer:
    """策略参数网格搜索优化器。

    在给定的参数空间中穷举所有组合，分别运行回测，
    最后按指定指标排序找出最优参数。

    使用示例：
        optimizer = StrategyOptimizer(
            strategy_id="dual_ma",
            symbol="600519.SSE",
            start=datetime(2023, 1, 1),
            capital=1_000_000,
        )
        results = optimizer.optimize({
            "fast_period": [5, 10, 15, 20],
            "slow_period": [20, 30, 40, 60],
        })
        best = optimizer.best(results, metric="sharpe_ratio")
    """

    def __init__(
        self,
        strategy_id: str,
        symbol: str,
        start: datetime,
        end: datetime | None = None,
        capital: float = 1_000_000.0,
        use_demo_data: bool = True,
    ) -> None:
        self._strategy_id = strategy_id
        self._symbol = symbol
        self._start = start
        self._end = end
        self._capital = capital
        self._use_demo_data = use_demo_data

    def optimize(
        self,
        param_grid: dict[str, list[Any]],
        fixed_params: dict[str, Any] | None = None,
    ) -> list[OptimizationResult]:
        """网格搜索：遍历所有参数组合并运行回测。

        参数：
            param_grid: 要搜索的参数及其候选值，
                        如 {"fast_period": [5, 10], "slow_period": [20, 30]}
            fixed_params: 固定不变的参数

        返回：
            按 Sharpe 降序排列的结果列表
        """
        fixed = fixed_params or {}
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        combinations = list(itertools.product(*values))

        total = len(combinations)
        logger.info(f"Optimizer: {total} combinations to test for {self._strategy_id}")

        results: list[OptimizationResult] = []

        for i, combo in enumerate(combinations, 1):
            params = {**fixed, **dict(zip(keys, combo))}

            # 跳过无意义的参数组合（如快线周期 > 慢线周期）
            if "fast_period" in params and "slow_period" in params:
                if params["fast_period"] >= params["slow_period"]:
                    continue

            try:
                result = run_backtest(
                    strategy_id=self._strategy_id,
                    symbol=self._symbol,
                    start=self._start,
                    end=self._end,
                    capital=self._capital,
                    params=params,
                    use_demo_data=self._use_demo_data,
                )
                m = result["metrics"]
                opt_result = OptimizationResult(
                    params=params,
                    total_return=m["total_return"],
                    sharpe_ratio=m["sharpe_ratio"],
                    max_drawdown=m["max_drawdown"],
                    calmar_ratio=m["calmar_ratio"],
                    total_trades=m["total_trades"],
                    win_rate=m["win_rate"],
                    final_capital=m["final_capital"],
                )
                results.append(opt_result)
                logger.debug(f"  [{i}/{total}] {opt_result}")
            except Exception as e:
                logger.warning(f"  [{i}/{total}] params={params} failed: {e}")

        results.sort(key=lambda r: r.sharpe_ratio, reverse=True)
        logger.info(f"Optimizer: completed {len(results)} valid results")
        return results

    @staticmethod
    def best(
        results: list[OptimizationResult],
        metric: str = "sharpe_ratio",
        ascending: bool = False,
    ) -> OptimizationResult | None:
        """按指定指标返回最优结果。"""
        if not results:
            return None
        return sorted(
            results,
            key=lambda r: getattr(r, metric, 0),
            reverse=not ascending,
        )[0]

    @staticmethod
    def top_n(
        results: list[OptimizationResult],
        n: int = 10,
        metric: str = "sharpe_ratio",
    ) -> list[OptimizationResult]:
        """返回前 N 个最优结果。"""
        return sorted(
            results,
            key=lambda r: getattr(r, metric, 0),
            reverse=True,
        )[:n]

    @staticmethod
    def format_table(results: list[OptimizationResult], top: int = 20) -> str:
        """格式化输出结果表格。"""
        lines = [
            f"{'#':>3s}  {'收益率':>8s}  {'Sharpe':>8s}  {'最大回撤':>8s}  "
            f"{'Calmar':>8s}  {'交易数':>6s}  {'胜率':>6s}  参数",
            "-" * 90,
        ]
        for i, r in enumerate(results[:top], 1):
            params_str = ", ".join(f"{k}={v}" for k, v in r.params.items())
            lines.append(
                f"{i:3d}  {r.total_return * 100:+7.2f}%  {r.sharpe_ratio:8.3f}  "
                f"{r.max_drawdown * 100:7.2f}%  {r.calmar_ratio:8.3f}  "
                f"{r.total_trades:6d}  {r.win_rate * 100:5.1f}%  {params_str}"
            )
        return "\n".join(lines)
