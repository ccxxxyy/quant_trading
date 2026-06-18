"""回测演示脚本 - 对比所有内置策略的表现。"""

from datetime import datetime
from quant_trading.interface.services import run_backtest

strategies = ["dual_ma", "rsi", "macd", "turtle", "bollinger"]

print("=" * 90)
print("量化交易系统 - 策略回测对比（演示数据 250 日）")
print("=" * 90)
print(f"{'策略':12s} | {'总收益率':>10s} | {'夏普比率':>8s} | {'最大回撤':>8s} | {'交易次数':>8s} | {'胜率':>6s}")
print("-" * 90)

for sid in strategies:
    result = run_backtest(
        strategy_id=sid,
        symbol="600519.SSE",
        start=datetime(2023, 1, 1),
        capital=1_000_000.0,
        use_demo_data=True,
    )
    m = result["metrics"]
    total_ret = f"{m['total_return']*100:+.2f}%"
    sharpe = f"{m['sharpe_ratio']:.3f}"
    max_dd = f"{m['max_drawdown']*100:.2f}%"
    trades = f"{m['total_trades']}"
    win = f"{m['win_rate']*100:.1f}%"
    print(f"{sid:12s} | {total_ret:>10s} | {sharpe:>8s} | {max_dd:>8s} | {trades:>8s} | {win:>6s}")

print("=" * 90)
