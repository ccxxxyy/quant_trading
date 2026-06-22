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
