"""AkShare 数据源 - 免费获取A股和中国期货市场的行情数据。"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from quant_trading.data.feed import DataFeed
from quant_trading.model.instrument import Exchange, InstrumentId
from quant_trading.model.market import Bar, BarInterval

logger = logging.getLogger(__name__)

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
    """基于 AkShare 的中国股票和期货数据源。

    支持市场：A股（上交所SSE/深交所SZSE）、中国期货（上期所/大商所/郑商所/中金所）。
    """

    @property
    def name(self) -> str:
        return "akshare"

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

        symbol = instrument_id.symbol
        exchange = instrument_id.exchange
        end = end or datetime.now()

        if exchange in (Exchange.SSE, Exchange.SZSE):
            return await self._fetch_stock_bars(ak, symbol, interval, start, end, instrument_id)
        elif exchange in (Exchange.SHFE, Exchange.DCE, Exchange.CZCE, Exchange.CFFEX):
            return await self._fetch_futures_bars(ak, symbol, interval, start, end, instrument_id)
        else:
            raise ValueError(f"AkShare does not support exchange: {exchange}")

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
        except Exception as e:
            logger.error(f"AkShare fetch error for {symbol}: {e}")
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
