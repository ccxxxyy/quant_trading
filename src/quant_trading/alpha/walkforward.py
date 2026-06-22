"""Walk-Forward 滚动验证 - 时间序列交叉验证框架。

Walk-Forward 是量化交易中标准的模型验证方法：
    1. 将历史数据按时间窗口滚动切分为「训练集」和「验证集」
    2. 在训练集上训练模型/优化参数
    3. 在紧接着的验证集上测试表现
    4. 滚动窗口前进，重复上述步骤
    5. 汇总所有验证集的样本外表现

这种方法可以有效防止过拟合，确保策略在未见过的数据上也有效。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from quant_trading.interface.services import run_backtest

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardWindow:
    """单个滚动窗口。"""

    window_id: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_result: dict | None = None
    test_result: dict | None = None

    @property
    def test_return(self) -> float:
        if self.test_result and "metrics" in self.test_result:
            return self.test_result["metrics"]["total_return"]
        return 0.0

    @property
    def test_sharpe(self) -> float:
        if self.test_result and "metrics" in self.test_result:
            return self.test_result["metrics"]["sharpe_ratio"]
        return 0.0


@dataclass
class WalkForwardResult:
    """Walk-Forward 验证汇总结果。"""

    windows: list[WalkForwardWindow]
    strategy_id: str
    symbol: str

    @property
    def num_windows(self) -> int:
        return len(self.windows)

    @property
    def avg_test_return(self) -> float:
        returns = [w.test_return for w in self.windows if w.test_result]
        return sum(returns) / len(returns) if returns else 0.0

    @property
    def avg_test_sharpe(self) -> float:
        sharpes = [w.test_sharpe for w in self.windows if w.test_result]
        return sum(sharpes) / len(sharpes) if sharpes else 0.0

    @property
    def positive_windows(self) -> int:
        return sum(1 for w in self.windows if w.test_return > 0)

    @property
    def consistency_ratio(self) -> float:
        """盈利窗口占比（一致性比率），>50% 说明策略稳定。"""
        total = sum(1 for w in self.windows if w.test_result)
        return self.positive_windows / total if total > 0 else 0.0

    def summary(self) -> dict:
        return {
            "strategy": self.strategy_id,
            "symbol": self.symbol,
            "num_windows": self.num_windows,
            "avg_test_return": self.avg_test_return,
            "avg_test_sharpe": self.avg_test_sharpe,
            "positive_windows": self.positive_windows,
            "consistency_ratio": self.consistency_ratio,
        }


class WalkForwardValidator:
    """Walk-Forward 滚动验证器。

    参数：
        strategy_id: 策略ID
        symbol: 交易标的
        train_days: 训练窗口天数（默认180天≈6个月）
        test_days: 验证窗口天数（默认30天≈1个月）
        step_days: 滚动步长（默认等于 test_days）
        capital: 初始资金
        params: 策略参数

    使用示例：
        validator = WalkForwardValidator(
            strategy_id="dual_ma",
            symbol="600519.SSE",
            train_days=180,
            test_days=30,
        )
        result = validator.run(
            start=datetime(2022, 1, 1),
            end=datetime(2024, 1, 1),
        )
        print(result.summary())
    """

    def __init__(
        self,
        strategy_id: str,
        symbol: str,
        train_days: int = 180,
        test_days: int = 30,
        step_days: int | None = None,
        capital: float = 1_000_000.0,
        params: dict[str, Any] | None = None,
    ) -> None:
        self._strategy_id = strategy_id
        self._symbol = symbol
        self._train_days = train_days
        self._test_days = test_days
        self._step_days = step_days or test_days
        self._capital = capital
        self._params = params or {}

    def _generate_windows(self, start: datetime, end: datetime) -> list[WalkForwardWindow]:
        """生成滚动窗口列表。"""
        from datetime import timedelta

        windows = []
        current = start
        wid = 0

        while True:
            train_start = current
            train_end = current + timedelta(days=self._train_days)
            test_start = train_end
            test_end = test_start + timedelta(days=self._test_days)

            if test_end > end:
                break

            windows.append(
                WalkForwardWindow(
                    window_id=wid,
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=test_end,
                )
            )

            current += timedelta(days=self._step_days)
            wid += 1

        return windows

    def run(
        self,
        start: datetime,
        end: datetime,
        use_demo_data: bool = True,
    ) -> WalkForwardResult:
        """执行 Walk-Forward 验证。"""
        windows = self._generate_windows(start, end)
        logger.info(
            f"Walk-Forward: {len(windows)} windows, "
            f"train={self._train_days}d test={self._test_days}d "
            f"step={self._step_days}d"
        )

        for w in windows:
            # 训练窗口回测
            try:
                w.train_result = run_backtest(
                    strategy_id=self._strategy_id,
                    symbol=self._symbol,
                    start=w.train_start,
                    end=w.train_end,
                    capital=self._capital,
                    params=self._params,
                    use_demo_data=use_demo_data,
                )
            except Exception as e:
                logger.warning(f"  Window {w.window_id} train failed: {e}")

            # 验证窗口回测（样本外）
            try:
                w.test_result = run_backtest(
                    strategy_id=self._strategy_id,
                    symbol=self._symbol,
                    start=w.test_start,
                    end=w.test_end,
                    capital=self._capital,
                    params=self._params,
                    use_demo_data=use_demo_data,
                )
                logger.info(
                    f"  Window {w.window_id}: "
                    f"train_ret={w.train_result['metrics']['total_return'] * 100:+.2f}% "
                    f"test_ret={w.test_return * 100:+.2f}%"
                    if w.train_result
                    else f"  Window {w.window_id}: test_ret={w.test_return * 100:+.2f}%"
                )
            except Exception as e:
                logger.warning(f"  Window {w.window_id} test failed: {e}")

        return WalkForwardResult(
            windows=windows,
            strategy_id=self._strategy_id,
            symbol=self._symbol,
        )

    @staticmethod
    def format_report(result: WalkForwardResult) -> str:
        """格式化 Walk-Forward 报告。"""
        lines = [
            "=" * 70,
            "Walk-Forward 滚动验证报告",
            "=" * 70,
            f"策略: {result.strategy_id}",
            f"标的: {result.symbol}",
            f"窗口数: {result.num_windows}",
            "",
            f"{'窗口':>4s}  {'训练区间':>25s}  {'测试区间':>25s}  {'测试收益':>10s}",
            "-" * 70,
        ]
        for w in result.windows:
            train_range = f"{w.train_start:%Y-%m-%d} ~ {w.train_end:%Y-%m-%d}"
            test_range = f"{w.test_start:%Y-%m-%d} ~ {w.test_end:%Y-%m-%d}"
            ret_str = f"{w.test_return * 100:+.2f}%" if w.test_result else "N/A"
            lines.append(f"{w.window_id:4d}  {train_range:>25s}  {test_range:>25s}  {ret_str:>10s}")

        lines.extend(
            [
                "-" * 70,
                f"平均测试收益: {result.avg_test_return * 100:+.2f}%",
                f"平均测试 Sharpe: {result.avg_test_sharpe:.3f}",
                f"盈利窗口: {result.positive_windows}/{result.num_windows}",
                f"一致性比率: {result.consistency_ratio:.1%}",
                "=" * 70,
            ]
        )
        return "\n".join(lines)
