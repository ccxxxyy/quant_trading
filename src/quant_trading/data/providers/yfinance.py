"""Yahoo Finance 数据源 - 获取美股和全球市场的行情数据。"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from quant_trading.data.feed import DataFeed
from quant_trading.model.instrument import InstrumentId
from quant_trading.model.market import Bar, BarInterval

logger = logging.getLogger(__name__)

_INTERVAL_MAP = {
    BarInterval.MINUTE_1: "1m",
    BarInterval.MINUTE_5: "5m",
    BarInterval.MINUTE_15: "15m",
    BarInterval.MINUTE_30: "30m",
    BarInterval.HOUR_1: "1h",
    BarInterval.DAILY: "1d",
    BarInterval.WEEKLY: "1wk",
}


class YFinanceFeed(DataFeed):
    """基于 yfinance 的美股和全球市场数据源。

    支持市场：NYSE、NASDAQ，以及 Yahoo Finance 覆盖的大多数国际交易所。
    """

    @property
    def name(self) -> str:
        return "yfinance"

    async def get_bars(
        self,
        instrument_id: InstrumentId,
        interval: BarInterval,
        start: datetime,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[Bar]:
        """通过 yfinance 获取历史K线数据。"""
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("yfinance is required: pip install quant-trading[data]")

        yf_interval = _INTERVAL_MAP.get(interval)
        if not yf_interval:
            raise ValueError(f"Unsupported interval for yfinance: {interval}")

        symbol = instrument_id.symbol
        end = end or datetime.now()

        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                interval=yf_interval,
            )
        except Exception as e:
            logger.error(f"yfinance fetch error for {symbol}: {e}")
            return []

        if df is None or df.empty:
            return []

        bars = []
        for timestamp, row in df.iterrows():
            try:
                ts = timestamp.to_pydatetime()
                bars.append(
                    Bar(
                        instrument_id=instrument_id,
                        timestamp=ts,
                        interval=interval,
                        open=Decimal(str(round(row["Open"], 4))),
                        high=Decimal(str(round(row["High"], 4))),
                        low=Decimal(str(round(row["Low"], 4))),
                        close=Decimal(str(round(row["Close"], 4))),
                        volume=int(row["Volume"]),
                        turnover=Decimal(0),
                    )
                )
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping row: {e}")
                continue

        if limit:
            bars = bars[-limit:]

        logger.info(f"Fetched {len(bars)} bars for {instrument_id} from yfinance")
        return bars
