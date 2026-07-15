"""回测完整流程的集成测试。"""

from datetime import datetime

from quant_trading.interface.services import run_backtest


class TestBacktestIntegration:
    def test_full_backtest_with_demo_data(self):
        """端到端测试：使用演示数据运行双均线策略回测。"""
        result = run_backtest(
            strategy_id="dual_ma",
            symbol="600519.SSE",
            start=datetime(2023, 1, 1),
            end=datetime(2023, 12, 31),
            capital=1_000_000.0,
            use_demo_data=True,
        )
        assert "metrics" in result
        assert "equity_curve" in result
        assert "trades" in result
        assert "report" in result
        assert result["bar_count"] >= 240
        assert result["used_demo_data"] is True
        assert result["metrics"]["initial_capital"] == 1_000_000.0

    def test_rsi_strategy_backtest(self):
        """使用 RSI 策略运行回测。"""
        result = run_backtest(
            strategy_id="rsi",
            symbol="TEST.SSE",
            start=datetime(2023, 1, 1),
            capital=500_000.0,
            use_demo_data=True,
        )
        assert result["metrics"]["initial_capital"] == 500_000.0
        assert len(result["equity_curve"]) > 0

    def test_macd_strategy_backtest(self):
        """使用 MACD 策略运行回测。"""
        result = run_backtest(
            strategy_id="macd",
            symbol="TEST.SSE",
            start=datetime(2023, 1, 1),
            capital=500_000.0,
            use_demo_data=True,
        )
        assert result["metrics"]["initial_capital"] == 500_000.0

    def test_turtle_strategy_backtest(self):
        """使用海龟策略运行回测。"""
        result = run_backtest(
            strategy_id="turtle",
            symbol="TEST.SSE",
            start=datetime(2023, 1, 1),
            capital=500_000.0,
            use_demo_data=True,
        )
        assert result["metrics"]["initial_capital"] == 500_000.0

    def test_bollinger_strategy_backtest(self):
        """使用布林带策略运行回测。"""
        result = run_backtest(
            strategy_id="bollinger",
            symbol="TEST.SSE",
            start=datetime(2023, 1, 1),
            capital=500_000.0,
            use_demo_data=True,
        )
        assert result["metrics"]["initial_capital"] == 500_000.0
