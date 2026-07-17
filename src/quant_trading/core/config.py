"""配置管理 - 使用 Pydantic 进行类型安全的配置校验。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class SystemConfig(BaseModel):
    name: str = "QuantTrading"
    log_level: str = "INFO"
    timezone: str = "Asia/Shanghai"
    data_dir: str = "./data"


class DataConfig(BaseModel):
    default_store: str = "parquet"
    parquet_dir: str = "./data/processed"
    duckdb_path: str = "./data/quant.duckdb"


class RiskConfig(BaseModel):
    max_position_pct: float = Field(default=0.25, ge=0, le=1.0)
    max_single_order_pct: float = Field(default=0.10, ge=0, le=1.0)
    max_daily_loss_pct: float = Field(default=0.05, ge=0, le=1.0)
    max_order_frequency: int = Field(default=100, ge=1)


class BacktestConfig(BaseModel):
    default_commission: float = Field(default=0.0003, ge=0)
    default_slippage: float = Field(default=0.0001, ge=0)
    initial_capital: float = Field(default=300_000.0, gt=0)


class Settings(BaseModel):
    system: SystemConfig = SystemConfig()
    data: DataConfig = DataConfig()
    risk: RiskConfig = RiskConfig()
    backtest: BacktestConfig = BacktestConfig()

    @classmethod
    def from_yaml(cls, path: str | Path) -> Settings:
        """从 YAML 文件加载配置。"""
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path) as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        return cls(**raw)

    @classmethod
    def load(cls, config_dir: str | Path = "config") -> Settings:
        """从默认配置目录加载配置。"""
        config_path = Path(config_dir) / "settings.yaml"
        return cls.from_yaml(config_path)
