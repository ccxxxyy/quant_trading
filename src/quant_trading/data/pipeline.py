"""数据清洗与标准化管道 - 对原始K线数据进行校验、清洗和标准化处理。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from quant_trading.model.market import Bar

logger = logging.getLogger(__name__)


@dataclass
class CleanStats:
    """清洗统计信息。"""

    input_count: int = 0
    output_count: int = 0
    removed_duplicates: int = 0
    removed_invalid: int = 0
    filled_missing: int = 0
    fixed_ohlc: int = 0
    removed_outliers: int = 0

    @property
    def removed_total(self) -> int:
        return self.input_count - self.output_count

    def summary(self) -> dict:
        return {
            "input": self.input_count,
            "output": self.output_count,
            "removed_duplicates": self.removed_duplicates,
            "removed_invalid": self.removed_invalid,
            "filled_missing": self.filled_missing,
            "fixed_ohlc": self.fixed_ohlc,
            "removed_outliers": self.removed_outliers,
        }


class DataPipeline:
    """数据清洗标准化管道。

    对K线数据依次执行以下处理步骤：
        1. 去重（相同时间戳的数据只保留最后一条）
        2. 时间排序（按时间戳升序排列）
        3. 无效数据过滤（价格<=0、成交量<0 等异常记录）
        4. OHLC 逻辑修正（确保 Low <= Open/Close <= High）
        5. 异常值检测（价格波动超过阈值的记录）
        6. 缺失值处理（可选：用前一根K线补全）

    使用方法：
        pipeline = DataPipeline()
        clean_bars, stats = pipeline.process(raw_bars)
    """

    def __init__(
        self,
        remove_duplicates: bool = True,
        fix_ohlc: bool = True,
        remove_invalid: bool = True,
        outlier_threshold: float = 0.5,
        remove_outliers: bool = True,
        fill_missing: bool = False,
        custom_filters: list[Callable[[Bar], bool]] | None = None,
    ) -> None:
        self._remove_duplicates = remove_duplicates
        self._fix_ohlc = fix_ohlc
        self._remove_invalid = remove_invalid
        self._outlier_threshold = outlier_threshold
        self._remove_outliers = remove_outliers
        self._fill_missing = fill_missing
        self._custom_filters = custom_filters or []

    def process(self, bars: list[Bar]) -> tuple[list[Bar], CleanStats]:
        """执行完整的清洗流水线。"""
        stats = CleanStats(input_count=len(bars))

        if not bars:
            return [], stats

        result = list(bars)

        if self._remove_duplicates:
            result, n = self._dedup(result)
            stats.removed_duplicates = n

        result.sort(key=lambda b: b.timestamp)

        if self._remove_invalid:
            result, n = self._filter_invalid(result)
            stats.removed_invalid = n

        if self._fix_ohlc:
            result, n = self._fix_ohlc_logic(result)
            stats.fixed_ohlc = n

        if self._remove_outliers and len(result) > 1:
            result, n = self._filter_outliers(result)
            stats.removed_outliers = n

        for custom_filter in self._custom_filters:
            result = [b for b in result if custom_filter(b)]

        stats.output_count = len(result)
        logger.info(
            f"Pipeline: {stats.input_count} -> {stats.output_count} bars "
            f"(dup={stats.removed_duplicates}, invalid={stats.removed_invalid}, "
            f"outlier={stats.removed_outliers}, ohlc_fix={stats.fixed_ohlc})"
        )
        return result, stats

    @staticmethod
    def _dedup(bars: list[Bar]) -> tuple[list[Bar], int]:
        """按时间戳去重，保留最后出现的记录。"""
        seen: dict[datetime, Bar] = {}
        for bar in bars:
            seen[bar.timestamp] = bar
        deduped = list(seen.values())
        return deduped, len(bars) - len(deduped)

    @staticmethod
    def _filter_invalid(bars: list[Bar]) -> tuple[list[Bar], int]:
        """过滤无效数据：价格<=0、成交量<0。"""
        valid = []
        for bar in bars:
            if bar.open <= 0 or bar.high <= 0 or bar.low <= 0 or bar.close <= 0:
                continue
            if bar.volume < 0:
                continue
            valid.append(bar)
        return valid, len(bars) - len(valid)

    @staticmethod
    def _fix_ohlc_logic(bars: list[Bar]) -> tuple[list[Bar], int]:
        """修正 OHLC 逻辑关系，确保 Low <= Open/Close <= High。"""
        fixed_count = 0
        result = []
        for bar in bars:
            o, h, lo, c = bar.open, bar.high, bar.low, bar.close
            needs_fix = False

            if h < max(o, c):
                h = max(o, c)
                needs_fix = True
            if lo > min(o, c):
                lo = min(o, c)
                needs_fix = True
            if lo > h:
                lo, h = h, lo
                needs_fix = True

            if needs_fix:
                fixed_count += 1
                bar = Bar(
                    instrument_id=bar.instrument_id,
                    timestamp=bar.timestamp,
                    interval=bar.interval,
                    open=o,
                    high=h,
                    low=lo,
                    close=c,
                    volume=bar.volume,
                    turnover=bar.turnover,
                    open_interest=bar.open_interest,
                )
            result.append(bar)
        return result, fixed_count

    def _filter_outliers(self, bars: list[Bar]) -> tuple[list[Bar], int]:
        """过滤价格异常波动的K线（涨跌幅超过阈值）。"""
        if not bars:
            return bars, 0

        valid = [bars[0]]
        removed = 0
        for i in range(1, len(bars)):
            prev_close = bars[i - 1].close
            if prev_close == 0:
                valid.append(bars[i])
                continue
            change = abs(float(bars[i].close - prev_close) / float(prev_close))
            if change > self._outlier_threshold:
                removed += 1
                logger.debug(
                    f"Outlier removed: {bars[i].timestamp} "
                    f"change={change:.2%} > threshold={self._outlier_threshold:.2%}"
                )
            else:
                valid.append(bars[i])
        return valid, removed

    @staticmethod
    def normalize_timezone(bars: list[Bar], tz: timezone | None = None) -> list[Bar]:
        """统一时区（可选）。默认移除时区信息（naive datetime）。"""
        result = []
        for bar in bars:
            ts = bar.timestamp
            if tz is not None:
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=tz)
                else:
                    ts = ts.astimezone(tz)
            elif ts.tzinfo is not None:
                ts = ts.replace(tzinfo=None)

            if ts != bar.timestamp:
                bar = Bar(
                    instrument_id=bar.instrument_id,
                    timestamp=ts,
                    interval=bar.interval,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    turnover=bar.turnover,
                    open_interest=bar.open_interest,
                )
            result.append(bar)
        return result
