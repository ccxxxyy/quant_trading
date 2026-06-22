"""交易标的定义 - 可交易资产的标准化表示。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Exchange(Enum):
    """支持的交易所。"""

    SSE = "SSE"  # 上海证券交易所
    SZSE = "SZSE"  # 深圳证券交易所
    CFFEX = "CFFEX"  # 中国金融期货交易所
    SHFE = "SHFE"  # 上海期货交易所
    DCE = "DCE"  # 大连商品交易所
    CZCE = "CZCE"  # 郑州商品交易所
    NYSE = "NYSE"  # 纽约证券交易所
    NASDAQ = "NASDAQ"  # 纳斯达克交易所
    BINANCE = "BINANCE"  # 币安交易所
    IB = "IB"  # 盈透证券（多交易所通道）


class InstrumentType(Enum):
    STOCK = "stock"  # 股票
    ETF = "etf"  # 交易型开放式基金
    FUTURE = "future"  # 期货合约
    OPTION = "option"  # 期权合约
    CRYPTO = "crypto"  # 加密货币
    INDEX = "index"  # 指数


class Currency(Enum):
    CNY = "CNY"  # 人民币
    USD = "USD"  # 美元
    HKD = "HKD"  # 港币
    USDT = "USDT"  # 泰达币（加密货币稳定币）


@dataclass(frozen=True, slots=True)
class InstrumentId:
    """全局唯一的交易标的标识符。"""

    symbol: str
    exchange: Exchange

    def __str__(self) -> str:
        return f"{self.symbol}.{self.exchange.value}"

    @classmethod
    def from_str(cls, s: str) -> InstrumentId:
        parts = s.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid instrument id: {s}, expected 'SYMBOL.EXCHANGE'")
        return cls(symbol=parts[0], exchange=Exchange(parts[1]))


@dataclass(frozen=True, slots=True)
class Instrument:
    """完整的交易标的规格定义。"""

    id: InstrumentId
    name: str
    instrument_type: InstrumentType
    currency: Currency
    lot_size: int = 1  # 每手数量（A股通常为100）
    tick_size: Decimal = Decimal("0.01")  # 最小价格变动单位
    margin_ratio: Decimal = Decimal("1.0")  # 保证金比例（1.0 = 无杠杆，全额交易）
    commission_rate: Decimal = Decimal("0.0003")  # 手续费率（默认万分之三）

    @property
    def symbol(self) -> str:
        return self.id.symbol

    @property
    def exchange(self) -> Exchange:
        return self.id.exchange
