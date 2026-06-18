"""机器学习模型接口 - 统一的训练和预测 API。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

import polars as pl

logger = logging.getLogger(__name__)


class BaseModel(ABC):
    """预测模型的抽象基类。"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def fit(self, X: pl.DataFrame, y: pl.Series) -> None:
        """训练模型。"""
        ...

    @abstractmethod
    def predict(self, X: pl.DataFrame) -> pl.Series:
        """生成预测结果。"""
        ...

    def save(self, path: str | Path) -> None:
        """将模型保存到磁盘。"""
        raise NotImplementedError

    def load(self, path: str | Path) -> None:
        """从磁盘加载模型。"""
        raise NotImplementedError


class LightGBMModel(BaseModel):
    """LightGBM 模型，适用于金融表格数据的 Alpha 预测。"""

    def __init__(self, params: dict | None = None) -> None:
        self._params = params or {
            "objective": "regression",
            "metric": "mse",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "n_estimators": 200,
            "verbose": -1,
        }
        self._model = None

    @property
    def name(self) -> str:
        return "lightgbm"

    def fit(self, X: pl.DataFrame, y: pl.Series) -> None:
        try:
            import lightgbm as lgb
        except ImportError:
            raise ImportError("lightgbm required: pip install quant-trading[ml]")

        X_np = X.to_numpy()
        y_np = y.to_numpy()

        self._model = lgb.LGBMRegressor(**self._params)
        self._model.fit(X_np, y_np)
        logger.info(f"LightGBM model trained on {len(X)} samples")

    def predict(self, X: pl.DataFrame) -> pl.Series:
        if self._model is None:
            raise RuntimeError("Model not trained")
        preds = self._model.predict(X.to_numpy())
        return pl.Series("prediction", preds)

    def save(self, path: str | Path) -> None:
        if self._model is None:
            raise RuntimeError("No model to save")
        import joblib

        joblib.dump(self._model, str(path))

    def load(self, path: str | Path) -> None:
        import joblib

        self._model = joblib.load(str(path))

    @property
    def feature_importance(self) -> dict[str, float] | None:
        """获取特征重要性（训练后可用）。"""
        if self._model is None:
            return None
        return dict(
            zip(
                self._model.feature_name_,
                self._model.feature_importances_.tolist(),
            )
        )


class AlphaPipeline:
    """端到端 Alpha 流水线：特征 → 模型训练 → 预测。"""

    def __init__(self, model: BaseModel) -> None:
        self._model = model
        self._feature_columns: list[str] = []
        self._target_column: str = "target"

    def prepare_dataset(
        self,
        df: pl.DataFrame,
        feature_columns: list[str],
        target_column: str = "target",
        forward_return_period: int = 5,
    ) -> tuple[pl.DataFrame, pl.Series]:
        """准备训练数据集（特征和目标变量）。

        默认目标变量为未来 N 期的收益率。
        """
        self._feature_columns = feature_columns
        self._target_column = target_column

        # 如果目标列不存在，自动计算未来N期收益率作为目标
        if target_column not in df.columns:
            df = df.with_columns(
                (pl.col("close").shift(-forward_return_period) / pl.col("close") - 1).alias(
                    target_column
                )
            )

        # 删除含空值的行
        df_clean = df.drop_nulls(subset=feature_columns + [target_column])

        X = df_clean.select(feature_columns)
        y = df_clean[target_column]
        return X, y

    def train(self, X: pl.DataFrame, y: pl.Series) -> None:
        self._model.fit(X, y)

    def predict(self, df: pl.DataFrame) -> pl.Series:
        X = df.select(self._feature_columns)
        return self._model.predict(X)
