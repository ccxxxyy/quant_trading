"""因子工程 - Alpha 因子计算和特征管理。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

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
        rs = gain / loss
        return (100 - 100 / (1 + rs)).alias(self.name)


class VolumeRatioFactor(BaseFactor):
    """量比因子（当前成交量相对于 N 周期平均成交量的倍数）。"""

    def __init__(self, period: int = 20) -> None:
        self._period = period

    @property
    def name(self) -> str:
        return f"volume_ratio_{self._period}"

    def compute(self, df: pl.DataFrame) -> pl.Series:
        return (pl.col("volume") / pl.col("volume").rolling_mean(window_size=self._period)).alias(
            self.name
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
        return result

    @property
    def factor_names(self) -> list[str]:
        return list(self._factors.keys())
