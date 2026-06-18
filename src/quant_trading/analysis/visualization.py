"""图表可视化工具 - 用于策略绩效分析的图表绘制。"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def plot_equity_curve(
    equity_curve: list[tuple[datetime, float]],
    title: str = "权益曲线",
    show: bool = True,
) -> Any:
    """绘制权益曲线图（使用 Plotly）。"""
    try:
        import plotly.graph_objects as go
    except ImportError:
        raise ImportError("plotly required: pip install quant-trading[viz]")

    timestamps, values = zip(*equity_curve)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=list(timestamps), y=list(values), mode="lines", name="权益"))
    fig.update_layout(title=title, xaxis_title="日期", yaxis_title="权益")

    if show:
        fig.show()
    return fig


def plot_drawdown(
    equity_curve: list[tuple[datetime, float]],
    title: str = "回撤图",
    show: bool = True,
) -> Any:
    """绘制回撤曲线图。"""
    try:
        import plotly.graph_objects as go
    except ImportError:
        raise ImportError("plotly required: pip install quant-trading[viz]")

    timestamps, values = zip(*equity_curve)

    # 计算回撤序列
    peak = values[0]
    drawdowns = []
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        drawdowns.append(-dd)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=list(timestamps),
            y=drawdowns,
            fill="tozeroy",
            mode="lines",
            name="回撤 %",
        )
    )
    fig.update_layout(title=title, xaxis_title="日期", yaxis_title="回撤 (%)")

    if show:
        fig.show()
    return fig


def plot_monthly_returns(
    equity_curve: list[tuple[datetime, float]],
    title: str = "月度收益热力图",
    show: bool = True,
) -> Any:
    """绘制月度收益热力图。"""
    try:
        import plotly.graph_objects as go
    except ImportError:
        raise ImportError("plotly required: pip install quant-trading[viz]")

    import polars as pl

    timestamps, values = zip(*equity_curve)
    df = pl.DataFrame({"timestamp": list(timestamps), "equity": list(values)})
    df = df.with_columns(pl.col("equity").pct_change().alias("return"))
    df = df.with_columns(
        [
            pl.col("timestamp").dt.year().alias("year"),
            pl.col("timestamp").dt.month().alias("month"),
        ]
    )

    monthly = (
        df.group_by(["year", "month"])
        .agg(((1 + pl.col("return")).product() - 1).alias("monthly_return"))
        .sort(["year", "month"])
    )

    years = sorted(monthly["year"].unique().to_list())
    months = list(range(1, 13))
    month_names = [
        "1月",
        "2月",
        "3月",
        "4月",
        "5月",
        "6月",
        "7月",
        "8月",
        "9月",
        "10月",
        "11月",
        "12月",
    ]

    z = []
    for year in years:
        row = []
        for month in months:
            filtered = monthly.filter((pl.col("year") == year) & (pl.col("month") == month))
            if len(filtered) > 0:
                row.append(filtered["monthly_return"][0] * 100)
            else:
                row.append(None)
        z.append(row)

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=month_names,
            y=[str(y) for y in years],
            colorscale="RdYlGn",
            zmid=0,
        )
    )
    fig.update_layout(title=title)

    if show:
        fig.show()
    return fig
