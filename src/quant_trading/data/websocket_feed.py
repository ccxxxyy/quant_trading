"""WebSocket 实时行情源 - 通过 WebSocket 接收实时行情并分发到系统。

支持功能：
    - 通用 WebSocket 行情接入（可对接任意行情源）
    - 自动断线重连（指数退避）
    - 行情缺失检测与补全
    - 心跳保活
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from quant_trading.model.instrument import InstrumentId
from quant_trading.model.market import Bar, BarInterval, Tick

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


class WebSocketFeed:
    """通用 WebSocket 实时行情源。

    职责：
        1. 建立并维护 WebSocket 连接
        2. 自动断线重连（指数退避：1s → 2s → 4s → ... → 最大60s）
        3. 心跳保活（定时发送 ping）
        4. 行情缺失检测：记录每个标的最后收到的时间，超时则触发补全回调
        5. 将收到的原始消息解析为 Bar/Tick 并通过回调分发

    使用方式::

        feed = WebSocketFeed(url="wss://example.com/ws")
        feed.on_bar = runner.on_bar
        feed.on_tick = lambda tick: print(tick)
        feed.on_connection_change = lambda s: print(f"state: {s}")
        await feed.connect(["600519.SSE", "000001.SSE"])
        # ... 运行中 ...
        await feed.disconnect()
    """

    def __init__(
        self,
        url: str = "ws://127.0.0.1:9999/ws/market",
        heartbeat_interval: float = 30.0,
        max_reconnect_delay: float = 60.0,
        gap_timeout: float = 120.0,
        message_parser: Callable[[str | bytes], dict | None] | None = None,
    ) -> None:
        self._url = url
        self._heartbeat_interval = heartbeat_interval
        self._max_reconnect_delay = max_reconnect_delay
        self._gap_timeout = gap_timeout
        self._parse_message = message_parser or self._default_parser

        self._state = ConnectionState.DISCONNECTED
        self._ws: Any = None
        self._subscribed_symbols: list[str] = []
        self._reconnect_count = 0
        self._last_message_time: dict[str, float] = {}
        self._total_messages = 0
        self._running = False

        # 用户回调
        self.on_bar: Callable[[Bar], None] | None = None
        self.on_tick: Callable[[Tick], None] | None = None
        self.on_connection_change: Callable[[ConnectionState], None] | None = None
        self.on_gap_detected: Callable[[str, float], None] | None = None

        self._tasks: list[asyncio.Task] = []

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def total_messages(self) -> int:
        return self._total_messages

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    @property
    def subscribed_symbols(self) -> list[str]:
        return list(self._subscribed_symbols)

    def _set_state(self, new_state: ConnectionState) -> None:
        old = self._state
        self._state = new_state
        if old != new_state:
            logger.info(f"WebSocket state: {old.value} → {new_state.value}")
            if self.on_connection_change:
                try:
                    self.on_connection_change(new_state)
                except Exception as e:
                    logger.error(f"Connection change callback error: {e}")

    async def connect(self, symbols: list[str] | None = None) -> None:
        """建立 WebSocket 连接并开始接收行情。"""
        if symbols:
            self._subscribed_symbols = list(symbols)
        self._running = True
        self._set_state(ConnectionState.CONNECTING)

        self._tasks.append(asyncio.create_task(self._connection_loop()))
        self._tasks.append(asyncio.create_task(self._gap_check_loop()))

    async def disconnect(self) -> None:
        """断开连接并清理资源。"""
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        self._set_state(ConnectionState.DISCONNECTED)
        logger.info("WebSocket feed disconnected")

    async def subscribe(self, symbols: list[str]) -> None:
        """动态添加订阅标的。"""
        for s in symbols:
            if s not in self._subscribed_symbols:
                self._subscribed_symbols.append(s)

        if self._ws and self._state == ConnectionState.CONNECTED:
            await self._send_subscribe(symbols)

    async def unsubscribe(self, symbols: list[str]) -> None:
        """取消订阅标的。"""
        for s in symbols:
            if s in self._subscribed_symbols:
                self._subscribed_symbols.remove(s)
            self._last_message_time.pop(s, None)

    # ------------------------------------------------------------------
    # 内部连接循环 + 重连
    # ------------------------------------------------------------------

    async def _connection_loop(self) -> None:
        """主连接循环：连接 → 收消息 → 断开 → 重连。"""
        while self._running:
            try:
                await self._do_connect()
                self._reconnect_count = 0
                self._set_state(ConnectionState.CONNECTED)

                if self._subscribed_symbols:
                    await self._send_subscribe(self._subscribed_symbols)

                heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                try:
                    await self._receive_loop()
                finally:
                    heartbeat_task.cancel()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"WebSocket connection error: {e}")

            if not self._running:
                break

            delay = self._reconnect_delay()
            self._reconnect_count += 1
            self._set_state(ConnectionState.RECONNECTING)
            logger.info(f"Reconnecting in {delay:.1f}s (attempt #{self._reconnect_count})")
            await asyncio.sleep(delay)

    def _reconnect_delay(self) -> float:
        """指数退避重连延迟：1, 2, 4, 8, ... 最大 max_reconnect_delay。"""
        delay = min(2**self._reconnect_count, self._max_reconnect_delay)
        return delay

    async def _do_connect(self) -> None:
        """实际建立 WebSocket 连接。优先使用 websockets 库，回退到 aiohttp。"""
        try:
            import websockets

            self._ws = await websockets.connect(self._url)
            self._ws_lib = "websockets"
            logger.info(f"Connected via websockets: {self._url}")
            return
        except ImportError:
            pass

        try:
            import aiohttp

            session = aiohttp.ClientSession()
            self._ws = await session.ws_connect(self._url)
            self._ws_lib = "aiohttp"
            self._aiohttp_session = session
            logger.info(f"Connected via aiohttp: {self._url}")
            return
        except ImportError:
            pass

        raise RuntimeError(
            "No WebSocket library available. Install one: uv add websockets  or  uv add aiohttp"
        )

    async def _receive_loop(self) -> None:
        """持续接收并处理 WebSocket 消息。"""
        while self._running:
            raw = await self._recv()
            if raw is None:
                break
            self._total_messages += 1

            parsed = self._parse_message(raw)
            if parsed is None:
                continue

            self._dispatch(parsed)

    async def _recv(self) -> str | bytes | None:
        """从 WebSocket 接收一条消息。"""
        try:
            if self._ws_lib == "websockets":
                return await self._ws.recv()
            else:
                msg = await self._ws.receive()
                if msg.type in (1, 2):  # TEXT, BINARY
                    return msg.data
                return None
        except Exception:
            return None

    async def _send(self, data: str) -> None:
        """发送消息到 WebSocket。"""
        try:
            if self._ws_lib == "websockets":
                await self._ws.send(data)
            else:
                await self._ws.send_str(data)
        except Exception as e:
            logger.warning(f"WebSocket send error: {e}")

    async def _send_subscribe(self, symbols: list[str]) -> None:
        """发送订阅请求。"""
        msg = json.dumps({"action": "subscribe", "symbols": symbols})
        await self._send(msg)
        logger.info(f"Subscribed to {len(symbols)} symbols")

    async def _heartbeat_loop(self) -> None:
        """定时心跳保活。"""
        try:
            while self._running:
                await asyncio.sleep(self._heartbeat_interval)
                await self._send(json.dumps({"action": "ping"}))
        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------
    # 行情缺失检测
    # ------------------------------------------------------------------

    async def _gap_check_loop(self) -> None:
        """定期检测是否有标的行情中断。"""
        try:
            while self._running:
                await asyncio.sleep(self._gap_timeout / 2)
                now = time.time()
                for symbol in self._subscribed_symbols:
                    last = self._last_message_time.get(symbol)
                    if last and (now - last) > self._gap_timeout:
                        gap_secs = now - last
                        logger.warning(f"Gap detected for {symbol}: no data for {gap_secs:.0f}s")
                        if self.on_gap_detected:
                            try:
                                self.on_gap_detected(symbol, gap_secs)
                            except Exception as e:
                                logger.error(f"Gap callback error: {e}")
        except asyncio.CancelledError:
            pass

    # ------------------------------------------------------------------
    # 消息解析 + 分发
    # ------------------------------------------------------------------

    def _dispatch(self, data: dict) -> None:
        """将解析后的行情数据分发到回调。"""
        msg_type = data.get("type", "bar")
        symbol = data.get("symbol", "")

        self._last_message_time[symbol] = time.time()

        if msg_type == "bar" and self.on_bar:
            bar = self._to_bar(data)
            if bar:
                self.on_bar(bar)
        elif msg_type == "tick" and self.on_tick:
            tick = self._to_tick(data)
            if tick:
                self.on_tick(tick)

    @staticmethod
    def _default_parser(raw: str | bytes) -> dict | None:
        """默认 JSON 解析器。"""
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
            return None
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    @staticmethod
    def _to_bar(data: dict) -> Bar | None:
        """将 dict 转为 Bar 对象。"""
        try:
            return Bar(
                instrument_id=InstrumentId.from_str(data["symbol"]),
                timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat())),
                interval=BarInterval(data.get("interval", "1m")),
                open=Decimal(str(data["open"])),
                high=Decimal(str(data["high"])),
                low=Decimal(str(data["low"])),
                close=Decimal(str(data["close"])),
                volume=int(data.get("volume", 0)),
            )
        except (KeyError, ValueError) as e:
            logger.debug(f"Cannot parse bar: {e}")
            return None

    @staticmethod
    def _to_tick(data: dict) -> Tick | None:
        """将 dict 转为 Tick 对象。"""
        try:
            return Tick(
                instrument_id=InstrumentId.from_str(data["symbol"]),
                timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat())),
                last_price=Decimal(str(data["last_price"])),
                last_volume=int(data.get("last_volume", 0)),
                bid_price=Decimal(str(data.get("bid_price", data["last_price"]))),
                ask_price=Decimal(str(data.get("ask_price", data["last_price"]))),
                bid_volume=int(data.get("bid_volume", 0)),
                ask_volume=int(data.get("ask_volume", 0)),
            )
        except (KeyError, ValueError) as e:
            logger.debug(f"Cannot parse tick: {e}")
            return None

    def get_status(self) -> dict:
        """返回行情源状态摘要。"""
        return {
            "state": self._state.value,
            "url": self._url,
            "subscribed_symbols": self._subscribed_symbols,
            "total_messages": self._total_messages,
            "reconnect_count": self._reconnect_count,
            "last_message_times": {
                k: datetime.fromtimestamp(v).isoformat() for k, v in self._last_message_time.items()
            },
        }
