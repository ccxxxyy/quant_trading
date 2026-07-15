"""实盘监控与告警系统 - 异常检测、风险告警、多渠道通知。

支持推送渠道：
    - 控制台 / Web 面板（默认）
    - 邮件（SMTP）
    - 企业微信 / 钉钉 Webhook
"""

from __future__ import annotations

import json
import logging
import smtplib
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from email.mime.text import MIMEText
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """告警级别。"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(Enum):
    """告警类型。"""

    DRAWDOWN = "drawdown"  # 回撤超阈值
    DAILY_LOSS = "daily_loss"  # 日亏损超阈值
    POSITION_LIMIT = "position_limit"  # 持仓超限
    ORDER_REJECTED = "order_rejected"  # 订单被拒
    CONNECTION_LOST = "connection_lost"  # 连接断开
    PRICE_ANOMALY = "price_anomaly"  # 价格异常
    STRATEGY_ERROR = "strategy_error"  # 策略运行出错
    FILL_DEVIATION = "fill_deviation"  # 成交偏离
    CUSTOM = "custom"


@dataclass
class Alert:
    """告警记录。"""

    alert_type: AlertType
    level: AlertLevel
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    data: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False

    def to_dict(self) -> dict:
        return {
            "type": self.alert_type.value,
            "level": self.level.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "acknowledged": self.acknowledged,
        }


class AlertManager:
    """告警管理器。

    监控系统关键指标，当指标超过阈值时触发告警。

    使用示例：
        manager = AlertManager()
        manager.set_threshold("max_drawdown", 0.10)  # 回撤超10%告警
        manager.set_threshold("max_daily_loss", 50000)  # 日亏损超5万告警
        manager.add_handler(print)  # 控制台输出
        manager.add_handler(send_email)  # 邮件通知

        manager.check_drawdown(current_equity=950000, peak_equity=1000000)
    """

    def __init__(self) -> None:
        self._thresholds: dict[str, float] = {
            "max_drawdown": 0.10,
            "max_daily_loss": 50000.0,
            "max_position_pct": 0.30,
            "fill_deviation_pct": 0.02,
        }
        self._handlers: list[Callable[[Alert], None]] = []
        self._alerts: list[Alert] = []
        self._suppressed: set[str] = set()
        self._daily_pnl: Decimal = Decimal("0")
        self._peak_equity: float = 0.0

    def set_threshold(self, key: str, value: float) -> None:
        """设置告警阈值。"""
        self._thresholds[key] = value

    def add_handler(self, handler: Callable[[Alert], None]) -> None:
        """注册告警处理函数（如日志、邮件、微信、钉钉等）。"""
        self._handlers.append(handler)

    def fire(self, alert: Alert) -> None:
        """触发告警。"""
        # 5分钟内相同类型告警只发一次
        key = f"{alert.alert_type.value}:{alert.message[:50]}"
        if key in self._suppressed:
            return

        self._alerts.append(alert)
        self._suppressed.add(key)

        level_map = {
            AlertLevel.INFO: logger.info,
            AlertLevel.WARNING: logger.warning,
            AlertLevel.CRITICAL: logger.critical,
        }
        log_fn = level_map.get(alert.level, logger.warning)
        log_fn(f"[ALERT:{alert.level.value}] {alert.alert_type.value}: {alert.message}")

        for handler in self._handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"Alert handler error: {e}")

    def check_drawdown(self, current_equity: float, peak_equity: float | None = None) -> None:
        """检查回撤是否超过阈值。"""
        if peak_equity is not None:
            self._peak_equity = max(self._peak_equity, peak_equity)
        self._peak_equity = max(self._peak_equity, current_equity)

        if self._peak_equity <= 0:
            return

        drawdown = (self._peak_equity - current_equity) / self._peak_equity
        threshold = self._thresholds.get("max_drawdown", 0.10)

        if drawdown >= threshold:
            level = AlertLevel.CRITICAL if drawdown >= threshold * 1.5 else AlertLevel.WARNING
            self.fire(
                Alert(
                    alert_type=AlertType.DRAWDOWN,
                    level=level,
                    message=f"回撤 {drawdown:.2%} 超过阈值 {threshold:.2%}",
                    data={
                        "drawdown": drawdown,
                        "equity": current_equity,
                        "peak": self._peak_equity,
                    },
                )
            )

    def check_daily_loss(self, daily_pnl: float) -> None:
        """检查日亏损是否超过阈值。"""
        threshold = self._thresholds.get("max_daily_loss", 50000)
        if daily_pnl < -threshold:
            self.fire(
                Alert(
                    alert_type=AlertType.DAILY_LOSS,
                    level=AlertLevel.CRITICAL,
                    message=f"日亏损 {daily_pnl:,.0f} 超过阈值 -{threshold:,.0f}",
                    data={"daily_pnl": daily_pnl},
                )
            )

    def check_fill_deviation(self, expected_price: float, fill_price: float) -> None:
        """检查成交价格是否偏离过大。"""
        if expected_price <= 0:
            return
        deviation = abs(fill_price - expected_price) / expected_price
        threshold = self._thresholds.get("fill_deviation_pct", 0.02)
        if deviation >= threshold:
            self.fire(
                Alert(
                    alert_type=AlertType.FILL_DEVIATION,
                    level=AlertLevel.WARNING,
                    message=(
                        f"成交偏离 {deviation:.2%}: "
                        f"期望 {expected_price:.2f}, 实际 {fill_price:.2f}"
                    ),
                    data={"expected": expected_price, "actual": fill_price, "deviation": deviation},
                )
            )

    def on_connection_lost(self, gateway_name: str) -> None:
        """网关连接断开告警。"""
        self.fire(
            Alert(
                alert_type=AlertType.CONNECTION_LOST,
                level=AlertLevel.CRITICAL,
                message=f"网关 {gateway_name} 连接断开",
                data={"gateway": gateway_name},
            )
        )

    def on_order_rejected(self, order_id: str, reason: str) -> None:
        """订单被拒告警。"""
        self.fire(
            Alert(
                alert_type=AlertType.ORDER_REJECTED,
                level=AlertLevel.WARNING,
                message=f"订单 {order_id} 被拒: {reason}",
                data={"order_id": order_id, "reason": reason},
            )
        )

    def on_strategy_error(self, strategy_id: str, error: str) -> None:
        """策略运行错误告警。"""
        self.fire(
            Alert(
                alert_type=AlertType.STRATEGY_ERROR,
                level=AlertLevel.CRITICAL,
                message=f"策略 {strategy_id} 出错: {error}",
                data={"strategy_id": strategy_id, "error": error},
            )
        )

    def get_recent_alerts(self, limit: int = 50) -> list[dict]:
        """获取最近的告警记录。"""
        return [a.to_dict() for a in self._alerts[-limit:]]

    def clear_suppression(self) -> None:
        """清除告警抑制（允许重复告警）。"""
        self._suppressed.clear()

    @property
    def alert_count(self) -> int:
        return len(self._alerts)

    @property
    def unacknowledged_count(self) -> int:
        return sum(1 for a in self._alerts if not a.acknowledged)


# ---------------------------------------------------------------------------
# 推送渠道 handlers
# ---------------------------------------------------------------------------


class EmailAlertHandler:
    """通过 SMTP 发送告警邮件。

    使用方式::

        handler = EmailAlertHandler(
            smtp_host="smtp.qq.com", smtp_port=465, use_ssl=True,
            username="bot@example.com", password="app_password",
            sender="bot@example.com", recipients=["admin@example.com"],
        )
        manager.add_handler(handler)
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int = 465,
        use_ssl: bool = True,
        username: str = "",
        password: str = "",
        sender: str = "",
        recipients: list[str] | None = None,
    ) -> None:
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.use_ssl = use_ssl
        self.username = username
        self.password = password
        self.sender = sender or username
        self.recipients = recipients or []

    def __call__(self, alert: Alert) -> None:
        if not self.recipients:
            return
        subject = f"[{alert.level.value.upper()}] {alert.alert_type.value}: {alert.message[:60]}"
        body = (
            f"告警级别: {alert.level.value}\n"
            f"告警类型: {alert.alert_type.value}\n"
            f"时间: {alert.timestamp.isoformat()}\n"
            f"详情: {alert.message}\n"
            f"数据: {alert.data}"
        )
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)

        try:
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
                server.starttls()
            if self.username:
                server.login(self.username, self.password)
            server.sendmail(self.sender, self.recipients, msg.as_string())
            server.quit()
            logger.info(f"Email alert sent to {self.recipients}")
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")


