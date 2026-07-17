"""本地数据存储 - 使用 Parquet 文件存储行情数据，DuckDB 进行分析查询。"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import polars as pl

from quant_trading.data.adjust import AdjustType, adjust_bars
from quant_trading.model.instrument import InstrumentId
from quant_trading.model.market import Bar, BarInterval, Tick

logger = logging.getLogger(__name__)


class DataStore:
    """使用 Parquet 文件的本地数据存储，支持 DuckDB 分析查询。

    目录结构:
        data/processed/{交易所}/{标的代码}/{K线周期}/*.parquet
    """

    def __init__(self, base_dir: str | Path = "data/processed", db_path: str | None = None) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path or str(self._base_dir.parent / "quant.duckdb")
        self._conn: duckdb.DuckDBPyConnection | None = None

    def _get_path(self, instrument_id: InstrumentId, interval: BarInterval) -> Path:
        """获取指定标的和周期的存储路径。"""
        path = self._base_dir / instrument_id.exchange.value / instrument_id.symbol / interval.value
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_bars(self, instrument_id: InstrumentId, bars: list[Bar]) -> int:
        """将K线数据保存到 Parquet 文件，返回写入的行数。"""
        if not bars:
            return 0

        interval = bars[0].interval
        path = self._get_path(instrument_id, interval)

        records = [
            {
                "timestamp": bar.timestamp,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": bar.volume,
                "turnover": float(bar.turnover),
                "open_interest": bar.open_interest,
            }
            for bar in bars
        ]

        df = pl.DataFrame(records)

        # 根据日期范围确定文件名
        start_date = bars[0].timestamp.strftime("%Y%m%d")
        end_date = bars[-1].timestamp.strftime("%Y%m%d")
        filename = f"{start_date}_{end_date}.parquet"
        filepath = path / filename

        # 如果文件已存在，合并并去重
        if filepath.exists():
            existing = pl.read_parquet(filepath)
            df = pl.concat([existing, df]).unique(subset=["timestamp"]).sort("timestamp")

        df.write_parquet(filepath)
        logger.info(f"Saved {len(df)} bars to {filepath}")
        return len(df)

    def load_bars(
        self,
        instrument_id: InstrumentId,
        interval: BarInterval,
        start: datetime | None = None,
        end: datetime | None = None,
        adjust: AdjustType = AdjustType.NONE,
    ) -> list[Bar]:
        """从 Parquet 文件加载K线数据。"""
        path = self._get_path(instrument_id, interval)
        parquet_files = sorted(path.glob("*.parquet"))

        if not parquet_files:
            return []

        df = pl.read_parquet(parquet_files)

        ts_col = pl.col("timestamp")
        ts_dtype = df.schema.get("timestamp")

        # Strip timezone from timestamp column to avoid tz-aware vs naive comparison errors
        if isinstance(ts_dtype, pl.Datetime) and ts_dtype.time_zone is not None:
            df = df.with_columns(ts_col.dt.replace_time_zone(None).alias("timestamp"))
            ts_dtype = pl.Datetime("us")

        if ts_dtype == pl.Date:
            if start:
                df = df.filter(
                    ts_col >= start.date() if isinstance(start, datetime) else ts_col >= start
                )
            if end:
                df = df.filter(ts_col <= end.date() if isinstance(end, datetime) else ts_col <= end)
        else:
            if start:
                df = df.filter(ts_col >= start)
            if end:
                df = df.filter(ts_col <= end)

        df = df.sort("timestamp")

        bars = []
        for row in df.iter_rows(named=True):
            ts = row["timestamp"]
            if not isinstance(ts, datetime):
                from datetime import date as _date

                if isinstance(ts, _date):
                    ts = datetime.combine(ts, datetime.min.time())
            bars.append(
                Bar(
                    instrument_id=instrument_id,
                    timestamp=ts,
                    interval=interval,
                    open=Decimal(str(row["open"])),
                    high=Decimal(str(row["high"])),
                    low=Decimal(str(row["low"])),
                    close=Decimal(str(row["close"])),
                    volume=row["volume"],
                    turnover=Decimal(str(row["turnover"])),
                    open_interest=row["open_interest"],
                )
            )

        if adjust != AdjustType.NONE:
            bars = adjust_bars(bars, adjust_type=adjust)

        return bars

    def load_bars_df(
        self,
        instrument_id: InstrumentId,
        interval: BarInterval,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pl.DataFrame:
        """将K线数据加载为 Polars DataFrame，便于向量化分析。"""
        path = self._get_path(instrument_id, interval)
        parquet_files = sorted(path.glob("*.parquet"))

        if not parquet_files:
            return pl.DataFrame()

        df = pl.read_parquet(parquet_files)

        ts_col = pl.col("timestamp")
        ts_dtype = df.schema.get("timestamp")

        if isinstance(ts_dtype, pl.Datetime) and ts_dtype.time_zone is not None:
            df = df.with_columns(ts_col.dt.replace_time_zone(None).alias("timestamp"))
            ts_dtype = pl.Datetime("us")

        if ts_dtype == pl.Date:
            if start:
                df = df.filter(ts_col >= (start.date() if isinstance(start, datetime) else start))
            if end:
                df = df.filter(ts_col <= (end.date() if isinstance(end, datetime) else end))
        else:
            if start:
                df = df.filter(ts_col >= start)
            if end:
                df = df.filter(ts_col <= end)

        return df.sort("timestamp")

    def query(self, sql: str) -> pl.DataFrame:
        """使用 DuckDB 对存储的数据执行 SQL 查询。"""
        if self._conn is None:
            self._conn = duckdb.connect(self._db_path)
        result = self._conn.execute(sql).pl()
        return result

    def register_views(self) -> int:
        """Register all Parquet files as DuckDB views for SQL querying.
        Returns the number of views registered."""
        if self._conn is None:
            self._conn = duckdb.connect(self._db_path)
        registered = 0
        if not self._base_dir.exists():
            return 0
        for exchange_dir in self._base_dir.iterdir():
            if not exchange_dir.is_dir():
                continue
            for symbol_dir in exchange_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue
                for interval_dir in symbol_dir.iterdir():
                    if not interval_dir.is_dir():
                        continue
                    parquet_files = list(interval_dir.glob("*.parquet"))
                    if not parquet_files:
                        continue
                    view_name = f"{symbol_dir.name}_{interval_dir.name}".replace(".", "_").replace(
                        "-", "_"
                    )
                    glob_path = str(interval_dir / "*.parquet").replace("\\", "/")
                    try:
                        self._conn.execute(
                            f"CREATE OR REPLACE VIEW {view_name} AS "
                            f"SELECT * FROM read_parquet('{glob_path}')"
                        )
                        registered += 1
                    except Exception as e:
                        logger.warning(f"Failed to register view {view_name}: {e}")
        logger.info(f"Registered {registered} DuckDB views")
        return registered

    def get_catalog(self) -> list[dict]:
        """Get data catalog: list all stored datasets with metadata."""
        catalog: list[dict] = []
        if not self._base_dir.exists():
            return catalog
        for exchange_dir in self._base_dir.iterdir():
            if not exchange_dir.is_dir():
                continue
            for symbol_dir in exchange_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue
                for interval_dir in symbol_dir.iterdir():
                    if not interval_dir.is_dir():
                        continue
                    parquet_files = list(interval_dir.glob("*.parquet"))
                    if not parquet_files:
                        continue
                    total_rows = 0
                    total_size = 0
                    date_min: str | None = None
                    date_max: str | None = None
                    for pf in parquet_files:
                        total_size += pf.stat().st_size
                        try:
                            df = pl.read_parquet(pf)
                            total_rows += len(df)
                            if "timestamp" in df.columns and len(df) > 0:
                                ts = df["timestamp"]
                                d_min = str(ts.min())
                                d_max = str(ts.max())
                                if date_min is None or d_min < date_min:
                                    date_min = d_min
                                if date_max is None or d_max > date_max:
                                    date_max = d_max
                        except Exception:
                            pass
                    catalog.append(
                        {
                            "exchange": exchange_dir.name,
                            "symbol": symbol_dir.name,
                            "interval": interval_dir.name,
                            "full_id": (f"{symbol_dir.name}.{exchange_dir.name}"),
                            "files": len(parquet_files),
                            "rows": total_rows,
                            "size_kb": round(total_size / 1024, 1),
                            "date_range": (f"{date_min} ~ {date_max}" if date_min else "-"),
                        }
                    )
        return sorted(catalog, key=lambda x: x["full_id"])

    def query_safe(self, sql: str) -> dict:
        """Execute SQL query with safety checks.
        Returns dict with columns and rows."""
        if self._conn is None:
            self._conn = duckdb.connect(self._db_path)

        sql_upper = sql.strip().upper()
        allowed_prefixes = ("SELECT", "WITH", "SHOW", "DESCRIBE")
        if not sql_upper.startswith(allowed_prefixes):
            raise ValueError("Only SELECT/WITH/SHOW/DESCRIBE statements are allowed")

        self.register_views()
        if "LIMIT" not in sql_upper:
            result = self._conn.execute(sql + " LIMIT 1000")
        else:
            result = self._conn.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = []
        for row in result.fetchall():
            rows.append(
                {col: (str(val) if val is not None else None) for col, val in zip(columns, row)}
            )
        return {"columns": columns, "rows": rows, "row_count": len(rows)}

    # ------------------------------------------------------------------
    # Tick 逐笔数据存储
    # ------------------------------------------------------------------

    def _get_tick_path(self, instrument_id: InstrumentId) -> Path:
        path = self._base_dir / instrument_id.exchange.value / instrument_id.symbol / "tick"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_ticks(self, instrument_id: InstrumentId, ticks: list[Tick]) -> int:
        """将 Tick 数据保存到 Parquet 文件。"""
        if not ticks:
            return 0

        path = self._get_tick_path(instrument_id)
        records = [
            {
                "timestamp": t.timestamp,
                "last_price": float(t.last_price),
                "last_volume": t.last_volume,
                "bid_price": float(t.bid_price),
                "ask_price": float(t.ask_price),
                "bid_volume": t.bid_volume,
                "ask_volume": t.ask_volume,
                "turnover": float(t.turnover),
                "open_interest": t.open_interest,
            }
            for t in ticks
        ]

        df = pl.DataFrame(records)
        start_date = ticks[0].timestamp.strftime("%Y%m%d")
        end_date = ticks[-1].timestamp.strftime("%Y%m%d")
        filepath = path / f"{start_date}_{end_date}_tick.parquet"

        if filepath.exists():
            existing = pl.read_parquet(filepath)
            df = pl.concat([existing, df]).unique(subset=["timestamp"]).sort("timestamp")

        df.write_parquet(filepath)
        logger.info(f"Saved {len(df)} ticks to {filepath}")
        return len(df)

    def load_ticks(
        self,
        instrument_id: InstrumentId,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Tick]:
        """从 Parquet 文件加载 Tick 数据。"""
        path = self._get_tick_path(instrument_id)
        parquet_files = sorted(path.glob("*.parquet"))

        if not parquet_files:
            return []

        df = pl.read_parquet(parquet_files)

        if start:
            df = df.filter(pl.col("timestamp") >= start)
        if end:
            df = df.filter(pl.col("timestamp") <= end)

        df = df.sort("timestamp")

        ticks = []
        for row in df.iter_rows(named=True):
            ticks.append(
                Tick(
                    instrument_id=instrument_id,
                    timestamp=row["timestamp"],
                    last_price=Decimal(str(row["last_price"])),
                    last_volume=row["last_volume"],
                    bid_price=Decimal(str(row["bid_price"])),
                    ask_price=Decimal(str(row["ask_price"])),
                    bid_volume=row["bid_volume"],
                    ask_volume=row["ask_volume"],
                    turnover=Decimal(str(row["turnover"])),
                    open_interest=row["open_interest"],
                )
            )

        return ticks

    def list_instruments(self) -> list[str]:
        """列出本地已存储数据的所有交易标的。"""
        instruments = []
        if not self._base_dir.exists():
            return instruments
        for exchange_dir in self._base_dir.iterdir():
            if exchange_dir.is_dir():
                for symbol_dir in exchange_dir.iterdir():
                    if symbol_dir.is_dir():
                        instruments.append(f"{symbol_dir.name}.{exchange_dir.name}")
        return sorted(instruments)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
