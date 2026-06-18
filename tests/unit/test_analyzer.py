"""回测分析器的单元测试。"""

from datetime import datetime, timedelta

from quant_trading.backtest.analyzer import BacktestAnalyzer, TradeRecord


class TestBacktestAnalyzer:
    def test_compute_basic_metrics(self):
        analyzer = BacktestAnalyzer()
        base = datetime(2023, 1, 1)
        equity_curve = [(base + timedelta(days=i), 100_000 + i * 100) for i in range(100)]
        metrics = analyzer.compute_metrics(equity_curve, initial_capital=100_000)
        assert metrics.total_return > 0
        assert metrics.annual_return > 0
        assert metrics.max_drawdown >= 0

    def test_with_trades(self):
        analyzer = BacktestAnalyzer()
        base = datetime(2023, 1, 1)
        equity_curve = [(base + timedelta(days=i), 100_000 + i * 50) for i in range(50)]
        trades = [
            TradeRecord(
                instrument_id="TEST.SSE",
                side="long",
                entry_time=base,
                exit_time=base + timedelta(days=10),
                entry_price=100.0,
                exit_price=110.0,
                quantity=100,
                pnl=1000.0,
                commission=30.0,
                return_pct=0.01,
            ),
            TradeRecord(
                instrument_id="TEST.SSE",
                side="long",
                entry_time=base + timedelta(days=15),
                exit_time=base + timedelta(days=25),
                entry_price=105.0,
                exit_price=100.0,
                quantity=100,
                pnl=-500.0,
                commission=30.0,
                return_pct=-0.005,
            ),
        ]
        metrics = analyzer.compute_metrics(equity_curve, trades, initial_capital=100_000)
        assert metrics.total_trades == 2
        assert metrics.winning_trades == 1
        assert metrics.losing_trades == 1
        assert metrics.win_rate == 0.5
        assert metrics.profit_factor > 0

    def test_format_report(self):
        analyzer = BacktestAnalyzer()
        base = datetime(2023, 1, 1)
        equity_curve = [(base + timedelta(days=i), 100_000 + i * 100) for i in range(50)]
        metrics = analyzer.compute_metrics(equity_curve, initial_capital=100_000)
        report = analyzer.format_report(metrics)
        assert "回测绩效报告" in report
        assert "夏普比率" in report
        assert "最大回撤" in report

    def test_empty_curve(self):
        analyzer = BacktestAnalyzer()
        metrics = analyzer.compute_metrics([], initial_capital=100_000)
        assert metrics.total_return == 0.0
        assert metrics.total_trades == 0
