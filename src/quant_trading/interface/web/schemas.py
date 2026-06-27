"""Web API 的 Pydantic 请求/响应数据格式定义。"""

from __future__ import annotations

from pydantic import BaseModel


class FetchDataRequest(BaseModel):
    symbol: str
    start: str
    end: str | None = None
    interval: str = "1d"
    provider: str = "akshare"


class BacktestRequest(BaseModel):
    strategy: str
    symbol: str
    start: str
    end: str | None = None
    capital: float = 1_000_000.0
    params: dict | None = None
    use_demo_data: bool = False


class HealthResponse(BaseModel):
    status: str
    version: str


class OptimizeRequest(BaseModel):
    strategy: str
    symbol: str
    start: str
    end: str | None = None
    capital: float = 1_000_000.0
    param_grid: dict[str, list]
    use_demo_data: bool = True


class PaperOrderRequest(BaseModel):
    symbol: str
    side: str  # "buy" or "sell"
    order_type: str = "market"  # "market" or "limit"
    quantity: int = 100
    price: float | None = None


class PaperConfigRequest(BaseModel):
    initial_capital: float = 1_000_000.0
    commission_rate: float = 0.0003
    slippage_rate: float = 0.0001
