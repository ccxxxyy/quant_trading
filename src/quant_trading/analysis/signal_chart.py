"""策略信号可视化 - K线图叠加买卖信号标记。"""

from __future__ import annotations

from typing import Any

from quant_trading.model.market import Bar


def plot_signals(
    bars: list[Bar],
    trades: list[dict[str, Any]],
    title: str = "策略信号图",
    show: bool = True,
) -> Any:
    """绘制K线图并叠加买卖信号。

    参数：
        bars: K线数据列表
        trades: 交易记录列表（来自回测结果的 trades 字段）
        title: 图表标题
        show: 是否立即显示

    返回：
        plotly Figure 对象
    """
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        raise ImportError("plotly is required: uv sync --extra viz")

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=["K线与信号", "成交量", "持仓盈亏"],
    )

    dates = [b.timestamp for b in bars]
    opens = [float(b.open) for b in bars]
    highs = [float(b.high) for b in bars]
    lows = [float(b.low) for b in bars]
    closes = [float(b.close) for b in bars]
    volumes = [b.volume for b in bars]

    # K线图（蜡烛图）
    fig.add_trace(
        go.Candlestick(
            x=dates,
            open=opens,
            high=highs,
            low=lows,
            close=closes,
            name="K线",
            increasing_line_color="#22c55e",
            decreasing_line_color="#ef4444",
        ),
        row=1,
        col=1,
    )

    # 买入信号（绿色三角形向上）
    buy_times = []
    buy_prices = []
    for t in trades:
        if t.get("side") in ("long", "buy"):
            buy_times.append(t.get("entry_time", ""))
            buy_prices.append(t.get("entry_price", 0))

    if buy_times:
        fig.add_trace(
            go.Scatter(
                x=buy_times,
                y=buy_prices,
                mode="markers",
                marker=dict(
                    symbol="triangle-up",
                    size=14,
                    color="#22c55e",
                    line=dict(width=1, color="white"),
                ),
                name="买入",
            ),
            row=1,
            col=1,
        )

    # 卖出信号（红色三角形向下）
    sell_times = []
    sell_prices = []
    for t in trades:
        exit_time = t.get("exit_time", "")
        exit_price = t.get("exit_price", 0)
        if exit_time and exit_price:
            sell_times.append(exit_time)
            sell_prices.append(exit_price)

    if sell_times:
        fig.add_trace(
            go.Scatter(
                x=sell_times,
                y=sell_prices,
                mode="markers",
                marker=dict(
                    symbol="triangle-down",
                    size=14,
                    color="#ef4444",
                    line=dict(width=1, color="white"),
                ),
                name="卖出",
            ),
            row=1,
            col=1,
        )

    # 成交量柱状图
    colors = ["#22c55e" if c >= o else "#ef4444" for o, c in zip(opens, closes)]
    fig.add_trace(
        go.Bar(x=dates, y=volumes, marker_color=colors, name="成交量", showlegend=False),
        row=2,
        col=1,
    )

    # 逐笔盈亏散点图
    trade_exits = []
    trade_pnls = []
    trade_colors = []
    for t in trades:
        if t.get("exit_time") and t.get("pnl") is not None:
            trade_exits.append(t["exit_time"])
            trade_pnls.append(t["pnl"])
            trade_colors.append("#22c55e" if t["pnl"] >= 0 else "#ef4444")

    if trade_exits:
        fig.add_trace(
            go.Bar(
                x=trade_exits,
                y=trade_pnls,
                marker_color=trade_colors,
                name="逐笔盈亏",
            ),
            row=3,
            col=1,
        )

    fig.update_layout(
        title=title,
        template="plotly_dark",
        height=900,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_rangeslider_visible=False,
        paper_bgcolor="#0b0f14",
        plot_bgcolor="#121820",
    )

    fig.update_xaxes(gridcolor="#2a3548")
    fig.update_yaxes(gridcolor="#2a3548")

    if show:
        fig.show()

    return fig


def plot_equity_with_drawdown(
    equity_curve: list[dict],
    title: str = "权益曲线与回撤",
    show: bool = True,
) -> Any:
    """绘制权益曲线与对应的回撤图。"""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        raise ImportError("plotly is required: uv sync --extra viz")

    timestamps = [p["timestamp"] for p in equity_curve]
    equities = [p["equity"] for p in equity_curve]

    # 计算回撤
    peak = equities[0]
    drawdowns = []
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (eq - peak) / peak * 100 if peak != 0 else 0
        drawdowns.append(dd)

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.7, 0.3],
        subplot_titles=["权益曲线", "回撤 (%)"],
    )

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=equities,
            mode="lines",
            name="权益",
            line=dict(color="#3b82f6", width=2),
            fill="tozeroy",
            fillcolor="rgba(59, 130, 246, 0.08)",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=drawdowns,
            mode="lines",
            name="回撤",
            line=dict(color="#ef4444", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(239, 68, 68, 0.12)",
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=title,
        template="plotly_dark",
        height=600,
        paper_bgcolor="#0b0f14",
        plot_bgcolor="#121820",
    )

    if show:
        fig.show()

    return fig
