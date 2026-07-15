"""AkShare 数据源 - 免费获取A股/期货/指数/可转债/期权的行情数据。"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from decimal import Decimal

from quant_trading.data.feed import DataFeed
from quant_trading.model.instrument import Exchange, InstrumentId
from quant_trading.model.market import Bar, BarInterval, Tick

logger = logging.getLogger(__name__)

_EASTMONEY_DOMAINS = (
    "push2his.eastmoney.com",
    "push2.eastmoney.com",
    "datacenter-web.eastmoney.com",
    "quote.eastmoney.com",
    "data.eastmoney.com",
)


def _disable_proxy_for_akshare():
    """永久绕过系统代理——AkShare 只访问东方财富等国内站点，不需要代理。

    许多用户本机开启了 Clash/V2Ray 等代理（如 Clash 的 127.0.0.1:7897），
    会导致 requests 库走代理后连接东方财富被拒。

    此函数通过三层策略确保绕过：
    1. 清除环境变量中的代理设置
    2. monkey-patch urllib.request.getproxies 阻止从注册表读取代理
    3. monkey-patch requests.Session.__init__ 强制 trust_env=False
    """
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        os.environ.pop(k, None)
    os.environ["NO_PROXY"] = "*"

    try:
        import urllib.request

        urllib.request.getproxies = lambda: {}  # type: ignore[assignment]
    except Exception:
        pass

    try:
        import requests
        import requests.utils

        requests.utils.getproxies = lambda: {}  # type: ignore[assignment]

        _orig_session_init = requests.Session.__init__

        def _patched_session_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            _orig_session_init(self, *args, **kwargs)
            self.trust_env = False
            self.proxies = {}

        if not getattr(_patched_session_init, "_proxy_patched", False):
            _patched_session_init._proxy_patched = True  # type: ignore[attr-defined]
            requests.Session.__init__ = _patched_session_init  # type: ignore[assignment]
    except Exception:
        pass


_disable_proxy_for_akshare()


def _ensure_no_proxy():
    """确保当前进程无代理设置——每次 AkShare 调用前执行。"""
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        os.environ.pop(k, None)
    os.environ["NO_PROXY"] = "*"


_INTERVAL_MAP = {
    BarInterval.MINUTE_1: "1",
    BarInterval.MINUTE_5: "5",
    BarInterval.MINUTE_15: "15",
    BarInterval.MINUTE_30: "30",
    BarInterval.HOUR_1: "60",
    BarInterval.DAILY: "daily",
    BarInterval.WEEKLY: "weekly",
}


class AkShareFeed(DataFeed):
    """基于 AkShare 的中国市场数据源。

    支持市场：
    - A股（SSE/SZSE）：股票、ETF
    - 指数（SSE/SZSE）：上证指数、沪深300 等（代码以 0/3/9 开头的6位数字）
    - 可转债（SSE/SZSE）：代码以 11/12 开头的6位数字
    - 期权（SSE/SZSE）：通过 AkShare 期权行情接口
    - 期货（SHFE/DCE/CZCE/CFFEX）
    - Tick 逐笔数据：A 股实时快照
    """

    @property
    def name(self) -> str:
        return "akshare"

    @staticmethod
    def _is_index(symbol: str) -> bool:
        """判断是否为指数代码（如 000001=上证指数, 399001=深成指, 000300=沪深300）。"""
        return symbol.startswith(("000", "399", "9")) and len(symbol) == 6

    @staticmethod
    def _is_convertible_bond(symbol: str) -> bool:
        """判断是否为可转债代码（11xxxx=沪市可转债, 12xxxx=深市可转债）。"""
        return symbol.startswith(("11", "12")) and len(symbol) == 6

    @staticmethod
    def _is_option(symbol: str) -> bool:
        """判断是否为期权代码（一般为8位以上含月份合约）。"""
        return len(symbol) >= 8 and not symbol.isdigit()

    async def get_bars(
        self,
        instrument_id: InstrumentId,
        interval: BarInterval,
        start: datetime,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[Bar]:
        """通过 AkShare 获取历史K线数据。"""
        try:
            import akshare as ak
        except ImportError:
            raise ImportError("akshare is required: pip install quant-trading[data]")

        _ensure_no_proxy()
        return await self._get_bars_impl(ak, instrument_id, interval, start, end)

    async def _get_bars_impl(self, ak, instrument_id, interval, start, end):
        """实际的数据获取逻辑（在 _bypass_proxy 上下文中调用）。"""

        symbol = instrument_id.symbol
        exchange = instrument_id.exchange
        end = end or datetime.now()

        if exchange in (Exchange.SSE, Exchange.SZSE):
            if self._is_index(symbol):
                return await self._fetch_index_bars(ak, symbol, interval, start, end, instrument_id)
            elif self._is_convertible_bond(symbol):
                return await self._fetch_cb_bars(ak, symbol, interval, start, end, instrument_id)
            elif self._is_option(symbol):
                return await self._fetch_option_bars(
                    ak, symbol, interval, start, end, instrument_id
                )
            else:
                return await self._fetch_stock_bars(ak, symbol, interval, start, end, instrument_id)
        elif exchange in (Exchange.SHFE, Exchange.DCE, Exchange.CZCE, Exchange.CFFEX):
            return await self._fetch_futures_bars(ak, symbol, interval, start, end, instrument_id)
        else:
            raise ValueError(f"AkShare does not support exchange: {exchange}")

    async def get_ticks(
        self,
        instrument_id: InstrumentId,
        start: datetime,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[Tick]:
        """获取 A 股实时 Tick 快照（通过 AkShare 实时行情接口）。"""
        try:
            import akshare as ak
        except ImportError:
            raise ImportError("akshare is required: pip install quant-trading[data]")

        symbol = instrument_id.symbol
        try:
            _ensure_no_proxy()
            df = ak.stock_zh_a_spot_em()
            row = df[df["代码"] == symbol]
            if row.empty:
                return []

            r = row.iloc[0]
            tick = Tick(
                instrument_id=instrument_id,
                timestamp=datetime.now(),
                last_price=Decimal(str(r.get("最新价", 0))),
                last_volume=int(r.get("成交量", 0)),
                bid_price=Decimal(str(r.get("买入价", r.get("最新价", 0)))),
                ask_price=Decimal(str(r.get("卖出价", r.get("最新价", 0)))),
                bid_volume=int(r.get("买入量", 0)),
                ask_volume=int(r.get("卖出量", 0)),
                turnover=Decimal(str(r.get("成交额", 0))),
            )
            return [tick]
        except Exception as e:
            logger.error(f"AkShare tick fetch error for {symbol}: {e}")
            return []

    async def _fetch_stock_bars(
        self,
        ak,
        symbol: str,
        interval: BarInterval,
        start: datetime,
        end: datetime,
        instrument_id: InstrumentId,
    ) -> list[Bar]:
        """获取A股股票/ETF的K线数据。"""
        period = _INTERVAL_MAP.get(interval)
        if not period:
            raise ValueError(f"Unsupported interval for AkShare stocks: {interval}")

        import time

        max_retries = 3
        df = None
        for attempt in range(max_retries):
            _ensure_no_proxy()
            try:
                if interval == BarInterval.DAILY:
                    df = ak.stock_zh_a_hist(
                        symbol=symbol,
                        period="daily",
                        start_date=start.strftime("%Y%m%d"),
                        end_date=end.strftime("%Y%m%d"),
                        adjust="qfq",
                    )
                else:
                    df = ak.stock_zh_a_hist_min_em(
                        symbol=symbol,
                        period=period,
                        start_date=start.strftime("%Y-%m-%d %H:%M:%S"),
                        end_date=end.strftime("%Y-%m-%d %H:%M:%S"),
                        adjust="qfq",
                    )
                break
            except Exception as e:
                logger.warning(
                    f"AkShare fetch attempt {attempt + 1}/{max_retries} for {symbol}: {e}"
                )
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))
                else:
                    err_str = str(e)
                    if "RemoteDisconnected" in err_str or "ProxyError" in err_str:
                        logger.error(
                            f"AkShare fetch failed for {symbol}: 网络连接被拒。"
                            f"如果你正在使用 Clash/V2Ray 等代理软件，"
                            f"请关闭 TUN 模式或将 eastmoney.com 添加到直连规则中。"
                        )
                    else:
                        logger.error(
                            f"AkShare fetch failed after {max_retries} retries for {symbol}: {e}"
                        )
                    return []

        if df is None or df.empty:
            return []

        bars = []
        for _, row in df.iterrows():
            try:
                ts_col = "日期" if "日期" in df.columns else "时间"
                timestamp = row[ts_col]
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp)

                bars.append(
                    Bar(
                        instrument_id=instrument_id,
                        timestamp=timestamp,
                        interval=interval,
                        open=Decimal(str(row["开盘"])),
                        high=Decimal(str(row["最高"])),
                        low=Decimal(str(row["最低"])),
                        close=Decimal(str(row["收盘"])),
                        volume=int(row["成交量"]),
                        turnover=Decimal(str(row.get("成交额", 0))),
                    )
                )
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping row due to parse error: {e}")
                continue

        logger.info(f"Fetched {len(bars)} bars for {instrument_id} from AkShare")
        return bars

    async def _fetch_futures_bars(
        self,
        ak,
        symbol: str,
        interval: BarInterval,
        start: datetime,
        end: datetime,
        instrument_id: InstrumentId,
    ) -> list[Bar]:
        """获取中国期货的K线数据。"""
        try:
            if interval == BarInterval.DAILY:
                df = ak.futures_zh_daily_sina(symbol=symbol)
            else:
                period_map = {"1": "1", "5": "5", "15": "15", "30": "30", "60": "60"}
                period = _INTERVAL_MAP.get(interval, "5")
                df = ak.futures_zh_minute_sina(symbol=symbol, period=period_map.get(period, "5"))
        except Exception as e:
            logger.error(f"AkShare futures fetch error for {symbol}: {e}")
            return []

        if df is None or df.empty:
            return []

        bars = []
        for _, row in df.iterrows():
            try:
                timestamp = row.get("date") or row.get("datetime") or row.name
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp)

                bars.append(
                    Bar(
                        instrument_id=instrument_id,
                        timestamp=timestamp,
                        interval=interval,
                        open=Decimal(str(row["open"])),
                        high=Decimal(str(row["high"])),
                        low=Decimal(str(row["low"])),
                        close=Decimal(str(row["close"])),
                        volume=int(row.get("volume", 0)),
                        turnover=Decimal(str(row.get("hold", 0))),
                    )
                )
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping futures row: {e}")
                continue

        # 按日期范围过滤
        bars = [b for b in bars if start <= b.timestamp <= end]
        logger.info(f"Fetched {len(bars)} futures bars for {instrument_id} from AkShare")
        return bars

    # ------------------------------------------------------------------
    # 指数数据
    # ------------------------------------------------------------------

    async def _fetch_index_bars(
        self,
        ak,
        symbol: str,
        interval: BarInterval,
        start: datetime,
        end: datetime,
        instrument_id: InstrumentId,
    ) -> list[Bar]:
        """获取指数K线数据（上证指数、沪深300等）。"""
        try:
            if interval == BarInterval.DAILY:
                df = ak.stock_zh_index_daily_em(
                    symbol=f"sh{symbol}" if symbol.startswith("0") else f"sz{symbol}"
                )
            else:
                period = _INTERVAL_MAP.get(interval, "5")
                df = ak.stock_zh_index_hist_min_em(
                    symbol=symbol,
                    period=period,
                    start_date=start.strftime("%Y-%m-%d %H:%M:%S"),
                    end_date=end.strftime("%Y-%m-%d %H:%M:%S"),
                )
        except Exception as e:
            logger.error(f"AkShare index fetch error for {symbol}: {e}")
            return []

        if df is None or df.empty:
            return []

        return self._df_to_bars(df, instrument_id, interval, start, end)

    # ------------------------------------------------------------------
    # 可转债数据
    # ------------------------------------------------------------------

    async def _fetch_cb_bars(
        self,
        ak,
        symbol: str,
        interval: BarInterval,
        start: datetime,
        end: datetime,
        instrument_id: InstrumentId,
    ) -> list[Bar]:
        """获取可转债K线数据。"""
        try:
            if interval == BarInterval.DAILY:
                df = ak.bond_zh_hs_cov_daily(
                    symbol=f"sh{symbol}" if symbol.startswith("11") else f"sz{symbol}"
                )
            else:
                df = ak.bond_zh_hs_cov_min(
                    symbol=symbol,
                    period=_INTERVAL_MAP.get(interval, "5"),
                )
        except Exception as e:
            logger.error(f"AkShare convertible bond fetch error for {symbol}: {e}")
            return []

        if df is None or df.empty:
            return []

        return self._df_to_bars(df, instrument_id, interval, start, end)

    # ------------------------------------------------------------------
    # 期权数据
    # ------------------------------------------------------------------

    async def _fetch_option_bars(
        self,
        ak,
        symbol: str,
        interval: BarInterval,
        start: datetime,
        end: datetime,
        instrument_id: InstrumentId,
    ) -> list[Bar]:
        """获取期权合约K线数据。"""
        try:
            df = ak.option_sse_daily(symbol=symbol)
        except Exception as e:
            logger.error(f"AkShare option fetch error for {symbol}: {e}")
            return []

        if df is None or df.empty:
            return []

        return self._df_to_bars(df, instrument_id, interval, start, end)

    # ------------------------------------------------------------------
    # 通用 DataFrame → Bar 转换
    # ------------------------------------------------------------------

    def _df_to_bars(
        self,
        df,
        instrument_id: InstrumentId,
        interval: BarInterval,
        start: datetime,
        end: datetime,
    ) -> list[Bar]:
        """将 AkShare 返回的 DataFrame 统一转为 Bar 列表。"""
        col_map = {
            "日期": "ts",
            "时间": "ts",
            "date": "ts",
            "datetime": "ts",
            "开盘": "open",
            "open": "open",
            "开盘价": "open",
            "最高": "high",
            "high": "high",
            "最高价": "high",
            "最低": "low",
            "low": "low",
            "最低价": "low",
            "收盘": "close",
            "close": "close",
            "收盘价": "close",
            "成交量": "volume",
            "volume": "volume",
            "vol": "volume",
            "成交额": "turnover",
            "amount": "turnover",
            "turnover": "turnover",
        }

        ts_col = None
        for c in df.columns:
            if col_map.get(c) == "ts":
                ts_col = c
                break

        def _find(target: str):
            for c in df.columns:
                if col_map.get(c) == target:
                    return c
            return None

        o_col = _find("open")
        h_col = _find("high")
        l_col = _find("low")
        c_col = _find("close")
        v_col = _find("volume")
        t_col = _find("turnover")

        if not all([ts_col, o_col, h_col, l_col, c_col]):
            logger.warning(f"Cannot map columns in DataFrame: {list(df.columns)}")
            return []

        bars: list[Bar] = []
        for _, row in df.iterrows():
            try:
                timestamp = row[ts_col]
                if isinstance(timestamp, str):
                    timestamp = datetime.fromisoformat(timestamp)

                bars.append(
                    Bar(
                        instrument_id=instrument_id,
                        timestamp=timestamp,
                        interval=interval,
                        open=Decimal(str(row[o_col])),
                        high=Decimal(str(row[h_col])),
                        low=Decimal(str(row[l_col])),
                        close=Decimal(str(row[c_col])),
                        volume=int(row[v_col]) if v_col else 0,
                        turnover=Decimal(str(row[t_col])) if t_col else Decimal(0),
                    )
                )
            except (KeyError, ValueError, TypeError) as e:
                logger.debug(f"Skipping row: {e}")
                continue

        bars = [b for b in bars if start <= b.timestamp <= end]
        logger.info(f"Fetched {len(bars)} bars for {instrument_id} from AkShare")
        return bars
