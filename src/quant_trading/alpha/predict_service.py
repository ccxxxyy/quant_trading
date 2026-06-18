"""预测服务 - 模型加载、批量预测与策略集成接口。"""

from __future__ import annotations

import logging
from pathlib import Path

from quant_trading.alpha.feature import FeatureEngine
from quant_trading.alpha.model import AlphaPipeline, BaseModel, LightGBMModel
from quant_trading.model.market import Bar

logger = logging.getLogger(__name__)


class PredictService:
    """AI 预测服务。

    提供模型加载、特征计算和预测的统一接口，
    可被策略或 Web API 调用。

    使用流程：
        1. 加载或训练模型
        2. 输入最新K线数据
        3. 自动计算特征 → 调用模型预测 → 返回信号

    使用示例：
        service = PredictService()
        service.load_model("models/lgbm_600519.pkl")

        signal = service.predict_signal(bars[-60:])
        # signal > 0 → 看多, signal < 0 → 看空
    """

    def __init__(self, model: BaseModel | None = None) -> None:
        self._model = model
        self._feature_engine = FeatureEngine()
        self._feature_engine.register_defaults()
        self._pipeline: AlphaPipeline | None = None

    def load_model(self, path: str | Path) -> None:
        """从文件加载已训练的模型。"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Model file not found: {path}")

        model = LightGBMModel()
        model.load(str(path))
        self._model = model
        logger.info(f"Model loaded from {path}")

    def train(
        self,
        bars: list[Bar],
        target_column: str = "future_return",
        lookahead: int = 5,
    ) -> dict[str, float]:
        """用K线数据训练新模型。

        参数：
            bars: 历史K线数据
            target_column: 目标变量名
            lookahead: 预测未来几期的收益率

        返回：
            训练指标
        """
        self._pipeline = AlphaPipeline(
            feature_engine=self._feature_engine,
            model=LightGBMModel(),
        )

        dataset = self._pipeline.prepare_dataset(bars, lookahead=lookahead)
        if dataset is None or len(dataset) < 100:
            raise ValueError("Insufficient data for training (need at least 100 bars)")

        metrics = self._pipeline.train(dataset)
        self._model = self._pipeline._model
        logger.info(f"Model trained: {metrics}")
        return metrics

    def predict_signal(self, recent_bars: list[Bar]) -> float:
        """基于最近K线数据预测信号。

        参数：
            recent_bars: 最近N根K线（建议60根以上）

        返回：
            预测信号值（正数看多、负数看空）
        """
        if self._model is None:
            raise RuntimeError("No model loaded. Call load_model() or train() first.")

        features = self._feature_engine.compute_features(recent_bars)
        if not features:
            return 0.0

        latest_features = features[-1]
        feature_values = list(latest_features.values())

        import numpy as np

        X = np.array([feature_values])
        prediction = self._model.predict(X)

        return float(prediction[0]) if len(prediction) > 0 else 0.0

    def predict_batch(self, bars: list[Bar]) -> list[float]:
        """批量预测所有K线的信号。"""
        if self._model is None:
            raise RuntimeError("No model loaded.")

        features = self._feature_engine.compute_features(bars)
        if not features:
            return []

        import numpy as np

        X = np.array([[v for v in f.values()] for f in features])
        return self._model.predict(X).tolist()

    def save_model(self, path: str | Path) -> None:
        """保存当前模型到文件。"""
        if self._model is None:
            raise RuntimeError("No model to save.")
        self._model.save(str(path))
        logger.info(f"Model saved to {path}")

    @property
    def is_ready(self) -> bool:
        """模型是否已加载可用。"""
        return self._model is not None

    def get_feature_names(self) -> list[str]:
        """获取当前使用的特征名列表。"""
        return list(self._feature_engine._factors.keys())