class WebhookAlertHandler:
    """通过 Webhook（企业微信 / 钉钉 / 飞书等）推送告警。

    企业微信示例::

        handler = WebhookAlertHandler(
            url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx",
            platform="wecom",
        )

    钉钉示例::

        handler = WebhookAlertHandler(
            url="https://oapi.dingtalk.com/robot/send?access_token=xxx",
            platform="dingtalk",
        )
    """

    PLATFORMS = ("wecom", "dingtalk", "feishu", "generic")

    def __init__(self, url: str, platform: str = "generic") -> None:
        self.url = url
        self.platform = platform if platform in self.PLATFORMS else "generic"

    def __call__(self, alert: Alert) -> None:
        text = (
            f"**[{alert.level.value.upper()}] {alert.alert_type.value}**\n"
            f"> {alert.message}\n"
            f"> 时间: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        payload = self._build_payload(text)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                logger.info(f"Webhook alert sent ({self.platform}): {resp.status}")
        except Exception as e:
            logger.error(f"Failed to send webhook alert ({self.platform}): {e}")

    def _build_payload(self, text: str) -> dict:
        if self.platform == "wecom":
            return {"msgtype": "markdown", "markdown": {"content": text}}
        if self.platform == "dingtalk":
            return {
                "msgtype": "markdown",
                "markdown": {"title": "交易告警", "text": text},
            }
        if self.platform == "feishu":
            return {"msg_type": "text", "content": {"text": text}}
        return {"text": text}
