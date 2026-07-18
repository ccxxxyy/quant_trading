"""FastAPI Web 应用 - REST API 和仪表盘服务器。"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from quant_trading import __version__
from quant_trading.interface.services import (
    BUILTIN_STRATEGIES,
    fetch_market_data,
    get_bar_preview,
    get_system_info,
    list_instruments,
    load_strategy,
    run_backtest,
)
from quant_trading.interface.web.schemas import (
    BacktestRequest,
    FetchDataRequest,
    HealthResponse,
    OptimizeRequest,
    PaperConfigRequest,
    PaperOrderRequest,
)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Quant Trading System",
    description="个人量化交易系统 Web API",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ── Multi-account paper gateway management ─────────────────
_paper_gateways: dict[str, Any] = {}
_active_account: str = "default"


def _get_paper_gateway(
    capital: float = 100_000.0,
    commission: float = 0.0003,
    slippage: float = 0.0001,
    reset: bool = False,
    account_name: str | None = None,
) -> Any:
    global _active_account
    name = account_name or _active_account
    if name not in _paper_gateways or reset:
        from quant_trading.gateway.paper import PaperTradingGateway

        _paper_gateways[name] = PaperTradingGateway(
            initial_capital=capital,
            commission_rate=commission,
            slippage_rate=slippage,
            account_name=name,
        )
    return _paper_gateways[name]


def _get_latest_price(symbol: str) -> tuple[Decimal, bool]:
    """从本地存储的K线数据中获取标的最新收盘价。

    Returns:
        (price, from_local_data) — from_local_data=False 表示使用了默认价。
    """
    from quant_trading.core.config import Settings
    from quant_trading.data.store import DataStore
    from quant_trading.model.instrument import InstrumentId
    from quant_trading.model.market import BarInterval

    try:
        settings = Settings.load()
        store = DataStore(settings.data.parquet_dir)
        instrument_id = InstrumentId.from_str(symbol)
        bars = store.load_bars(instrument_id, BarInterval.DAILY)
        if bars:
            return bars[-1].close, True
    except Exception:
        pass
    # Fallback: use gateway cache or default
    gw = _paper_gateways.get(_active_account)
    if gw:
        cached = gw._latest_prices.get(symbol)
        if cached:
            return cached, True
    return Decimal("100.00"), False


# ── Static pages ───────────────────────────────────────────


@app.get("/")
async def index():
    """提供仪表盘单页应用。"""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(
            index_file,
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )
    return {"message": "Quant Trading API", "docs": "/docs"}


# ── Core APIs ──────────────────────────────────────────────


@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok", version=__version__)


@app.get("/api/system/info")
async def system_info():
    return get_system_info()


@app.get("/api/strategies")
async def strategies():
    return {
        "strategies": [
            {"id": k, **{key: v for key, v in meta.items() if key != "class"}}
            for k, meta in BUILTIN_STRATEGIES.items()
        ]
    }


@app.post("/api/arbitrage/scan")
async def arbitrage_scan(symbols: str = "600519.SSE,000858.SSE"):
    """扫描标的配对：相关性矩阵 + 协整检验 + 对冲比估计。"""
    import numpy as np

    from quant_trading.core.config import Settings
    from quant_trading.data.store import DataStore
    from quant_trading.interface.services import generate_demo_bars
    from quant_trading.model.instrument import InstrumentId
    from quant_trading.model.market import BarInterval

    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if len(sym_list) < 2:
        raise HTTPException(status_code=400, detail="至少需要 2 个标的")

    settings = Settings.load()
    store = DataStore(settings.data.parquet_dir)

    close_data: dict[str, list[float]] = {}
    for sym in sym_list:
        iid = InstrumentId.from_str(sym)
        bars = store.load_bars(iid, BarInterval.DAILY)
        if not bars:
            bars = generate_demo_bars(iid, count=120)
        close_data[sym] = [float(b.close) for b in bars]

    min_len = min(len(v) for v in close_data.values())
    if min_len < 20:
        raise HTTPException(status_code=400, detail="数据不足，需至少 20 根 K 线")

    trimmed = {k: v[-min_len:] for k, v in close_data.items()}

    names = list(trimmed.keys())
    n = len(names)
    corr_matrix: list[list[float]] = []
    for i in range(n):
        row = []
        for j in range(n):
            a = np.array(trimmed[names[i]])
            b = np.array(trimmed[names[j]])
            corr = float(np.corrcoef(a, b)[0, 1])
            row.append(round(corr, 4))
        corr_matrix.append(row)

    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            a = np.array(trimmed[names[i]])
            b = np.array(trimmed[names[j]])
            corr_val = corr_matrix[i][j]

            hedge_ratio = float(np.polyfit(b, a, 1)[0])
            spread = a - hedge_ratio * b
            spread_mean = float(np.mean(spread))
            spread_std = float(np.std(spread))

            adf_stat = _simple_adf(spread)
            p_value = _adf_pvalue(adf_stat, len(spread))

            suggestion = (
                "可配对"
                if (abs(corr_val) > 0.7 and p_value < 0.1)
                else "弱"
                if abs(corr_val) > 0.5
                else "不建议"
            )

            pairs.append(
                {
                    "a": names[i],
                    "b": names[j],
                    "correlation": round(corr_val, 4),
                    "coint_pvalue": round(p_value, 4),
                    "hedge_ratio": round(hedge_ratio, 4),
                    "spread_mean": round(spread_mean, 2),
                    "spread_std": round(spread_std, 2),
                    "suggestion": suggestion,
                }
            )

    pairs.sort(key=lambda x: x["coint_pvalue"])

    return {
        "symbols": names,
        "corr_matrix": corr_matrix,
        "pairs": pairs,
    }


def _simple_adf(series) -> float:
    """Simplified ADF test statistic (Dickey-Fuller)."""
    import numpy as np

    y = np.array(series)
    dy = np.diff(y)
    y_lag = y[:-1]
    n = len(dy)
    if n < 5:
        return 0.0
    x = np.column_stack([y_lag, np.ones(n)])
    beta = np.linalg.lstsq(x, dy, rcond=None)[0]
    residuals = dy - x @ beta
    se = np.sqrt(np.sum(residuals**2) / (n - 2))
    se_beta = se / np.sqrt(np.sum((y_lag - y_lag.mean()) ** 2))
    if se_beta == 0:
        return 0.0
    return float(beta[0] / se_beta)


def _adf_pvalue(stat: float, nobs: int) -> float:
    """Approximate ADF p-value from test statistic."""
    if stat < -3.96:
        return 0.01
    elif stat < -3.41:
        return 0.05
    elif stat < -3.13:
        return 0.10
    elif stat < -2.86:
        return 0.15
    elif stat < -2.57:
        return 0.20
    elif stat < -1.94:
        return 0.35
    elif stat < -1.62:
        return 0.50
    else:
        return 0.80


_CN_NAMES: dict[str, str] = {}
_CN_NAMES_LOADED = False


def _load_cn_names():
    """Lazy-load Chinese security names from AkShare."""
    global _CN_NAMES, _CN_NAMES_LOADED
    if _CN_NAMES_LOADED:
        return
    try:
        import akshare as ak

        _ensure_no_proxy_for_names()
        for loader in [
            lambda: ak.stock_zh_a_spot_em()[["代码", "名称"]],
            lambda: ak.fund_name_em()[["基金代码", "基金简称"]],
        ]:
            try:
                df = loader()
                for _, row in df.iterrows():
                    _CN_NAMES[str(row.iloc[0])] = str(row.iloc[1])
            except Exception:
                pass
    except ImportError:
        pass
    _CN_NAMES_LOADED = True


def _ensure_no_proxy_for_names():
    import os

    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        os.environ.pop(k, None)
    os.environ["NO_PROXY"] = "*"


_STATIC_CN_NAMES = {
    "600519": "贵州茅台",
    "000001": "平安银行",
    "000300": "沪深300",
    "510300": "沪深300ETF",
    "510500": "中证500ETF",
    "159915": "创业板ETF",
    "159659": "纳指100ETF",
    "513500": "标普500ETF",
    "513400": "道琼斯ETF",
    "513860": "东证ETF",
    "513030": "德国ETF华安",
    "513080": "法国ETF",
    "159501": "纳指ETF嘉实",
    "159502": "标普生物科技ETF",
    "159632": "纳斯达克100ETF",
    "000016": "上证50",
    "399001": "深成指",
    "399006": "创业板指",
    "000905": "中证500",
    "600036": "招商银行",
    "601318": "中国平安",
    "000858": "五粮液",
    "002594": "比亚迪",
    "600276": "恒瑞医药",
    "000333": "美的集团",
    "601398": "工商银行",
    "600887": "伊利股份",
    "002415": "海康威视",
    "AAPL": "苹果",
    "TSLA": "特斯拉",
    "MSFT": "微软",
    "GOOGL": "谷歌",
    "AMZN": "亚马逊",
    "NVDA": "英伟达",
    "META": "Meta",
    "JPM": "摩根大通",
    "MU": "美光科技",
    "WU": "西联汇款",
    "110011": "易方达中小盘",
    "161725": "招商中证白酒",
    "012414": "景顺长城新能源",
    "005827": "易方达蓝筹精选",
    "163406": "兴全合润",
    "260108": "景顺长城新兴成长",
    "519069": "汇添富价值精选",
    "008888": "华夏国证半导体芯片ETF联接C",
    "688256": "寒武纪",
    "au2412": "黄金2412",
    "au": "黄金",
    "ag": "白银",
    "cu": "铜",
    "al": "铝",
    "zn": "锌",
    "rb": "螺纹钢",
    "i": "铁矿石",
    "m": "豆粕",
    "y": "豆油",
    "p": "棕榈油",
    "IF": "沪深300股指",
    "IH": "上证50股指",
    "IC": "中证500股指",
    "IM": "中证1000股指",
}


def get_cn_name(symbol_with_exchange: str) -> str:
    """Get Chinese name for a symbol. Returns empty string if not found."""
    code = symbol_with_exchange.split(".")[0].strip()
    if code in _STATIC_CN_NAMES:
        return _STATIC_CN_NAMES[code]
    # 期货合约：au2412 → 黄金2412
    import re

    m = re.match(r"^([a-zA-Z]+)(\d{3,4})$", code)
    if m:
        product, month = m.group(1), m.group(2)
        product_name = _STATIC_CN_NAMES.get(product) or _STATIC_CN_NAMES.get(product.lower())
        if product_name:
            return f"{product_name}{month}"
    if not _CN_NAMES_LOADED:
        _load_cn_names()
    return _CN_NAMES.get(code, "")


@app.get("/api/data/instruments")
async def data_instruments():
    instruments = list_instruments()
    named = []
    for sym in instruments:
        cn = get_cn_name(sym)
        named.append({"symbol": sym, "name": cn})
    return {"instruments": instruments, "named": named, "count": len(instruments)}


@app.get("/api/data/cn_name/{symbol}")
async def data_cn_name(symbol: str):
    """查询标的中文名称。"""
    return {"symbol": symbol, "name": get_cn_name(symbol)}


@app.get("/api/data/bars/{symbol}")
async def data_bars(symbol: str, limit: int = 0, start: str | None = None, end: str | None = None):
    try:
        bars = get_bar_preview(symbol, limit=limit, start_str=start, end_str=end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"symbol": symbol, "bars": bars, "count": len(bars)}


@app.post("/api/data/fetch")
async def data_fetch(req: FetchDataRequest):
    try:
        start = datetime.strptime(req.start, "%Y-%m-%d")
        end = datetime.strptime(req.end, "%Y-%m-%d") if req.end else None
        result = await fetch_market_data(
            symbol=req.symbol.strip(),
            start=start,
            end=end,
            interval=req.interval,
            provider=req.provider,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Data provider not installed: {e}. Run: uv sync --extra data",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.delete("/api/data/instruments/{symbol}")
async def data_delete_instrument(symbol: str):
    """删除本地已存储标的的全部行情数据。"""
    from quant_trading.core.config import Settings
    from quant_trading.data.store import DataStore
    from quant_trading.model.instrument import InstrumentId

    try:
        instrument_id = InstrumentId.from_str(symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    settings = Settings.load()
    store = DataStore(settings.data.parquet_dir)
    ok = store.delete_instrument(instrument_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"未找到本地数据: {symbol}")
    return {"status": "deleted", "symbol": str(instrument_id)}


@app.get("/api/data/catalog")
async def data_catalog():
    """获取数据目录：所有已存储数据集的元数据。"""
    from quant_trading.core.config import Settings
    from quant_trading.data.store import DataStore

    settings = Settings.load()
    store = DataStore(settings.data.parquet_dir)
    catalog = store.get_catalog()
    return {"catalog": catalog, "count": len(catalog)}


@app.post("/api/data/query")
async def data_query(sql: str = "SELECT 1 AS test"):
    """执行 SQL 查询（只读，仅 SELECT/WITH/SHOW）。"""
    from quant_trading.core.config import Settings
    from quant_trading.data.store import DataStore

    settings = Settings.load()
    store = DataStore(settings.data.parquet_dir)
    try:
        result = store.query_safe(sql)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/backtest/run")
async def backtest_run(req: BacktestRequest):
    try:
        start = datetime.strptime(req.start, "%Y-%m-%d")
        end = datetime.strptime(req.end, "%Y-%m-%d") if req.end else None
        result = run_backtest(
            strategy_id=req.strategy,
            symbol=req.symbol,
            start=start,
            end=end,
            capital=req.capital,
            params=req.params,
            use_demo_data=req.use_demo_data,
            enable_t1=req.enable_t1,
            adjust=req.adjust,
            transfer_fee_rate=req.transfer_fee_rate,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/backtest/compare")
async def backtest_compare(req: BacktestRequest):
    """对比所有策略在相同标的和日期范围上的表现。"""
    try:
        start = datetime.strptime(req.start, "%Y-%m-%d")
        end = datetime.strptime(req.end, "%Y-%m-%d") if req.end else None
        results = {}
        for sid in BUILTIN_STRATEGIES:
            if sid == "pair":
                continue
            try:
                result = run_backtest(
                    strategy_id=sid,
                    symbol=req.symbol,
                    start=start,
                    end=end,
                    capital=req.capital,
                    use_demo_data=True,
                )
                results[sid] = result
            except Exception:
                pass
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# ── Monte Carlo Stress Test API ────────────────────────────


@app.post("/api/backtest/montecarlo")
async def backtest_montecarlo(req: BacktestRequest):
    """对回测交易序列做 Monte Carlo 随机扰动压力测试。"""
    import random

    try:
        start = datetime.strptime(req.start, "%Y-%m-%d")
        end = datetime.strptime(req.end, "%Y-%m-%d") if req.end else None
        base = run_backtest(
            strategy_id=req.strategy,
            symbol=req.symbol,
            start=start,
            end=end,
            capital=req.capital,
            params=req.params,
            use_demo_data=req.use_demo_data,
            enable_t1=req.enable_t1,
            adjust=req.adjust,
            transfer_fee_rate=req.transfer_fee_rate,
        )

        trades = base["trades"]
        if not trades:
            raise ValueError("回测无交易记录，无法做 Monte Carlo 分析")

        pnl_list = [t["pnl"] for t in trades]
        capital = req.capital
        n_sims = 500
        sim_finals = []
        sim_drawdowns = []
        percentile_curves: list[list[float]] = []

        for _ in range(n_sims):
            shuffled = pnl_list[:]
            random.shuffle(shuffled)
            eq = capital
            peak = eq
            max_dd = 0.0
            curve = [eq]
            for pnl in shuffled:
                eq += pnl
                curve.append(eq)
                if eq > peak:
                    peak = eq
                dd = (peak - eq) / peak if peak > 0 else 0
                if dd > max_dd:
                    max_dd = dd
            sim_finals.append(eq)
            sim_drawdowns.append(max_dd)
            percentile_curves.append(curve)

        sim_finals.sort()
        sim_drawdowns.sort()
        n = len(sim_finals)

        p5_idx = max(0, int(n * 0.05) - 1)
        p25_idx = max(0, int(n * 0.25) - 1)
        p50_idx = max(0, int(n * 0.50) - 1)
        p75_idx = max(0, int(n * 0.75) - 1)
        p95_idx = min(n - 1, int(n * 0.95))

        max_len = max(len(c) for c in percentile_curves)
        p5_curve, p50_curve, p95_curve = [], [], []
        for i in range(max_len):
            vals = sorted(c[i] for c in percentile_curves if i < len(c))
            if not vals:
                break
            p5_curve.append(vals[max(0, int(len(vals) * 0.05) - 1)])
            p50_curve.append(vals[len(vals) // 2])
            p95_curve.append(vals[min(len(vals) - 1, int(len(vals) * 0.95))])

        return {
            "n_simulations": n_sims,
            "n_trades": len(pnl_list),
            "base_final": base["metrics"]["final_capital"],
            "base_return": base["metrics"]["total_return"],
            "base_max_dd": base["metrics"]["max_drawdown"],
            "stats": {
                "mean_final": sum(sim_finals) / n,
                "p5_final": sim_finals[p5_idx],
                "p25_final": sim_finals[p25_idx],
                "p50_final": sim_finals[p50_idx],
                "p75_final": sim_finals[p75_idx],
                "p95_final": sim_finals[p95_idx],
                "worst_final": sim_finals[0],
                "best_final": sim_finals[-1],
                "mean_max_dd": sum(sim_drawdowns) / n,
                "p95_max_dd": sim_drawdowns[p95_idx],
                "worst_max_dd": sim_drawdowns[-1],
            },
            "distribution": {
                "finals": [
                    round(sim_finals[min(n - 1, int(n * p / 100))], 2) for p in range(0, 101, 5)
                ],
                "drawdowns": [
                    round(sim_drawdowns[min(n - 1, int(n * p / 100))] * 100, 2)
                    for p in range(0, 101, 5)
                ],
            },
            "percentile_curves": {
                "p5": [round(v, 2) for v in p5_curve],
                "p50": [round(v, 2) for v in p50_curve],
                "p95": [round(v, 2) for v in p95_curve],
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# ── Review Report API ──────────────────────────────────────


@app.post("/api/backtest/review")
async def backtest_review(req: BacktestRequest):
    """生成回测复盘报表：按月/按周统计、最大连胜/连亏、持仓分析。"""
    from collections import defaultdict

    try:
        start = datetime.strptime(req.start, "%Y-%m-%d")
        end = datetime.strptime(req.end, "%Y-%m-%d") if req.end else None
        result = run_backtest(
            strategy_id=req.strategy,
            symbol=req.symbol,
            start=start,
            end=end,
            capital=req.capital,
            params=req.params,
            use_demo_data=req.use_demo_data,
            enable_t1=req.enable_t1,
            adjust=req.adjust,
            transfer_fee_rate=req.transfer_fee_rate,
        )

        trades = result["trades"]
        equity = result["equity_curve"]
        metrics = result["metrics"]

        monthly: dict[str, dict] = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
        for t in trades:
            month_key = t["entry_time"][:7]
            monthly[month_key]["pnl"] += t["pnl"]
            monthly[month_key]["trades"] += 1
            if t["pnl"] > 0:
                monthly[month_key]["wins"] += 1

        monthly_list = []
        for k in sorted(monthly.keys()):
            m = monthly[k]
            wr = m["wins"] / m["trades"] if m["trades"] > 0 else 0
            monthly_list.append(
                {
                    "month": k,
                    "pnl": round(m["pnl"], 2),
                    "trades": m["trades"],
                    "win_rate": round(wr, 4),
                }
            )

        streak_win, streak_lose, cur_win, cur_lose = 0, 0, 0, 0
        for t in trades:
            if t["pnl"] > 0:
                cur_win += 1
                cur_lose = 0
            else:
                cur_lose += 1
                cur_win = 0
            streak_win = max(streak_win, cur_win)
            streak_lose = max(streak_lose, cur_lose)

        win_pnls = [t["pnl"] for t in trades if t["pnl"] > 0]
        lose_pnls = [t["pnl"] for t in trades if t["pnl"] <= 0]
        durations = []
        for t in trades:
            try:
                entry = datetime.fromisoformat(t["entry_time"])
                exit_ = datetime.fromisoformat(t["exit_time"])
                durations.append((exit_ - entry).days)
            except Exception:
                pass

        return {
            "metrics": metrics,
            "monthly": monthly_list,
            "streaks": {
                "max_consecutive_wins": streak_win,
                "max_consecutive_losses": streak_lose,
            },
            "trade_analysis": {
                "total": len(trades),
                "avg_win": round(sum(win_pnls) / len(win_pnls), 2) if win_pnls else 0,
                "avg_loss": round(sum(lose_pnls) / len(lose_pnls), 2) if lose_pnls else 0,
                "largest_win": round(max(win_pnls), 2) if win_pnls else 0,
                "largest_loss": round(min(lose_pnls), 2) if lose_pnls else 0,
                "avg_duration_days": round(sum(durations) / len(durations), 1) if durations else 0,
                "max_duration_days": max(durations) if durations else 0,
                "min_duration_days": min(durations) if durations else 0,
            },
            "equity_curve": equity,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# ── Parameter Optimization APIs ────────────────────────────


@app.post("/api/optimize/run")
async def optimize_run(req: OptimizeRequest):
    """运行参数网格搜索优化。"""
    from quant_trading.strategy.optimizer import StrategyOptimizer

    try:
        start = datetime.strptime(req.start, "%Y-%m-%d")
        end = datetime.strptime(req.end, "%Y-%m-%d") if req.end else None
        optimizer = StrategyOptimizer(
            strategy_id=req.strategy,
            symbol=req.symbol,
            start=start,
            end=end,
            capital=req.capital,
            use_demo_data=req.use_demo_data,
        )
        results = await asyncio.to_thread(optimizer.optimize, req.param_grid)
        return {
            "results": [dataclasses.asdict(r) for r in results],
            "total": len(results),
            "strategy": req.strategy,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# ── Monitor / Alert APIs ──────────────────────────────────


@app.get("/api/monitor/alerts")
async def monitor_alerts(limit: int = 50):
    """获取最近的告警记录。"""
    from quant_trading.monitoring.alert import AlertManager

    manager = AlertManager()
    return {"alerts": manager.get_recent_alerts(limit), "count": manager.alert_count}


@app.get("/api/monitor/config")
async def monitor_config():
    """获取监控告警阈值配置。"""
    from quant_trading.monitoring.alert import AlertManager

    manager = AlertManager()
    return {"thresholds": manager._thresholds}


@app.post("/api/monitor/test")
async def monitor_test_alert():
    """发送一条测试告警。"""
    from quant_trading.monitoring.alert import Alert, AlertLevel, AlertManager, AlertType

    manager = AlertManager()
    manager.fire(
        Alert(
            alert_type=AlertType.CUSTOM,
            level=AlertLevel.INFO,
            message="这是一条测试告警（Web 界面触发）",
        )
    )
    return {"alerts": manager.get_recent_alerts(10), "count": manager.alert_count}


@app.post("/api/monitor/push-config")
async def monitor_push_config(
    channel: str = "webhook",
    url: str = "",
    platform: str = "wecom",
    smtp_host: str = "",
    smtp_port: int = 465,
    username: str = "",
    password: str = "",
    sender: str = "",
    recipients: str = "",
):
    """配置告警推送通道（Webhook 或 Email），并发送测试消息验证。"""
    from quant_trading.monitoring.alert import (
        Alert,
        AlertLevel,
        AlertManager,
        AlertType,
        EmailAlertHandler,
        WebhookAlertHandler,
    )

    manager = AlertManager()

    if channel == "webhook":
        if not url:
            raise HTTPException(status_code=400, detail="Webhook URL 不能为空")
        handler = WebhookAlertHandler(url=url, platform=platform)
        manager.add_handler(handler)
        test_alert = Alert(
            alert_type=AlertType.CUSTOM,
            level=AlertLevel.INFO,
            message=f"告警通道测试（{platform}）- 来自 Web 配置",
        )
        manager.fire(test_alert)
        return {"status": "ok", "channel": "webhook", "platform": platform}

    elif channel == "email":
        if not smtp_host or not recipients:
            raise HTTPException(status_code=400, detail="SMTP 主机和收件人不能为空")
        rcpt_list = [r.strip() for r in recipients.split(",") if r.strip()]
        handler = EmailAlertHandler(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            use_ssl=True,
            username=username,
            password=password,
            sender=sender or username,
            recipients=rcpt_list,
        )
        manager.add_handler(handler)
        test_alert = Alert(
            alert_type=AlertType.CUSTOM,
            level=AlertLevel.INFO,
            message="告警通道测试（邮件）- 来自 Web 配置",
        )
        manager.fire(test_alert)
        return {"status": "ok", "channel": "email", "recipients": rcpt_list}

    raise HTTPException(status_code=400, detail=f"Unknown channel: {channel}")


# ── Multi-Account APIs ─────────────────────────────────────


@app.get("/api/accounts")
async def accounts_list():
    """列出所有模拟盘账户。"""
    result = []
    for name, gw in _paper_gateways.items():
        account = await gw.query_account()
        result.append(
            {
                "name": name,
                "active": name == _active_account,
                "balance": float(account.balance),
                "available": float(account.available),
            }
        )
    if not result:
        gw = _get_paper_gateway()
        await gw.connect()
        account = await gw.query_account()
        result.append(
            {
                "name": _active_account,
                "active": True,
                "balance": float(account.balance),
                "available": float(account.available),
            }
        )
    return {"accounts": result, "active": _active_account}


@app.post("/api/accounts/create")
async def accounts_create(
    name: str = "sub1",
    capital: float = 100_000.0,
):
    """创建新的模拟盘账户。"""
    global _active_account
    if name in _paper_gateways:
        raise HTTPException(status_code=400, detail=f"账户 {name} 已存在")
    gw = _get_paper_gateway(capital=capital, account_name=name)
    await gw.connect()
    return {"status": "created", "name": name}


@app.post("/api/accounts/switch")
async def accounts_switch(name: str = "default"):
    """切换活跃账户。"""
    global _active_account
    if name not in _paper_gateways:
        raise HTTPException(status_code=400, detail=f"账户 {name} 不存在")
    _active_account = name
    gw = _paper_gateways[name]
    if not gw.is_connected:
        await gw.connect()
    account = await gw.query_account()
    return {
        "status": "switched",
        "active": name,
        "account": _serialize_account(account),
    }


@app.delete("/api/accounts/delete")
async def accounts_delete(name: str):
    """删除模拟盘账户。"""
    global _active_account
    if name == "default":
        raise HTTPException(status_code=400, detail="不能删除默认账户")
    if name not in _paper_gateways:
        raise HTTPException(status_code=400, detail=f"账户 {name} 不存在")
    del _paper_gateways[name]
    if _active_account == name:
        _active_account = "default"
    return {"status": "deleted", "name": name}


# ── Paper Trading APIs ─────────────────────────────────────


@app.post("/api/paper/connect")
async def paper_connect(req: PaperConfigRequest | None = None):
    """连接模拟盘（恢复之前的状态，不会重置）。"""
    cfg = req or PaperConfigRequest()
    gw = _get_paper_gateway(cfg.initial_capital, cfg.commission_rate, cfg.slippage_rate)
    await gw.connect()
    account = await gw.query_account()
    positions = await gw.query_positions()
    return {
        "status": "connected",
        "account": _serialize_account(account),
        "positions": [_serialize_position(p) for p in positions],
        "history_count": len(gw._order_history),
    }


@app.post("/api/paper/reset")
async def paper_reset(req: PaperConfigRequest | None = None):
    """重置模拟盘（清除所有订单/持仓/资金，重新开始）。"""
    cfg = req or PaperConfigRequest()
    gw = _get_paper_gateway(cfg.initial_capital, cfg.commission_rate, cfg.slippage_rate, reset=True)
    gw.reset()
    await gw.connect()
    account = await gw.query_account()
    return {
        "status": "reset",
        "account": _serialize_account(account),
    }


@app.get("/api/paper/account")
async def paper_account():
    """查询模拟盘账户。"""
    gw = _get_paper_gateway()
    if not gw.is_connected:
        await gw.connect()
    account = await gw.query_account()
    return {"account": _serialize_account(account)}


@app.get("/api/paper/positions")
async def paper_positions():
    """查询模拟盘持仓。"""
    gw = _get_paper_gateway()
    if not gw.is_connected:
        await gw.connect()
    positions = await gw.query_positions()
    return {
        "positions": [_serialize_position(p) for p in positions],
        "count": len(positions),
    }


@app.post("/api/paper/order")
async def paper_submit_order(req: PaperOrderRequest):
    """模拟盘下单。"""
    from quant_trading.model.instrument import InstrumentId
    from quant_trading.model.order import Order, OrderSide, OrderType

    gw = _get_paper_gateway()
    if not gw.is_connected:
        await gw.connect()

    instrument_id = InstrumentId.from_str(req.symbol)
    side = OrderSide.BUY if req.side.lower() == "buy" else OrderSide.SELL
    type_map = {
        "market": OrderType.MARKET,
        "limit": OrderType.LIMIT,
        "trailing_stop": OrderType.TRAILING_STOP,
        "conditional": OrderType.CONDITIONAL,
    }
    order_type = type_map.get(req.order_type.lower(), OrderType.LIMIT)

    order = Order(
        instrument_id=instrument_id,
        side=side,
        order_type=order_type,
        quantity=req.quantity,
        price=Decimal(str(req.price)) if req.price else Decimal(0),
    )
    if order_type == OrderType.TRAILING_STOP:
        if req.trigger_price is not None:
            order.stop_price = Decimal(str(req.trigger_price))
        elif req.trail_offset is not None:
            order.stop_price = Decimal(str(req.trail_offset))
    elif order_type == OrderType.CONDITIONAL and req.cond_price is not None:
        op = "<=" if (req.cond_direction or "above") == "below" else ">="
        order.condition_expr = f"close {op} {req.cond_price}"

    latest_price, from_local = _get_latest_price(req.symbol)
    gw.on_price_update(instrument_id, latest_price)

    order_id = await gw.submit_order(order)
    account = await gw.query_account()
    positions = await gw.query_positions()

    return {
        "order_id": order_id,
        "status": order.status.value,
        "fill_price": float(latest_price),
        "price_from_local_data": from_local,
        "account": _serialize_account(account),
        "positions": [_serialize_position(p) for p in positions],
    }


@app.get("/api/paper/orders")
async def paper_orders():
    """查询模拟盘挂单。"""
    gw = _get_paper_gateway()
    if not gw.is_connected:
        await gw.connect()
    pending = gw._pending_orders
    return {
        "orders": [
            {
                "order_id": o.order_id,
                "instrument_id": str(o.instrument_id),
                "side": o.side.value,
                "order_type": o.order_type.value,
                "quantity": o.quantity,
                "price": float(o.price) if o.price else None,
                "status": o.status.value,
            }
            for o in pending
        ],
        "count": len(pending),
    }


@app.get("/api/paper/order_history")
async def paper_order_history():
    """查询模拟盘已成交订单历史。"""
    gw = _get_paper_gateway()
    if not gw.is_connected:
        await gw.connect()
    history = gw._order_history
    return {"orders": history, "count": len(history)}


# ── Watchlist (自选) ───────────────────────────────────────

_WATCHLIST_FILE = Path("data/paper_trading/watchlist.json")


def _load_watchlist() -> list[str]:
    if not _WATCHLIST_FILE.exists():
        return []
    try:
        data = json.loads(_WATCHLIST_FILE.read_text(encoding="utf-8"))
        return list(data.get("symbols", []))
    except Exception:
        return []


def _save_watchlist(symbols: list[str]) -> None:
    _WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    _WATCHLIST_FILE.write_text(
        json.dumps({"symbols": symbols}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


_WATCHLIST_QUOTE_CACHE: dict[str, Any] = {"ts": 0.0, "spot": {}, "etf": {}, "industry": {}}


def _refresh_quote_cache() -> None:
    """刷新 A 股/ETF 行情与行业涨幅缓存（约 60 秒）。"""
    import time

    now = time.time()
    if now - float(_WATCHLIST_QUOTE_CACHE["ts"]) < 60:
        return
    try:
        import akshare as ak

        _ensure_no_proxy_for_names()
        spot: dict[str, dict[str, Any]] = {}
        try:
            df = ak.stock_zh_a_spot_em()
            for _, row in df.iterrows():
                code = str(row.get("代码", "")).strip()
                if not code:
                    continue
                spot[code] = {
                    "name": str(row.get("名称", "")),
                    "change_pct": float(row.get("涨跌幅", 0) or 0),
                    "price": float(row.get("最新价", 0) or 0),
                }
        except Exception:
            pass
        etf: dict[str, dict[str, Any]] = {}
        try:
            df_etf = ak.fund_etf_spot_em()
            for _, row in df_etf.iterrows():
                code = str(row.iloc[0]).strip()
                # columns vary; try common names
                name = str(row.get("名称", row.iloc[1] if len(row) > 1 else ""))
                chg = row.get("涨跌幅", None)
                if chg is None and len(row) > 4:
                    try:
                        chg = float(row.iloc[4])
                    except Exception:
                        chg = 0
                etf[code] = {
                    "name": name,
                    "change_pct": float(chg or 0),
                }
        except Exception:
            pass
        industry: dict[str, float] = {}
        try:
            df_ind = ak.stock_board_industry_name_em()
            for _, row in df_ind.iterrows():
                ind_name = str(row.get("板块名称", "")).strip()
                if ind_name:
                    industry[ind_name] = float(row.get("涨跌幅", 0) or 0)
        except Exception:
            pass
        _WATCHLIST_QUOTE_CACHE.update({"ts": now, "spot": spot, "etf": etf, "industry": industry})
    except ImportError:
        _WATCHLIST_QUOTE_CACHE["ts"] = now


_SECTOR_CACHE: dict[str, str] = {}


def _sector_for_code(code: str) -> tuple[str, float | None]:
    """查询个股所属行业及行业涨跌幅（行业名本地缓存）。"""
    sector = _SECTOR_CACHE.get(code, "")
    if not sector:
        try:
            import akshare as ak

            _ensure_no_proxy_for_names()
            info = ak.stock_individual_info_em(symbol=code)
            for _, row in info.iterrows():
                item = str(row.iloc[0])
                if item in ("行业", "所属行业"):
                    sector = str(row.iloc[1]).strip()
                    break
            if sector:
                _SECTOR_CACHE[code] = sector
        except Exception:
            return "", None
    if not sector:
        return "", None
    _refresh_quote_cache()
    chg = _WATCHLIST_QUOTE_CACHE["industry"].get(sector)
    return sector, chg


def _quote_for_symbol(symbol: str) -> dict[str, Any]:
    """为自选标的组装名称、涨跌幅与对应日期。"""
    from quant_trading.core.config import Settings
    from quant_trading.data.store import DataStore
    from quant_trading.model.instrument import InstrumentId
    from quant_trading.model.market import BarInterval

    code = symbol.split(".")[0].strip()
    exchange = symbol.split(".")[-1].upper() if "." in symbol else ""
    today = datetime.now().strftime("%Y-%m-%d")
    result: dict[str, Any] = {
        "symbol": symbol,
        "name": get_cn_name(symbol),
        "change_pct": None,
        "price": None,
        "asof_date": today,
        "quote_source": "none",
    }

    def _from_local() -> dict[str, Any]:
        settings = Settings.load()
        store = DataStore(settings.data.parquet_dir)
        bars = store.load_bars(InstrumentId.from_str(symbol), BarInterval.DAILY)
        by_day: dict[str, Any] = {}
        for b in bars:
            by_day[b.timestamp.strftime("%Y-%m-%d")] = b
        uniq = [by_day[k] for k in sorted(by_day)]
        if len(uniq) >= 2:
            prev, last = float(uniq[-2].close), float(uniq[-1].close)
            if prev:
                result["change_pct"] = round((last - prev) / prev * 100, 2)
                result["price"] = last
                result["quote_source"] = "local"
                result["asof_date"] = uniq[-1].timestamp.strftime("%Y-%m-%d")
        elif len(uniq) == 1:
            result["price"] = float(uniq[-1].close)
            result["quote_source"] = "local"
            result["asof_date"] = uniq[-1].timestamp.strftime("%Y-%m-%d")
            result["change_pct"] = None
        return result

    # 场外基金直接用本地净值，避免拉全市场实时行情拖慢接口
    if exchange == "OTC":
        try:
            return _from_local()
        except Exception:
            return result

    _refresh_quote_cache()
    spot = _WATCHLIST_QUOTE_CACHE["spot"]
    etf = _WATCHLIST_QUOTE_CACHE["etf"]

    if code in spot:
        result["change_pct"] = spot[code]["change_pct"]
        result["price"] = spot[code]["price"]
        if spot[code].get("name") and not result["name"]:
            result["name"] = spot[code]["name"]
        result["quote_source"] = "spot"
        result["asof_date"] = today
        return result

    if code in etf:
        result["change_pct"] = etf[code]["change_pct"]
        if etf[code].get("name") and not result["name"]:
            result["name"] = etf[code]["name"]
        result["quote_source"] = "etf"
        result["asof_date"] = today
        return result

    if exchange in ("SSE", "SZSE", "NASDAQ", "NYSE", "SHFE", "DCE", "CZCE", "CFFEX"):
        try:
            return _from_local()
        except Exception:
            pass
    return result


@app.get("/api/watchlist")
async def watchlist_get():
    """获取自选列表（含中文名、当日涨跌及日期）。"""
    symbols = _load_watchlist()
    items = [_quote_for_symbol(s) for s in symbols]
    return {"items": items, "count": len(items)}


@app.post("/api/watchlist")
async def watchlist_add(body: dict[str, Any]):
    """添加自选。body: {\"symbol\": \"161725.OTC\"}"""
    raw = (body.get("symbol") or "").strip()
    if not raw or "." not in raw:
        raise HTTPException(status_code=400, detail="需要标的代码，如 161725.OTC")
    code, exchange = raw.rsplit(".", 1)
    symbol = f"{code.strip()}.{exchange.strip().upper()}"
    symbols = _load_watchlist()
    if symbol not in symbols:
        symbols.append(symbol)
        _save_watchlist(symbols)
    item = _quote_for_symbol(symbol)
    return {"status": "ok", **item, "count": len(symbols)}


@app.delete("/api/watchlist/{symbol}")
async def watchlist_remove(symbol: str):
    """移除自选。"""
    symbols = _load_watchlist()
    symbols = [s for s in symbols if s != symbol]
    _save_watchlist(symbols)
    return {"status": "ok", "count": len(symbols)}


def _serialize_account(account: Any) -> dict:
    return {
        "account_id": account.account_id,
        "balance": float(account.balance),
        "available": float(account.available),
        "commission": float(account.commission),
        "currency": account.currency.value,
    }


def _serialize_position(pos: Any) -> dict:
    sym = str(pos.instrument_id)
    return {
        "instrument_id": sym,
        "name": get_cn_name(sym),
        "quantity": pos.quantity,
        "avg_price": float(pos.avg_cost),
        "realized_pnl": float(pos.realized_pnl),
        "side": "long" if pos.quantity > 0 else "short",
    }


# ── Emergency Risk Control APIs ────────────────────────────

_risk_engine: Any = None


def _get_risk_engine() -> Any:
    global _risk_engine
    if _risk_engine is None:
        from quant_trading.risk.engine import RiskEngine

        _risk_engine = RiskEngine()
    return _risk_engine


@app.get("/api/risk/status")
async def risk_status():
    """获取风控引擎当前状态。"""
    engine = _get_risk_engine()
    return engine.get_status()


@app.post("/api/risk/freeze")
async def risk_freeze():
    """紧急冻结 - 拒绝所有新订单。"""
    engine = _get_risk_engine()
    engine.emergency_freeze()
    return {"action": "freeze", "status": engine.get_status()}


@app.post("/api/risk/unfreeze")
async def risk_unfreeze():
    """解除紧急冻结。"""
    engine = _get_risk_engine()
    engine.emergency_unfreeze()
    return {"action": "unfreeze", "status": engine.get_status()}


@app.post("/api/risk/halt")
async def risk_halt_strategies():
    """暂停所有策略。"""
    engine = _get_risk_engine()
    engine.halt_strategies()
    return {"action": "halt_strategies", "status": engine.get_status()}


@app.post("/api/risk/resume")
async def risk_resume_strategies():
    """恢复所有策略。"""
    engine = _get_risk_engine()
    engine.resume_strategies()
    return {"action": "resume_strategies", "status": engine.get_status()}


@app.get("/api/risk/auto-reduce")
async def risk_auto_reduce(threshold: float = 0.08, reduce_ratio: float = 0.50):
    """检测浮亏并返回需要自动减仓的订单（不自动执行，供前端确认）。"""
    gw = _get_paper_gateway()
    if not gw.is_connected:
        await gw.connect()
    positions = await gw.query_positions()
    if not positions:
        return {"orders": [], "message": "No positions"}

    pos_dict: dict[str, Any] = {}
    price_dict: dict[str, Decimal] = {}
    for p in positions:
        key = str(p.instrument_id)
        pos_dict[key] = p
        price_dict[key] = p.avg_cost

    engine = _get_risk_engine()
    orders = engine.check_unrealized_loss(pos_dict, price_dict, threshold, reduce_ratio)
    return {
        "orders": [
            {
                "instrument_id": str(o.instrument_id),
                "side": o.side.value,
                "quantity": o.quantity,
            }
            for o in orders
        ],
        "threshold_pct": threshold,
        "reduce_ratio": reduce_ratio,
    }


@app.get("/api/position-sizer/config")
async def position_sizer_config():
    """获取仓位管理器当前配置。"""
    sizer = _get_position_sizer()
    return sizer.get_config()


@app.post("/api/position-sizer/calculate")
async def position_sizer_calculate(
    mode: str = "equal_weight",
    symbols: str = "600519.SSE,000001.SSE",
):
    """根据指定模式计算各标的目标仓位。"""
    from quant_trading.risk.position_sizer import SizingMode

    sizer = _get_position_sizer()
    try:
        sizer.mode = SizingMode(mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {mode}")

    gw = _get_paper_gateway()
    if not gw.is_connected:
        await gw.connect()
    account = await gw.query_account()

    instrument_list = [s.strip() for s in symbols.split(",") if s.strip()]
    prices = {s: 100.0 for s in instrument_list}
    results = sizer.calculate(
        total_equity=float(account.balance),
        instruments=instrument_list,
        current_prices=prices,
    )
    return {
        "mode": mode,
        "equity": float(account.balance),
        "results": [
            {
                "instrument": r.instrument_key,
                "weight": round(r.weight, 4),
                "target_value": round(r.target_value, 2),
                "target_quantity": r.target_quantity,
            }
            for r in results
        ],
    }


_position_sizer: Any = None


def _get_position_sizer() -> Any:
    global _position_sizer
    if _position_sizer is None:
        from quant_trading.risk.position_sizer import PositionSizer

        _position_sizer = PositionSizer()
    return _position_sizer


@app.post("/api/risk/close-all")
async def risk_close_all():
    """一键清仓 - 对模拟盘所有持仓发出市价平仓指令。"""
    gw = _get_paper_gateway()
    if not gw.is_connected:
        await gw.connect()

    positions = await gw.query_positions()
    if not positions:
        return {"action": "close_all", "closed": 0, "message": "No positions to close"}

    closed = 0
    for pos in positions:
        if pos.is_flat:
            continue
        from quant_trading.model.order import Order, OrderSide, OrderType

        side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
        qty = abs(pos.quantity)
        order = Order(
            instrument_id=pos.instrument_id,
            side=side,
            order_type=OrderType.MARKET,
            quantity=qty,
            strategy_id="emergency_close",
        )
        gw.on_price_update(pos.instrument_id, pos.avg_cost)
        await gw.submit_order(order)
        closed += 1

    engine = _get_risk_engine()
    engine.emergency_freeze()

    account = await gw.query_account()
    return {
        "action": "close_all",
        "closed": closed,
        "account": _serialize_account(account),
        "risk_status": engine.get_status(),
    }


# ── AI Lab APIs ────────────────────────────────────────────


@app.get("/api/alpha/features")
async def alpha_features():
    """获取可用的 AI 特征列表及其描述。"""
    from quant_trading.alpha.feature import FeatureEngine

    engine = FeatureEngine()
    engine.register_defaults()
    features = []
    for name, factor in engine._factors.items():
        features.append(
            {
                "name": name,
                "dependencies": factor.dependencies,
                "type": type(factor).__name__,
            }
        )
    return {"features": features, "count": len(features)}


@app.post("/api/alpha/compute")
async def alpha_compute(symbol: str = "DEMO.SSE"):
    """对指定标的计算全部 AI 特征。"""
    import polars as pl

    from quant_trading.alpha.feature import FeatureEngine
    from quant_trading.core.config import Settings
    from quant_trading.data.store import DataStore
    from quant_trading.interface.services import generate_demo_bars
    from quant_trading.model.instrument import InstrumentId
    from quant_trading.model.market import BarInterval

    instrument_id = InstrumentId.from_str(symbol)

    settings = Settings.load()
    store = DataStore(settings.data.parquet_dir)
    bars = store.load_bars(instrument_id, BarInterval.DAILY)

    if not bars:
        bars = generate_demo_bars(instrument_id, count=120)

    df = pl.DataFrame(
        {
            "timestamp": [b.timestamp for b in bars],
            "open": [float(b.open) for b in bars],
            "high": [float(b.high) for b in bars],
            "low": [float(b.low) for b in bars],
            "close": [float(b.close) for b in bars],
            "volume": [b.volume for b in bars],
        }
    )

    engine = FeatureEngine()
    engine.register_defaults()
    result_df = engine.compute_features(df)

    tail = result_df.tail(20)
    rows = tail.to_dicts()
    for row in rows:
        if "timestamp" in row:
            row["timestamp"] = str(row["timestamp"])

    return {
        "symbol": symbol,
        "rows": rows,
        "columns": result_df.columns,
        "total_rows": len(result_df),
    }


@app.get("/api/alpha/models")
async def alpha_models():
    """获取可用的 ML 模型列表。"""
    return {
        "models": [
            {
                "id": "lightgbm",
                "name": "LightGBM",
                "description": "梯度提升树，适合金融表格数据",
                "status": "available",
            },
        ]
    }


@app.get("/api/alpha/cache")
async def alpha_cache_list():
    """列出所有已缓存的因子数据。"""
    from quant_trading.alpha.feature import FeatureEngine

    engine = FeatureEngine()
    cached = engine.list_cached()
    return {"cached": cached, "count": len(cached)}


@app.post("/api/alpha/cache/compute")
async def alpha_cache_compute(symbol: str = "DEMO.SSE", interval: str = "1d"):
    """计算并缓存指定标的的因子数据。"""
    import polars as pl

    from quant_trading.alpha.feature import FeatureEngine
    from quant_trading.core.config import Settings
    from quant_trading.data.store import DataStore
    from quant_trading.interface.services import generate_demo_bars
    from quant_trading.model.instrument import InstrumentId
    from quant_trading.model.market import BarInterval

    instrument_id = InstrumentId.from_str(symbol)
    settings = Settings.load()
    store = DataStore(settings.data.parquet_dir)

    interval_map = {
        "1d": BarInterval.DAILY,
        "1h": BarInterval.HOUR_1,
        "5m": BarInterval.MINUTE_5,
        "1m": BarInterval.MINUTE_1,
    }
    bar_interval = interval_map.get(interval, BarInterval.DAILY)
    bars = store.load_bars(instrument_id, bar_interval)

    if not bars:
        bars = generate_demo_bars(instrument_id, count=120)

    df = pl.DataFrame(
        {
            "timestamp": [b.timestamp for b in bars],
            "open": [float(b.open) for b in bars],
            "high": [float(b.high) for b in bars],
            "low": [float(b.low) for b in bars],
            "close": [float(b.close) for b in bars],
            "volume": [b.volume for b in bars],
        }
    )

    engine = FeatureEngine()
    engine.register_defaults()
    result_df = engine.compute_features(df)
    cached = engine.cache_features(symbol, interval, result_df)

    return {
        "status": "cached",
        "symbol": symbol,
        "interval": interval,
        "rows": cached,
        "factors": engine.factor_names,
    }


@app.delete("/api/alpha/cache/clear")
async def alpha_cache_clear(symbol: str | None = None):
    """清除因子缓存。"""
    from quant_trading.alpha.feature import FeatureEngine

    engine = FeatureEngine()
    deleted = engine.clear_cache(symbol)
    return {"status": "cleared", "deleted": deleted}


# ── Live Strategy Runner APIs ──────────────────────────────

_live_runner: Any = None


def _get_live_runner() -> Any:
    global _live_runner
    if _live_runner is None:
        from quant_trading.strategy.runner import LiveStrategyRunner

        _live_runner = LiveStrategyRunner(
            gateway=_get_paper_gateway(),
            risk_engine=_get_risk_engine(),
        )
    return _live_runner


@app.get("/api/live/status")
async def live_status():
    """获取实时策略运行器状态。"""
    runner = _get_live_runner()
    return runner.get_status()


@app.post("/api/live/start")
async def live_start(strategy_id: str = "dual_ma", symbol: str = "600519.SSE"):
    """启动实时策略运行。"""
    runner = _get_live_runner()
    if runner.running:
        return {"status": "already_running", **runner.get_status()}

    if strategy_id not in BUILTIN_STRATEGIES:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {strategy_id}")

    try:
        strategy = load_strategy(strategy_id, symbol)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    runner.add_strategy(strategy, [symbol])
    await runner.start()
    return {"status": "started", **runner.get_status()}


@app.post("/api/live/stop")
async def live_stop():
    """停止实时策略运行。"""
    global _live_runner
    runner = _get_live_runner()
    await runner.disconnect_websocket()
    await runner.stop()
    _live_runner = None
    return {"status": "stopped"}


@app.post("/api/live/ws-connect")
async def live_ws_connect(
    url: str = "ws://127.0.0.1:9999/ws/market",
    symbols: str = "",
):
    """连接 WebSocket 实时行情源。"""
    runner = _get_live_runner()
    if not runner.running:
        raise HTTPException(status_code=400, detail="Runner not started, start a strategy first")

    sym_list = [s.strip() for s in symbols.split(",") if s.strip()] or None
    await runner.connect_websocket(url=url, symbols=sym_list)
    return {"status": "ws_connected", **runner.get_status()}


@app.post("/api/live/ws-disconnect")
async def live_ws_disconnect():
    """断开 WebSocket 实时行情源。"""
    runner = _get_live_runner()
    await runner.disconnect_websocket()
    return {"status": "ws_disconnected", **runner.get_status()}


@app.get("/api/live/ws-status")
async def live_ws_status():
    """获取 WebSocket 行情源状态。"""
    runner = _get_live_runner()
    status = runner.get_status()
    return {
        "feed_state": status.get("feed_state", "disconnected"),
        "websocket": status.get("websocket"),
        "active_orders": status.get("active_orders", 0),
    }


@app.post("/api/live/feed")
async def live_feed(symbol: str = "DEMO.SSE", price: float = 100.0, volume: int = 1000):
    """手动推送一根模拟K线到运行器（用于测试）。"""
    from quant_trading.model.instrument import InstrumentId
    from quant_trading.model.market import Bar, BarInterval

    runner = _get_live_runner()
    if not runner.running:
        raise HTTPException(status_code=400, detail="Runner not started")

    instrument_id = InstrumentId.from_str(symbol)
    bar = Bar(
        instrument_id=instrument_id,
        timestamp=datetime.now(),
        interval=BarInterval.MINUTE_1,
        open=Decimal(str(price)),
        high=Decimal(str(price * 1.001)),
        low=Decimal(str(price * 0.999)),
        close=Decimal(str(price)),
        volume=volume,
    )
    runner.on_bar(bar)
    return {"status": "fed", "bar_count": runner.bar_count, **runner.get_status()}


# ── Scheduler APIs ────────────────────────────────────────

_scheduler: Any = None


def _get_scheduler() -> Any:
    global _scheduler
    if _scheduler is None:
        from datetime import time

        from quant_trading.core.scheduler import TaskScheduler

        _scheduler = TaskScheduler()

        async def _noop_pre():
            pass

        async def _noop_post():
            pass

        _scheduler.add_pre_market("盘前数据更新", _noop_pre, run_time=time(9, 15))
        _scheduler.add_post_market("盘后日报统计", _noop_post, run_time=time(15, 30))
    return _scheduler


@app.get("/api/scheduler/status")
async def scheduler_status():
    """获取定时任务调度器状态。"""
    return _get_scheduler().get_status()


@app.post("/api/scheduler/start")
async def scheduler_start():
    """启动定时任务调度器。"""
    s = _get_scheduler()
    if s.running:
        return {"status": "already_running", **s.get_status()}
    await s.start()
    return {"status": "started", **s.get_status()}


@app.post("/api/scheduler/stop")
async def scheduler_stop():
    """停止定时任务调度器。"""
    s = _get_scheduler()
    await s.stop()
    return {"status": "stopped"}


@app.post("/api/scheduler/run")
async def scheduler_run_task(task_name: str):
    """手动立即执行指定定时任务。"""
    return await _get_scheduler().run_task_now(task_name)


# ── Guardian APIs ─────────────────────────────────────────

_guardian: Any = None


def _get_guardian() -> Any:
    global _guardian
    if _guardian is None:
        import sys

        from quant_trading.core.guardian import ProcessGuardian

        _guardian = ProcessGuardian()
        python = sys.executable
        _guardian.add_process(
            name="quant-web",
            command=[
                python,
                "-m",
                "uvicorn",
                "quant_trading.interface.web.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8889",
            ],
            max_restarts=5,
            health_url="http://127.0.0.1:8889/api/health",
        )
    return _guardian


@app.get("/api/guardian/status")
async def guardian_status():
    """获取进程守护器状态。"""
    return _get_guardian().get_status()


@app.post("/api/guardian/start")
async def guardian_start():
    """启动进程守护器。"""
    g = _get_guardian()
    if g.running:
        return {"status": "already_running", **g.get_status()}
    await g.start()
    return {"status": "started", **g.get_status()}


@app.post("/api/guardian/stop")
async def guardian_stop():
    """停止进程守护器（终止所有被守护进程）。"""
    g = _get_guardian()
    await g.stop()
    return {"status": "stopped"}


@app.post("/api/guardian/restart")
async def guardian_restart_process(name: str):
    """手动重启指定被守护进程。"""
    return await _get_guardian().restart_process(name)


@app.get("/api/guardian/health")
async def guardian_health(name: str):
    """检查指定进程健康状态。"""
    return await _get_guardian().check_health(name)


# ── Walk-Forward API ──────────────────────────────────────


@app.post("/api/walkforward/run")
async def walkforward_run(
    strategy: str = "dual_ma",
    symbol: str = "DEMO.SSE",
    start: str = "2022-01-01",
    end: str = "2024-01-01",
    train_days: int = 180,
    test_days: int = 30,
    capital: float = 100_000.0,
    use_demo_data: bool = True,
):
    """运行 Walk-Forward 滚动验证。"""
    from quant_trading.alpha.walkforward import WalkForwardValidator

    validator = WalkForwardValidator(
        strategy_id=strategy,
        symbol=symbol,
        train_days=train_days,
        test_days=test_days,
        capital=capital,
    )
    s = datetime.strptime(start, "%Y-%m-%d")
    e = datetime.strptime(end, "%Y-%m-%d")
    result = validator.run(start=s, end=e, use_demo_data=use_demo_data)
    return {
        **result.summary(),
        "windows": [
            {
                "id": w.window_id,
                "train": f"{w.train_start:%Y-%m-%d} ~ {w.train_end:%Y-%m-%d}",
                "test": f"{w.test_start:%Y-%m-%d} ~ {w.test_end:%Y-%m-%d}",
                "return": round(w.test_return, 4),
                "sharpe": round(w.test_sharpe, 4),
            }
            for w in result.windows
        ],
    }


# ── Execution Algorithm APIs ─────────────────────────────


@app.post("/api/algo/preview")
async def algo_preview(
    algorithm: str = "twap",
    symbol: str = "600519.SSE",
    side: str = "buy",
    total_quantity: int = 10000,
    num_slices: int = 10,
    interval_seconds: int = 60,
):
    """预览执行算法拆单方案（TWAP/VWAP）。"""
    from quant_trading.model.instrument import InstrumentId
    from quant_trading.model.order import OrderSide

    iid = InstrumentId.from_str(symbol)
    order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL

    if algorithm == "twap":
        from quant_trading.execution.algorithms.twap import TWAPAlgorithm

        duration_min = max(1, (num_slices * interval_seconds) // 60)
        algo = TWAPAlgorithm(
            instrument_id=iid,
            side=order_side,
            total_quantity=total_quantity,
            duration_minutes=duration_min,
            num_slices=num_slices,
        )
        slice_qty = algo._slice_quantity
        remainder = algo._remainder
        slices_out = []
        for i in range(num_slices):
            q = slice_qty + (remainder if i == num_slices - 1 else 0)
            slices_out.append({"index": i, "quantity": q, "time_offset": i * interval_seconds})
    elif algorithm == "vwap":
        from quant_trading.execution.algorithms.vwap import VWAPAlgorithm

        algo = VWAPAlgorithm(
            instrument_id=iid,
            side=order_side,
            total_quantity=total_quantity,
            num_slices=num_slices,
        )
        slices_out = [
            {"index": s.slice_index, "quantity": s.quantity, "volume_pct": round(s.volume_pct, 4)}
            for s in algo.slices
        ]
    else:
        raise HTTPException(status_code=400, detail=f"Unknown algorithm: {algorithm}")

    return {
        "algorithm": algorithm,
        "symbol": symbol,
        "side": side,
        "total_quantity": total_quantity,
        "num_slices": len(slices_out),
        "slices": slices_out,
    }


# ── Risk Rules API ───────────────────────────────────────


@app.get("/api/risk/rules")
async def risk_rules():
    """获取事前风控四重规则配置。"""
    re = _get_risk_engine()
    return {
        "rules": [
            {
                "name": "单标的持仓比例上限",
                "key": "max_position_pct",
                "value": float(re._max_position_pct),
                "desc": "单标的持仓市值不超过总权益的此比例",
            },
            {
                "name": "单笔下单比例上限",
                "key": "max_single_order_pct",
                "value": float(re._max_single_order_pct),
                "desc": "单笔下单金额不超过总资金的此比例",
            },
            {
                "name": "下单频率上限",
                "key": "max_order_frequency",
                "value": re._max_order_frequency,
                "desc": "每分钟最大下单笔数",
            },
            {
                "name": "日亏损比例阈值",
                "key": "max_daily_loss_pct",
                "value": float(re._max_daily_loss_pct),
                "desc": "当日亏损达到此比例时冻结账户",
            },
        ],
        "frozen": re.is_frozen,
        "strategies_halted": re.strategies_halted,
    }


@app.post("/api/risk/rules/update")
async def risk_rules_update(
    max_position_pct: float | None = None,
    max_single_order_pct: float | None = None,
    max_order_frequency: int | None = None,
    max_daily_loss_pct: float | None = None,
):
    """更新事前风控规则阈值。"""
    from decimal import Decimal

    re = _get_risk_engine()
    if max_position_pct is not None:
        re._max_position_pct = Decimal(str(max_position_pct))
    if max_single_order_pct is not None:
        re._max_single_order_pct = Decimal(str(max_single_order_pct))
    if max_order_frequency is not None:
        re._max_order_frequency = max_order_frequency
    if max_daily_loss_pct is not None:
        re._max_daily_loss_pct = Decimal(str(max_daily_loss_pct))
    return {"status": "updated", **(await risk_rules())}


# ── Scheduler/Guardian Add APIs ──────────────────────────


@app.post("/api/scheduler/add")
async def scheduler_add_task(
    name: str,
    task_type: str = "interval",
    run_time: str = "09:15",
    interval: float = 60,
):
    """通过 Web 添加定时任务。"""
    from datetime import time as dt_time

    s = _get_scheduler()
    if task_type == "pre_market":
        h, m = map(int, run_time.split(":"))
        s.add_pre_market(name, _noop_task, run_time=dt_time(h, m))
    elif task_type == "post_market":
        h, m = map(int, run_time.split(":"))
        s.add_post_market(name, _noop_task, run_time=dt_time(h, m))
    elif task_type == "interval":
        s.add_interval(name, _noop_task, interval=interval)
    else:
        h, m = map(int, run_time.split(":"))
        s.add_daily(name, _noop_task, run_time=dt_time(h, m))
    return {"status": "added", **s.get_status()}


async def _noop_task():
    pass


@app.post("/api/guardian/add")
async def guardian_add_process(
    name: str,
    command: str,
    max_restarts: int = 10,
):
    """通过 Web 添加被守护进程。"""
    g = _get_guardian()
    cmd_parts = command.split()
    g.add_process(name=name, command=cmd_parts, max_restarts=max_restarts)
    return {"status": "added", **g.get_status()}


# ── Gateway Connection API ───────────────────────────────


@app.get("/api/gateway/list")
async def gateway_list():
    """获取可用网关列表及连接状态。"""
    gateways = [
        {
            "name": "paper",
            "display": "模拟盘网关",
            "status": (
                "connected"
                if _paper_gateways.get(_active_account)
                and _paper_gateways[_active_account]._connected
                else "disconnected"
            ),
            "type": "paper",
        },
        {
            "name": "ctp",
            "display": "CTP 期货网关（SimNow）",
            "status": "not_configured",
            "type": "ctp",
            "note": "需配置 config/gateways/ctp_simnow.yaml",
        },
        {
            "name": "ibkr",
            "display": "IB 盈透网关",
            "status": "not_configured",
            "type": "ib",
            "note": "需安装 TWS/IB Gateway 并配置连接",
        },
    ]
    return {"gateways": gateways}


@app.post("/api/gateway/connect")
async def gateway_connect(name: str = "paper"):
    """连接指定网关。"""
    if name == "paper":
        gw = _get_paper_gateway()
        if not gw._connected:
            await gw.connect()
        account = await gw.query_account()
        return {"status": "connected", "gateway": name, "account": _serialize_account(account)}
    elif name == "ctp":
        try:
            from quant_trading.gateway.ctp import CTPGateway

            gw = CTPGateway.create_simnow("demo", "demo")
            await gw.connect()
            return {"status": "connected", "gateway": name, "stub": True}
        except Exception as e:
            return {"status": "error", "gateway": name, "error": str(e)}
    raise HTTPException(status_code=400, detail=f"Unknown gateway: {name}")


# ── Active Orders API ────────────────────────────────────


@app.get("/api/live/orders")
async def live_active_orders():
    """获取当前活跃订单列表。"""
    runner = _get_live_runner()
    orders = []
    for oid, order in runner._active_orders.items():
        orders.append(
            {
                "order_id": oid[:12],
                "symbol": str(order.instrument_id),
                "side": order.side.value,
                "type": order.order_type.value,
                "quantity": str(order.quantity),
                "price": str(order.price) if order.price else "-",
                "status": order.status.value,
            }
        )
    return {"orders": orders, "count": len(orders)}


# ── Risk Daily Report + Consecutive Loss Pause (P2-8) ─────


@app.get("/api/risk/daily-report")
async def risk_daily_report():
    """生成当日风控日报：当日盈亏、订单统计、风控触发记录、连续亏损检测。"""
    engine = _get_risk_engine()
    status = engine.get_status()

    gw = _get_paper_gateway()
    if not gw.is_connected:
        await gw.connect()
    account = await gw.query_account()
    positions = await gw.query_positions()

    pos_list = []
    for p in positions:
        if p.is_flat:
            continue
        pos_list.append(
            {
                "instrument_id": str(p.instrument_id),
                "quantity": p.quantity,
                "avg_cost": float(p.avg_cost),
                "realized_pnl": float(p.realized_pnl),
                "side": "long" if p.quantity > 0 else "short",
            }
        )

    history = engine.get_order_history()

    consecutive_losses = 0
    max_consecutive_losses = 0
    for rec in history:
        if rec.get("pnl", 0) < 0:
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
        else:
            consecutive_losses = 0

    pause_threshold = engine.get_consecutive_loss_limit()
    should_pause = consecutive_losses >= pause_threshold and pause_threshold > 0

    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "account": {
            "balance": float(account.balance),
            "available": float(account.available),
            "equity": float(account.equity if hasattr(account, "equity") else account.balance),
        },
        "risk_status": status,
        "positions": pos_list,
        "order_summary": {
            "total_orders": status["daily_order_count"],
            "daily_pnl": status["daily_pnl"],
        },
        "consecutive_loss": {
            "current_streak": consecutive_losses,
            "max_streak": max_consecutive_losses,
            "pause_threshold": pause_threshold,
            "should_pause": should_pause,
            "is_paused": status["strategies_halted"],
        },
        "order_history": history[-20:],
    }


@app.post("/api/risk/consecutive-loss-config")
async def risk_consecutive_loss_config(threshold: int = 3):
    """设置连续亏损暂停阈值。"""
    engine = _get_risk_engine()
    engine.set_consecutive_loss_limit(threshold)
    return {"status": "updated", "threshold": threshold}


@app.post("/api/risk/consecutive-loss-check")
async def risk_consecutive_loss_check():
    """手动触发连续亏损检测，超过阈值时自动暂停策略。"""
    engine = _get_risk_engine()
    history = engine.get_order_history()
    consecutive = 0
    for rec in reversed(history):
        if rec.get("pnl", 0) < 0:
            consecutive += 1
        else:
            break

    threshold = engine.get_consecutive_loss_limit()
    triggered = consecutive >= threshold and threshold > 0
    if triggered and not engine.strategies_halted:
        engine.halt_strategies()

    return {
        "consecutive_losses": consecutive,
        "threshold": threshold,
        "triggered": triggered,
        "strategies_halted": engine.strategies_halted,
    }


# ── Blacklist & Liquidity Filter (P2-7) ──────────────────


@app.get("/api/risk/blacklist")
async def risk_blacklist():
    """获取当前黑名单。"""
    engine = _get_risk_engine()
    return {
        "blacklist": list(engine.get_blacklist()),
        "count": len(engine.get_blacklist()),
    }


@app.post("/api/risk/blacklist/add")
async def risk_blacklist_add(symbol: str):
    """添加标的到黑名单。"""
    engine = _get_risk_engine()
    engine.add_to_blacklist(symbol)
    return {"status": "added", "symbol": symbol, "blacklist": list(engine.get_blacklist())}


@app.post("/api/risk/blacklist/remove")
async def risk_blacklist_remove(symbol: str):
    """从黑名单移除标的。"""
    engine = _get_risk_engine()
    engine.remove_from_blacklist(symbol)
    return {"status": "removed", "symbol": symbol, "blacklist": list(engine.get_blacklist())}


@app.get("/api/risk/liquidity")
async def risk_liquidity_config():
    """获取流动性过滤配置。"""
    engine = _get_risk_engine()
    return engine.get_liquidity_config()


@app.post("/api/risk/liquidity/update")
async def risk_liquidity_update(
    min_volume: int = 10000,
    min_turnover: float = 1_000_000.0,
    enabled: bool = True,
):
    """更新流动性过滤阈值。"""
    engine = _get_risk_engine()
    engine.set_liquidity_config(
        min_volume=min_volume,
        min_turnover=min_turnover,
        enabled=enabled,
    )
    return {"status": "updated", **engine.get_liquidity_config()}


# ── Config Management (P2-10) ────────────────────────────


@app.get("/api/config")
async def config_get():
    """获取完整配置。"""
    from quant_trading.core.config import Settings

    settings = Settings.load()
    return settings.model_dump()


@app.post("/api/config/update")
async def config_update(
    section: str,
    key: str,
    value: str,
):
    """更新配置项并持久化到 settings.yaml。"""
    import yaml

    from quant_trading.core.config import Settings

    config_path = Path("config") / "settings.yaml"

    if config_path.exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}

    if section not in raw:
        raw[section] = {}

    try:
        if "." in value:
            parsed = float(value)
        else:
            parsed = int(value)
    except ValueError:
        parsed = value

    raw[section][key] = parsed

    try:
        Settings(**raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid config: {e}") from e

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True)

    if section == "risk":
        re = _get_risk_engine()
        if key == "max_position_pct":
            re._max_position_pct = Decimal(str(parsed))
        elif key == "max_single_order_pct":
            re._max_single_order_pct = Decimal(str(parsed))
        elif key == "max_daily_loss_pct":
            re._max_daily_loss_pct = Decimal(str(parsed))
        elif key == "max_order_frequency":
            re._max_order_frequency = int(parsed)

    return {"status": "saved", "section": section, "key": key, "value": parsed}


@app.post("/api/config/reset")
async def config_reset():
    """重置配置到默认值。"""
    import yaml

    from quant_trading.core.config import Settings

    defaults = Settings()
    raw = defaults.model_dump()
    config_path = Path("config") / "settings.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True)
    return {"status": "reset", "config": raw}


# ── Entrypoint ─────────────────────────────────────────────


def main():
    """quant-web 命令的入口点。"""
    import os
    import sys

    import uvicorn

    # AkShare 访问东方财富等国内站点，不需要代理。
    # 许多用户本机开启 Clash/V2Ray，会导致连接被拒。
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        os.environ.pop(k, None)
    os.environ["NO_PROXY"] = "*"

    use_reload = sys.platform != "win32"

    uvicorn.run(
        "quant_trading.interface.web.app:app",
        host="127.0.0.1",
        port=8888,
        reload=use_reload,
    )


if __name__ == "__main__":
    main()
