"""因子工程 - Alpha 因子计算和特征管理。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)


class BaseFactor(ABC):
    """Alpha 因子计算的抽象基类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """因子的唯一名称。"""
        ...

    @property
    def dependencies(self) -> list[str]:
        """该因子依赖的数据列名列表。"""
        return ["close"]

    @abstractmethod
    def compute(self, df: pl.DataFrame) -> pl.Series:
        """从K线 DataFrame 计算因子值。

        输入 DataFrame 包含列：timestamp, open, high, low, close, volume, turnover
        返回一个 pl.Series，包含计算后的因子值。
        """
        ...


class MomentumFactor(BaseFactor):
    """N 周期价格动量因子（区间收益率）。"""

    def __init__(self, period: int = 20) -> None:
        self._period = period

    @property
    def name(self) -> str:
        return f"momentum_{self._period}"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        return (pl.col("close") / pl.col("close").shift(self._period) - 1).alias(self.name)


class VolatilityFactor(BaseFactor):
    """滚动波动率因子（收益率的标准差）。"""

    def __init__(self, period: int = 20) -> None:
        self._period = period

    @property
    def name(self) -> str:
        return f"volatility_{self._period}"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        return pl.col("close").pct_change().rolling_std(window_size=self._period).alias(self.name)


class RSIFactor(BaseFactor):
    """RSI 相对强弱指标因子。"""

    def __init__(self, period: int = 14) -> None:
        self._period = period

    @property
    def name(self) -> str:
        return f"rsi_{self._period}"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        delta = pl.col("close").diff()
        gain = delta.clip(lower_bound=0).rolling_mean(window_size=self._period)
        loss = (-delta.clip(upper_bound=0)).rolling_mean(window_size=self._period)
        # loss=0 时 rs 会 inf；统一落成可 JSON 序列化的 null
        rs = pl.when(loss.is_null() | (loss == 0)).then(None).otherwise(gain / loss)
        return (100 - 100 / (1 + rs)).alias(self.name)


class VolumeRatioFactor(BaseFactor):
    """量比因子（当前成交量相对于 N 周期平均成交量的倍数）。"""

    def __init__(self, period: int = 20) -> None:
        self._period = period

    @property
    def name(self) -> str:
        return f"volume_ratio_{self._period}"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        avg = pl.col("volume").rolling_mean(window_size=self._period)
        # 场外基金等成交量恒为 0 时，量比无意义，避免 0/0 → NaN 导致 JSON 序列化失败
        return (
            pl.when(avg.is_null() | (avg == 0))
            .then(None)
            .otherwise(pl.col("volume") / avg)
            .alias(self.name)
        )


class FeatureEngine:
    """因子计算和特征管理引擎。"""

    def __init__(self) -> None:
        self._factors: dict[str, BaseFactor] = {}

    def register_factor(self, factor: BaseFactor) -> None:
        """注册一个因子用于计算。"""
        self._factors[factor.name] = factor

    def register_defaults(self) -> None:
        """注册一组默认的常用因子。"""
        defaults = [
            MomentumFactor(5),
            MomentumFactor(10),
            MomentumFactor(20),
            VolatilityFactor(10),
            VolatilityFactor(20),
            RSIFactor(14),
            VolumeRatioFactor(20),
        ]
        for factor in defaults:
            self.register_factor(factor)

    def compute_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """对K线 DataFrame 计算所有已注册的因子。"""
        result = df.clone()
        for name, factor in self._factors.items():
            try:
                expr = factor.compute(df)
                result = result.with_columns(expr)
            except Exception as e:
                logger.warning(f"Error computing factor {name}: {e}")
        # NaN/Inf 不能进 JSON；统一成 null
        float_cols = [
            c
            for c, dt in zip(result.columns, result.dtypes, strict=False)
            if getattr(dt, "is_float", lambda: False)()
        ]
        if float_cols:
            result = result.with_columns(
                [
                    pl.when(pl.col(c).is_nan() | pl.col(c).is_infinite())
                    .then(None)
                    .otherwise(pl.col(c))
                    .alias(c)
                    for c in float_cols
                ]
            )
        return result

    @property
    def factor_names(self) -> list[str]:
        return list(self._factors.keys())

    def cache_features(self, symbol: str, interval: str, df: pl.DataFrame) -> int:
        """Cache computed features to Parquet file. Returns rows cached."""
        cache_dir = Path("data/factors") / symbol / interval
        cache_dir.mkdir(parents=True, exist_ok=True)
        filepath = cache_dir / "features.parquet"
        df.write_parquet(filepath)
        logger.info(f"Cached {len(df)} rows of features to {filepath}")
        return len(df)

    def load_cached_features(self, symbol: str, interval: str) -> pl.DataFrame | None:
        """Load cached features. Returns None if no cache exists."""
        filepath = Path("data/factors") / symbol / interval / "features.parquet"
        if filepath.exists():
            return pl.read_parquet(filepath)
        return None

    def list_cached(self) -> list[dict]:
        """List all cached factor files with metadata."""
        cache_root = Path("data/factors")
        if not cache_root.exists():
            return []
        result = []
        for symbol_dir in sorted(cache_root.iterdir()):
            if not symbol_dir.is_dir():
                continue
            for interval_dir in sorted(symbol_dir.iterdir()):
                if not interval_dir.is_dir():
                    continue
                fp = interval_dir / "features.parquet"
                if fp.exists():
                    try:
                        df = pl.read_parquet(fp)
                        ohlcv = (
                            "timestamp",
                            "open",
                            "high",
                            "low",
                            "close",
                            "volume",
                            "turnover",
                        )
                        result.append(
                            {
                                "symbol": symbol_dir.name,
                                "interval": interval_dir.name,
                                "rows": len(df),
                                "columns": len(df.columns),
                                "factors": [c for c in df.columns if c not in ohlcv],
                                "size_kb": round(fp.stat().st_size / 1024, 1),
                            }
                        )
                    except Exception:
                        pass
        return result

    def clear_cache(self, symbol: str | None = None) -> int:
        """Clear cached factor files. Returns files deleted."""
        import shutil

        cache_root = Path("data/factors")
        if not cache_root.exists():
            return 0
        deleted = 0
        if symbol:
            target = cache_root / symbol
            if target.exists():
                shutil.rmtree(target)
                deleted = 1
        else:
            for d in list(cache_root.iterdir()):
                if d.is_dir():
                    shutil.rmtree(d)
                    deleted += 1
        return deleted
