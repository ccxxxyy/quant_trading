"""CTP网关 - 通过 CTP 协议连接中国期货市场。

CTP（Comprehensive Transaction Platform，综合交易平台）是中国期货市场的主流交易接口，
由上期技术公司开发，支持所有中国期货交易所的交易和行情。

本模块提供两种运行模式：
    1. 真实模式：安装 openctp-ctp 后连接 SimNow 模拟盘或期货公司实盘
    2. 桩模式（Stub）：未安装 CTP 库时自动降级，仅做接口验证

SimNow 模拟盘（免费注册，无需开户）：
    - 注册地址：https://www.simnow.com.cn
    - 7×24 小时测试环境：
        行情前置：tcp://180.168.146.187:10131
        交易前置：tcp://180.168.146.187:10130
    - BrokerID：9999

依赖安装：
    uv pip install openctp-ctp
    或
    pip install openctp-ctp
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime
from decimal import Decimal
from typing import Any

from quant_trading.gateway.base import BaseGateway
from quant_trading.model.account import Account
from quant_trading.model.instrument import Currency, Exchange, InstrumentId
from quant_trading.model.market import Tick
from quant_trading.model.order import Fill, Order, OrderSide, OrderStatus, OrderType
from quant_trading.model.position import Position

logger = logging.getLogger(__name__)

CTP_EXCHANGE_MAP = {
    Exchange.SHFE: "SHFE",
    Exchange.DCE: "DCE",
    Exchange.CZCE: "CZCE",
    Exchange.CFFEX: "CFFEX",
}

EXCHANGE_REVERSE_MAP = {v: k for k, v in CTP_EXCHANGE_MAP.items()}

SIMNOW_CONFIG = {
    "broker_id": "9999",
    "td_address": "tcp://180.168.146.187:10130",
    "md_address": "tcp://180.168.146.187:10131",
    "auth_code": "0000000000000000",
    "app_id": "simnow_client_test",
}

# CTP 方向常量
DIRECTION_BUY = "0"
DIRECTION_SELL = "1"

# CTP 开平标志
OFFSET_OPEN = "0"
OFFSET_CLOSE = "1"
OFFSET_CLOSE_TODAY = "3"
OFFSET_CLOSE_YESTERDAY = "4"

# CTP 价格类型
PRICE_LIMIT = "2"
PRICE_MARKET = "1"
PRICE_STOP = "4"

# CTP 订单状态
STATUS_ALL_TRADED = "0"
STATUS_PART_TRADED = "1"
STATUS_NO_TRADE = "3"
STATUS_CANCELED = "5"
STATUS_NOT_TOUCHED = "a"
STATUS_TOUCHED = "b"


def _check_ctp_available() -> bool:
    """检查 openctp-ctp 库是否已安装。"""
    try:
        import thostmduserapi  # noqa: F401
        import thosttraderapi  # noqa: F401

        return True
    except ImportError:
        return False


class CTPMdSpi:
    """CTP 行情回调处理器（SPI = Service Provider Interface）。

    CTP 行情的工作方式是"注册回调"：
    1. 创建 MdApi 并注册这个 SPI
    2. 调用 MdApi.Init() 启动行情线程
    3. CTP 行情服务器有新数据时，会自动调用 SPI 中对应的 On* 方法
    """

    def __init__(self, gateway: CTPGateway) -> None:
        self._gateway = gateway
        self._login_event = threading.Event()
        self._login_success = False

    def OnFrontConnected(self) -> None:
        """行情前置服务器连接成功回调。连上后自动发起登录。"""
        logger.info("CTP 行情前置已连接")
        self._gateway._md_login()

    def OnFrontDisconnected(self, reason: int) -> None:
        """行情前置断开回调。CTP 会自动重连，无需手动处理。"""
        logger.warning(f"CTP 行情前置断开, 原因代码: {reason}")

    def OnRspUserLogin(self, data: dict, error: dict, request_id: int, is_last: bool) -> None:
        """行情登录响应回调。"""
        if error and error.get("ErrorID", 0) != 0:
            logger.error(f"CTP 行情登录失败: [{error['ErrorID']}] {error.get('ErrorMsg', '')}")
            self._login_success = False
        else:
            logger.info(f"CTP 行情登录成功, 交易日: {data.get('TradingDay', '')}")
            self._login_success = True
        self._login_event.set()

    def OnRtnDepthMarketData(self, data: dict) -> None:
        """实时行情推送回调 - 每当订阅的合约价格变动时触发。"""
        try:
            exchange_id = data.get("ExchangeID", "")
            exchange = EXCHANGE_REVERSE_MAP.get(exchange_id, Exchange.SHFE)

            instrument_id = InstrumentId(
                symbol=data.get("InstrumentID", ""),
                exchange=exchange,
            )

            update_time = data.get("UpdateTime", "00:00:00")
            update_ms = data.get("UpdateMillisec", 0)
            trading_day = data.get("TradingDay", "")
            try:
                ts = datetime.strptime(
                    f"{trading_day} {update_time}.{update_ms:03d}",
                    "%Y%m%d %H:%M:%S.%f",
                )
            except (ValueError, TypeError):
                ts = datetime.now()

            last_price = data.get("LastPrice", 0.0)
            if last_price is None or last_price > 1e30:
                return

            tick = Tick(
                instrument_id=instrument_id,
                timestamp=ts,
                last_price=Decimal(str(last_price)),
                last_volume=int(data.get("Volume", 0)),
                bid_price=Decimal(str(data.get("BidPrice1", 0) or 0)),
                ask_price=Decimal(str(data.get("AskPrice1", 0) or 0)),
                bid_volume=int(data.get("BidVolume1", 0)),
                ask_volume=int(data.get("AskVolume1", 0)),
                open_interest=int(data.get("OpenInterest", 0)),
                turnover=Decimal(str(data.get("Turnover", 0) or 0)),
            )

            if self._gateway._on_tick:
                self._gateway._on_tick(tick)

        except Exception as e:
            logger.error(f"CTP 行情解析错误: {e}")

    def OnRspSubMarketData(self, data: dict, error: dict, request_id: int, is_last: bool) -> None:
        """订阅行情响应回调。"""
        if error and error.get("ErrorID", 0) != 0:
            logger.error(
                f"CTP 订阅行情失败 {data.get('InstrumentID', '')}: "
                f"[{error['ErrorID']}] {error.get('ErrorMsg', '')}"
            )
        else:
            logger.info(f"CTP 订阅行情成功: {data.get('InstrumentID', '')}")


class CTPTdSpi:
    """CTP 交易回调处理器。

    处理订单提交/撤销/成交/持仓/账户查询等交易相关的回调事件。
    CTP 的认证流程为：连接 → 认证(Authenticate) → 登录(Login) → 确认结算单 → 可交易。
    """

    def __init__(self, gateway: CTPGateway) -> None:
        self._gateway = gateway
        self._login_event = threading.Event()
        self._login_success = False
        self._auth_event = threading.Event()
        self._auth_success = False

        self._positions: list[Position] = []
        self._position_event = threading.Event()

        self._account: Account | None = None
        self._account_event = threading.Event()

    def OnFrontConnected(self) -> None:
        """交易前置服务器连接成功回调。连上后自动发起客户端认证。"""
        logger.info("CTP 交易前置已连接")
        self._gateway._td_authenticate()

    def OnFrontDisconnected(self, reason: int) -> None:
        """交易前置断开回调。"""
        logger.warning(f"CTP 交易前置断开, 原因代码: {reason}")
        self._gateway._connected = False

    def OnRspAuthenticate(self, data: dict, error: dict, request_id: int, is_last: bool) -> None:
        """客户端认证响应回调。认证通过后自动发起登录。"""
        if error and error.get("ErrorID", 0) != 0:
            logger.error(f"CTP 认证失败: [{error['ErrorID']}] {error.get('ErrorMsg', '')}")
            self._auth_success = False
        else:
            logger.info("CTP 客户端认证成功")
            self._auth_success = True
            self._gateway._td_login()
        self._auth_event.set()

    def OnRspUserLogin(self, data: dict, error: dict, request_id: int, is_last: bool) -> None:
        """交易登录响应回调。登录成功后获取前置编号和会话编号用于唯一标识本次会话。"""
        if error and error.get("ErrorID", 0) != 0:
            logger.error(f"CTP 交易登录失败: [{error['ErrorID']}] {error.get('ErrorMsg', '')}")
            self._login_success = False
        else:
            self._gateway._front_id = data.get("FrontID", 0)
            self._gateway._session_id = data.get("SessionID", 0)
            self._gateway._max_order_ref = int(data.get("MaxOrderRef", "0"))
            logger.info(
                f"CTP 交易登录成功, 交易日: {data.get('TradingDay', '')}, "
                f"FrontID: {self._gateway._front_id}, "
                f"SessionID: {self._gateway._session_id}"
            )
            self._login_success = True
            self._gateway._td_confirm_settlement()
        self._login_event.set()

    def OnRspSettlementInfoConfirm(
        self, data: dict, error: dict, request_id: int, is_last: bool
    ) -> None:
        """结算单确认响应。每日首次登录需确认昨日结算单后才能交易。"""
        if error and error.get("ErrorID", 0) != 0:
            logger.error(f"CTP 结算确认失败: [{error['ErrorID']}] {error.get('ErrorMsg', '')}")
        else:
            logger.info(f"CTP 结算单已确认, 确认日期: {data.get('ConfirmDate', '')}")

    def OnRspOrderInsert(self, data: dict, error: dict, request_id: int, is_last: bool) -> None:
        """报单录入响应 - 仅在报单被 CTP 柜台拒绝时回调。"""
        if error and error.get("ErrorID", 0) != 0:
            order_ref = data.get("OrderRef", "")
            logger.error(
                f"CTP 报单被拒: ref={order_ref} [{error['ErrorID']}] {error.get('ErrorMsg', '')}"
            )
            order = self._gateway._order_map.get(order_ref)
            if order:
                order.status = OrderStatus.REJECTED
                order.reject_reason = error.get("ErrorMsg", "CTP报单被拒")

    def OnRtnOrder(self, data: dict) -> None:
        """报单状态变化通知 - 每次订单状态更新都会推送。"""
        order_ref = data.get("OrderRef", "")
        order = self._gateway._order_map.get(order_ref)
        if not order:
            return

        ctp_status = data.get("OrderStatus", "")
        status_text = data.get("StatusMsg", "")

        if ctp_status == STATUS_ALL_TRADED:
            order.status = OrderStatus.FILLED
        elif ctp_status == STATUS_PART_TRADED:
            order.status = OrderStatus.PARTIAL_FILLED
        elif ctp_status == STATUS_CANCELED:
            order.status = OrderStatus.CANCELLED
        elif ctp_status in (STATUS_NO_TRADE, STATUS_NOT_TOUCHED):
            order.status = OrderStatus.SUBMITTED

        logger.info(f"CTP 订单状态: ref={order_ref} status={order.status.value} msg={status_text}")

    def OnRtnTrade(self, data: dict) -> None:
        """成交回报通知 - 每笔成交单独推送。"""
        order_ref = data.get("OrderRef", "")
        order = self._gateway._order_map.get(order_ref)
        if not order:
            return

        try:
            exchange_id = data.get("ExchangeID", "")
            exchange = EXCHANGE_REVERSE_MAP.get(exchange_id, Exchange.SHFE)

            instrument_id = InstrumentId(
                symbol=data.get("InstrumentID", ""),
                exchange=exchange,
            )

            direction = data.get("Direction", DIRECTION_BUY)
            side = OrderSide.BUY if direction == DIRECTION_BUY else OrderSide.SELL

            trade_time = data.get("TradeTime", "")
            trading_day = data.get("TradingDay", "")
            try:
                ts = datetime.strptime(f"{trading_day} {trade_time}", "%Y%m%d %H:%M:%S")
            except (ValueError, TypeError):
                ts = datetime.now()

            fill = Fill(
                order_id=order.order_id,
                instrument_id=instrument_id,
                side=side,
                price=Decimal(str(data.get("Price", 0))),
                quantity=int(data.get("Volume", 0)),
                commission=Decimal("0"),
                timestamp=ts,
            )

            order.filled_quantity += fill.quantity
            order.avg_fill_price = fill.price

            logger.info(f"CTP 成交: ref={order_ref} {side.value} {fill.quantity}@{fill.price}")

            if self._gateway._on_fill:
                self._gateway._on_fill(fill)

        except Exception as e:
            logger.error(f"CTP 成交回报处理错误: {e}")

    def OnRspQryInvestorPosition(
        self, data: dict, error: dict, request_id: int, is_last: bool
    ) -> None:
        """持仓查询响应 - 逐条推送，is_last=True 表示最后一条。"""
        if error and error.get("ErrorID", 0) != 0:
            logger.error(f"CTP 持仓查询失败: {error.get('ErrorMsg', '')}")
            if is_last:
                self._position_event.set()
            return

        if data and data.get("InstrumentID"):
            exchange_id = data.get("ExchangeID", "")
            exchange = EXCHANGE_REVERSE_MAP.get(exchange_id, Exchange.SHFE)

            instrument_id = InstrumentId(
                symbol=data["InstrumentID"],
                exchange=exchange,
            )

            direction = data.get("PosiDirection", "")
            # CTP 持仓方向：2=多头, 3=空头
            quantity = int(data.get("Position", 0))
            if direction == "3":
                quantity = -quantity

            if quantity != 0:
                avg_cost = Decimal(str(data.get("OpenCost", 0)))
                abs_qty = abs(quantity)
                if abs_qty > 0 and avg_cost > 0:
                    avg_cost = avg_cost / abs_qty

                position = Position(
                    instrument_id=instrument_id,
                    quantity=quantity,
                    avg_cost=avg_cost,
                    realized_pnl=Decimal(str(data.get("CloseProfit", 0))),
                    commission=Decimal(str(data.get("Commission", 0))),
                )
                self._positions.append(position)

        if is_last:
            self._position_event.set()

    def OnRspQryTradingAccount(
        self, data: dict, error: dict, request_id: int, is_last: bool
    ) -> None:
        """资金账户查询响应。"""
        if error and error.get("ErrorID", 0) != 0:
            logger.error(f"CTP 账户查询失败: {error.get('ErrorMsg', '')}")
            if is_last:
                self._account_event.set()
            return

        if data:
            self._account = Account(
                account_id=data.get("AccountID", "ctp"),
                currency=Currency.CNY,
                balance=Decimal(str(data.get("Balance", 0))),
                available=Decimal(str(data.get("Available", 0))),
                frozen=Decimal(str(data.get("FrozenCash", 0))),
                margin=Decimal(str(data.get("CurrMargin", 0))),
                unrealized_pnl=Decimal(str(data.get("PositionProfit", 0))),
                realized_pnl=Decimal(str(data.get("CloseProfit", 0))),
                commission=Decimal(str(data.get("Commission", 0))),
            )

        if is_last:
            self._account_event.set()

    def OnRspOrderAction(self, data: dict, error: dict, request_id: int, is_last: bool) -> None:
        """撤单响应 - 仅在撤单被拒绝时回调。"""
        if error and error.get("ErrorID", 0) != 0:
            logger.error(f"CTP 撤单被拒: [{error['ErrorID']}] {error.get('ErrorMsg', '')}")


class CTPGateway(BaseGateway):
    """CTP 网关，连接中国各期货交易所。

    使用前提：
        1. 安装 CTP Python 封装库：pip install openctp-ctp
        2. 在期货公司开户或注册 SimNow 模拟盘账号（https://www.simnow.com.cn）
        3. 配置连接参数（见 __init__ 参数说明）
        4. 期货交易有严格的时段限制：
           - 日盘：9:00-11:30, 13:30-15:00
           - 夜盘：21:00-次日凌晨（品种不同收盘时间不同）
           - SimNow 7×24 测试环境不受此限制

    支持的交易所：上期所(SHFE)、大商所(DCE)、郑商所(CZCE)、中金所(CFFEX)
    支持的品种：商品期货、金融期货、期权

    使用示例::

        gateway = CTPGateway.create_simnow(
            investor_id="你的SimNow账号",
            password="你的密码",
        )
        await gateway.connect()
        await gateway.subscribe_market_data([
            InstrumentId("au2412", Exchange.SHFE),   # 黄金期货
            InstrumentId("IF2412", Exchange.CFFEX),  # 沪深300股指期货
        ])
    """

    def __init__(
        self,
        broker_id: str = "",
        investor_id: str = "",
        password: str = "",
        td_address: str = "",
        md_address: str = "",
        auth_code: str = "",
        app_id: str = "",
    ) -> None:
        super().__init__(name="ctp")
        self._broker_id = broker_id
        self._investor_id = investor_id
        self._password = password
        self._td_address = td_address
        self._md_address = md_address
        self._auth_code = auth_code
        self._app_id = app_id

        self._td_api: Any = None
        self._md_api: Any = None
        self._td_spi: CTPTdSpi | None = None
        self._md_spi: CTPMdSpi | None = None

        self._order_ref: int = 0
        self._order_map: dict[str, Order] = {}
        self._front_id: int = 0
        self._session_id: int = 0
        self._max_order_ref: int = 0
        self._request_id: int = 0
        self._stub_mode: bool = False

    @classmethod
    def create_simnow(
        cls,
        investor_id: str,
        password: str,
    ) -> CTPGateway:
        """快捷创建 SimNow 模拟盘网关。

        SimNow 是上期技术提供的免费期货模拟交易平台，
        注册后即可获得模拟资金进行期货交易练习。

        Args:
            investor_id: SimNow 注册账号
            password: SimNow 登录密码

        Returns:
            配置好的 CTPGateway 实例
        """
        return cls(
            broker_id=SIMNOW_CONFIG["broker_id"],
            investor_id=investor_id,
            password=password,
            td_address=SIMNOW_CONFIG["td_address"],
            md_address=SIMNOW_CONFIG["md_address"],
            auth_code=SIMNOW_CONFIG["auth_code"],
            app_id=SIMNOW_CONFIG["app_id"],
        )

    def _next_request_id(self) -> int:
        """生成下一个请求编号（CTP 要求每次请求使用不同的 RequestID）。"""
        self._request_id += 1
        return self._request_id

    def _next_order_ref(self) -> str:
        """生成下一个订单引用号。"""
        self._max_order_ref += 1
        return str(self._max_order_ref)

    async def connect(self) -> None:
        """连接到 CTP 交易和行情服务器。

        连接流程：
        1. 创建交易 API 和行情 API
        2. 注册回调处理器（SPI）
        3. 连接前置服务器
        4. 等待认证 → 登录 → 结算确认 完成
        """
        if not self._td_address:
            raise ValueError("必须提供交易服务器地址 (td_address)")

        if not _check_ctp_available():
            logger.warning(
                "openctp-ctp 未安装，CTP 网关以桩模式运行。安装方法: pip install openctp-ctp"
            )
            self._stub_mode = True
            self._connected = True
            return

        try:
            import thostmduserapi as mdapi
            import thosttraderapi as tdapi

            # ---- 交易 API ----
            self._td_spi = CTPTdSpi(self)
            self._td_api = tdapi.CThostFtdcTraderApi.CreateFtdcTraderApi("")
            self._td_api.RegisterSpi(self._td_spi)
            self._td_api.SubscribePrivateTopic(tdapi.THOST_TERT_QUICK)
            self._td_api.SubscribePublicTopic(tdapi.THOST_TERT_QUICK)
            self._td_api.RegisterFront(self._td_address)
            self._td_api.Init()

            logger.info(f"CTP 交易前置连接中: {self._td_address}")

            success = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._td_spi._login_event.wait(timeout=30)
            )
            if not success or not self._td_spi._login_success:
                raise ConnectionError("CTP 交易登录超时或失败")

            # ---- 行情 API ----
            if self._md_address:
                self._md_spi = CTPMdSpi(self)
                self._md_api = mdapi.CThostFtdcMdApi.CreateFtdcMdApi("")
                self._md_api.RegisterSpi(self._md_spi)
                self._md_api.RegisterFront(self._md_address)
                self._md_api.Init()

                logger.info(f"CTP 行情前置连接中: {self._md_address}")

                success = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: self._md_spi._login_event.wait(timeout=15)
                )
                if not success or not self._md_spi._login_success:
                    logger.warning("CTP 行情登录失败，行情功能不可用")

            self._connected = True
            logger.info("CTP 网关连接完成")

        except ImportError:
            logger.warning("CTP 库导入失败，以桩模式运行")
            self._stub_mode = True
            self._connected = True
        except Exception as e:
            logger.error(f"CTP 连接失败: {e}")
            raise

    def _td_authenticate(self) -> None:
        """发起 CTP 客户端认证请求。"""
        if not self._td_api:
            return
        req = {
            "BrokerID": self._broker_id,
            "UserID": self._investor_id,
            "AuthCode": self._auth_code,
            "AppID": self._app_id,
        }
        self._td_api.ReqAuthenticate(req, self._next_request_id())

    def _td_login(self) -> None:
        """发起 CTP 交易登录请求。"""
        if not self._td_api:
            return
        req = {
            "BrokerID": self._broker_id,
            "UserID": self._investor_id,
            "Password": self._password,
        }
        self._td_api.ReqUserLogin(req, self._next_request_id())

    def _td_confirm_settlement(self) -> None:
        """确认结算单（每日首次登录必须确认昨日结算单）。"""
        if not self._td_api:
            return
        req = {
            "BrokerID": self._broker_id,
            "InvestorID": self._investor_id,
        }
        self._td_api.ReqSettlementInfoConfirm(req, self._next_request_id())

    def _md_login(self) -> None:
        """发起 CTP 行情登录请求（行情登录不需要认证）。"""
        if not self._md_api:
            return
        req = {
            "BrokerID": self._broker_id,
            "UserID": self._investor_id,
            "Password": self._password,
        }
        self._md_api.ReqUserLogin(req, self._next_request_id())

    async def disconnect(self) -> None:
        """断开 CTP 连接并释放 API 资源。"""
        if self._td_api and not self._stub_mode:
            try:
                self._td_api.Release()
            except Exception:
                pass
        if self._md_api and not self._stub_mode:
            try:
                self._md_api.Release()
            except Exception:
                pass

        self._td_api = None
        self._md_api = None
        self._td_spi = None
        self._md_spi = None
        self._connected = False
        logger.info("CTP 网关已断开")

    async def subscribe_market_data(self, instruments: list[InstrumentId]) -> None:
        """订阅期货实时行情。

        Args:
            instruments: 要订阅的合约列表，如 [InstrumentId("au2412", Exchange.SHFE)]

        注意：CTP 行情订阅使用合约代码（不含交易所前缀），如 "au2412"、"IF2412"。
        """
        if not self._connected:
            raise RuntimeError("CTP 网关未连接")

        for inst_id in instruments:
            if inst_id.exchange not in CTP_EXCHANGE_MAP:
                logger.warning(f"CTP 不支持该交易所: {inst_id.exchange}")
                continue

            if self._stub_mode:
                logger.info(f"CTP [桩模式] 订阅行情: {inst_id}")
                continue

            if self._md_api:
                self._md_api.SubscribeMarketData([inst_id.symbol.encode()], 1)
                logger.info(f"CTP 订阅行情: {inst_id}")

    async def submit_order(self, order: Order) -> str:
        """提交期货订单到 CTP。

        Args:
            order: 订单对象

        Returns:
            订单ID

        期货订单的特殊之处：
        - 有"开仓/平仓"区分（股票没有）
        - 平仓还分"平今"和"平昨"（上期所要求）
        - 保证金交易，只需缴纳合约价值的一部分（通常 5%-15%）
        """
        if not self._connected:
            raise RuntimeError("CTP 网关未连接")

        order_ref = self._next_order_ref()

        if self._stub_mode:
            order.status = OrderStatus.SUBMITTED
            order.broker_order_id = order_ref
            self._order_map[order_ref] = order
            logger.info(f"CTP [桩模式] 报单: {order.order_id} -> ref#{order_ref}")
            return order.order_id

        if not self._td_api:
            raise RuntimeError("CTP 交易 API 未初始化")

        direction = DIRECTION_BUY if order.side == OrderSide.BUY else DIRECTION_SELL

        if order.order_type == OrderType.LIMIT:
            price_type = PRICE_LIMIT
            price = float(order.price)
        elif order.order_type == OrderType.MARKET:
            price_type = PRICE_MARKET
            price = 0.0
        else:
            price_type = PRICE_LIMIT
            price = float(order.stop_price or order.price)

        exchange = CTP_EXCHANGE_MAP.get(order.instrument_id.exchange, "")

        req = {
            "BrokerID": self._broker_id,
            "InvestorID": self._investor_id,
            "InstrumentID": order.instrument_id.symbol,
            "OrderRef": order_ref,
            "Direction": direction,
            "CombOffsetFlag": OFFSET_OPEN,
            "CombHedgeFlag": "1",  # 投机
            "LimitPrice": price,
            "VolumeTotalOriginal": order.quantity,
            "OrderPriceType": price_type,
            "TimeCondition": "3",  # GFD（当日有效）
            "VolumeCondition": "1",  # 任何数量
            "MinVolume": 1,
            "ContingentCondition": "1",  # 立即触发
            "StopPrice": 0.0,
            "ForceCloseReason": "0",  # 非强平
            "IsAutoSuspend": 0,
            "ExchangeID": exchange,
        }

        ret = self._td_api.ReqOrderInsert(req, self._next_request_id())
        if ret != 0:
            order.status = OrderStatus.REJECTED
            order.reject_reason = f"CTP ReqOrderInsert 返回错误码: {ret}"
            logger.error(order.reject_reason)
        else:
            order.status = OrderStatus.SUBMITTED
            order.broker_order_id = order_ref

        self._order_map[order_ref] = order
        logger.info(f"CTP 报单: {order.order_id} -> ref#{order_ref}")
        return order.order_id

    async def cancel_order(self, order_id: str) -> bool:
        """撤销期货订单。

        Args:
            order_id: 要撤销的订单 ID

        Returns:
            是否成功发出撤单请求
        """
        target_ref = None
        target_order = None
        for ref, order in self._order_map.items():
            if order.order_id == order_id and order.is_active:
                target_ref = ref
                target_order = order
                break

        if not target_ref or not target_order:
            logger.warning(f"CTP 撤单失败: 未找到活跃订单 {order_id}")
            return False

        if self._stub_mode:
            target_order.status = OrderStatus.CANCELLED
            logger.info(f"CTP [桩模式] 撤单: {order_id}")
            return True

        if not self._td_api:
            return False

        exchange = CTP_EXCHANGE_MAP.get(target_order.instrument_id.exchange, "")

        req = {
            "BrokerID": self._broker_id,
            "InvestorID": self._investor_id,
            "InstrumentID": target_order.instrument_id.symbol,
            "OrderRef": target_ref,
            "FrontID": self._front_id,
            "SessionID": self._session_id,
            "ActionFlag": "0",  # 删除
            "ExchangeID": exchange,
        }

        ret = self._td_api.ReqOrderAction(req, self._next_request_id())
        if ret != 0:
            logger.error(f"CTP 撤单请求失败, 错误码: {ret}")
            return False

        logger.info(f"CTP 撤单请求已发出: {order_id}")
        return True

    async def query_positions(self) -> list[Position]:
        """查询当前所有期货持仓。

        CTP 期货持仓有以下特点：
        - 区分多头和空头（可以同时持有同一品种的多头和空头）
        - 区分今仓和昨仓（上期所平仓需要指定平今或平昨）
        - 持仓盈亏按逐日盯市或逐笔对冲计算

        Returns:
            持仓列表
        """
        if not self._connected:
            return []

        if self._stub_mode:
            logger.info("CTP [桩模式] 查询持仓")
            return []

        if not self._td_api or not self._td_spi:
            return []

        self._td_spi._positions = []
        self._td_spi._position_event.clear()

        req = {
            "BrokerID": self._broker_id,
            "InvestorID": self._investor_id,
        }
        self._td_api.ReqQryInvestorPosition(req, self._next_request_id())

        success = await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._td_spi._position_event.wait(timeout=10)
        )
        if not success:
            logger.warning("CTP 持仓查询超时")
            return []

        return self._td_spi._positions

    async def query_account(self) -> Account:
        """查询期货资金账户。

        期货账户的资金结构：
        - Balance（动态权益）= 上日结存 + 当日入金 - 当日出金 + 平仓盈亏 + 持仓盈亏 - 手续费
        - Available（可用资金）= 动态权益 - 占用保证金 - 冻结资金
        - CurrMargin（当前保证金）= 各品种的持仓保证金之和
        - FrozenCash（冻结资金）= 未成交委托冻结的资金

        Returns:
            账户信息
        """
        if not self._connected:
            raise RuntimeError("CTP 网关未连接")

        if self._stub_mode:
            logger.info("CTP [桩模式] 查询账户")
            return Account(
                account_id=self._investor_id or "ctp_stub",
                currency=Currency.CNY,
            )

        if not self._td_api or not self._td_spi:
            raise RuntimeError("CTP 交易 API 未初始化")

        self._td_spi._account = None
        self._td_spi._account_event.clear()

        req = {
            "BrokerID": self._broker_id,
            "InvestorID": self._investor_id,
        }
        self._td_api.ReqQryTradingAccount(req, self._next_request_id())

        success = await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._td_spi._account_event.wait(timeout=10)
        )
        if not success:
            logger.warning("CTP 账户查询超时")
            return Account(
                account_id=self._investor_id or "ctp",
                currency=Currency.CNY,
            )

        return self._td_spi._account or Account(
            account_id=self._investor_id or "ctp",
            currency=Currency.CNY,
        )
