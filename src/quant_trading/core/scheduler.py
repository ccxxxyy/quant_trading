"""定时任务调度器 - 管理盘前数据更新、盘后统计等周期性任务。

基于 asyncio 实现，无需外部依赖。支持：
    - Cron 风格定时调度（交易日 + 指定时间）
    - 盘前任务（数据更新、因子计算）
    - 盘后任务（日报统计、持仓快照）
    - 自定义间隔重复任务
    - 任务执行日志和错误处理
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TaskType(Enum):
    PRE_MARKET = "pre_market"
    POST_MARKET = "post_market"
    INTERVAL = "interval"
    DAILY = "daily"


@dataclass
class ScheduledTask:
    """单个定时任务定义。"""

    name: str
    task_type: TaskType
    handler: Callable[..., Coroutine[Any, Any, Any]] | Callable[..., Any]
    run_time: time | None = None
    interval_seconds: float = 0
    enabled: bool = True
    last_run: datetime | None = None
    run_count: int = 0
    error_count: int = 0
    last_error: str | None = None
    _kwargs: dict = field(default_factory=dict)


# A 股交易日历简化判断
_WEEKDAYS = {0, 1, 2, 3, 4}  # 周一到周五


def is_trading_day(dt: datetime | None = None) -> bool:
    """简易判断是否为交易日（周一至周五，不含节假日）。

    生产环境建议替换为完整的交易日历。
    """
    dt = dt or datetime.now()
    return dt.weekday() in _WEEKDAYS


class TaskScheduler:
    """异步定时任务调度器。

    使用方式::

        scheduler = TaskScheduler()

        # 盘前任务：09:15 更新行情数据
        scheduler.add_pre_market("更新行情", update_data, run_time=time(9, 15))

        # 盘后任务：15:30 统计当日盈亏
        scheduler.add_post_market("日报统计", daily_report, run_time=time(15, 30))

        # 间隔任务：每 60 秒检查行情连接
        scheduler.add_interval("连接检查", check_connection, interval=60)

        await scheduler.start()
    """

    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._loop_task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._running

    @property
    def tasks(self) -> dict[str, ScheduledTask]:
        return dict(self._tasks)

    def add_pre_market(
        self,
        name: str,
        handler: Callable,
        run_time: time = time(9, 15),
        **kwargs,
    ) -> None:
        """添加盘前任务。"""
        self._tasks[name] = ScheduledTask(
            name=name,
            task_type=TaskType.PRE_MARKET,
            handler=handler,
            run_time=run_time,
            _kwargs=kwargs,
        )

    def add_post_market(
        self,
        name: str,
        handler: Callable,
        run_time: time = time(15, 30),
        **kwargs,
    ) -> None:
        """添加盘后任务。"""
        self._tasks[name] = ScheduledTask(
            name=name,
            task_type=TaskType.POST_MARKET,
            handler=handler,
            run_time=run_time,
            _kwargs=kwargs,
        )

    def add_interval(
        self,
        name: str,
        handler: Callable,
        interval: float = 60.0,
        **kwargs,
    ) -> None:
        """添加间隔重复任务。"""
        self._tasks[name] = ScheduledTask(
            name=name,
            task_type=TaskType.INTERVAL,
            handler=handler,
            interval_seconds=interval,
            _kwargs=kwargs,
        )

    def add_daily(
        self,
        name: str,
        handler: Callable,
        run_time: time = time(8, 0),
        **kwargs,
    ) -> None:
        """添加每日定时任务（不限交易日）。"""
        self._tasks[name] = ScheduledTask(
            name=name,
            task_type=TaskType.DAILY,
            handler=handler,
            run_time=run_time,
            _kwargs=kwargs,
        )

    def remove_task(self, name: str) -> bool:
        return self._tasks.pop(name, None) is not None

    def enable_task(self, name: str) -> None:
        if name in self._tasks:
            self._tasks[name].enabled = True

    def disable_task(self, name: str) -> None:
        if name in self._tasks:
            self._tasks[name].enabled = False

    async def start(self) -> None:
        """启动调度器主循环。"""
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._main_loop())
        logger.info(f"TaskScheduler started with {len(self._tasks)} tasks")

    async def stop(self) -> None:
        """停止调度器。"""
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            self._loop_task = None
        logger.info("TaskScheduler stopped")

    async def run_task_now(self, name: str) -> dict:
        """立即手动执行指定任务。"""
        task = self._tasks.get(name)
        if not task:
            return {"error": f"Task not found: {name}"}
        return await self._execute_task(task)

    async def _main_loop(self) -> None:
        """调度主循环：每 30 秒检查一次是否有需要执行的任务。"""
        try:
            while self._running:
                now = datetime.now()
                for task in self._tasks.values():
                    if not task.enabled:
                        continue
                    if self._should_run(task, now):
                        await self._execute_task(task)
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            pass

    def _should_run(self, task: ScheduledTask, now: datetime) -> bool:
        """判断任务是否应该在当前时刻执行。"""
        if task.task_type == TaskType.INTERVAL:
            if task.last_run is None:
                return True
            elapsed = (now - task.last_run).total_seconds()
            return elapsed >= task.interval_seconds

        if task.run_time is None:
            return False

        if task.last_run and task.last_run.date() == now.date():
            return False

        current_time = now.time()
        target = task.run_time
        within_window = (
            target
            <= current_time
            <= time(target.hour, target.minute + 1 if target.minute < 59 else target.minute)
        )

        if not within_window:
            return False

        if task.task_type in (TaskType.PRE_MARKET, TaskType.POST_MARKET):
            return is_trading_day(now)

        return True  # DAILY

    async def _execute_task(self, task: ScheduledTask) -> dict:
        """执行单个任务并记录结果。"""
        logger.info(f"Executing scheduled task: {task.name}")
        try:
            result = task.handler(**task._kwargs)
            if asyncio.iscoroutine(result):
                result = await result

            task.last_run = datetime.now()
            task.run_count += 1
            logger.info(f"Task completed: {task.name} (#{task.run_count})")
            return {"task": task.name, "status": "success", "run_count": task.run_count}
        except Exception as e:
            task.error_count += 1
            task.last_error = str(e)
            task.last_run = datetime.now()
            logger.error(f"Task failed: {task.name}: {e}")
            return {"task": task.name, "status": "error", "error": str(e)}

    def get_status(self) -> dict:
        """返回调度器状态摘要。"""
        return {
            "running": self._running,
            "task_count": len(self._tasks),
            "tasks": [
                {
                    "name": t.name,
                    "type": t.task_type.value,
                    "enabled": t.enabled,
                    "run_time": t.run_time.isoformat() if t.run_time else None,
                    "interval": t.interval_seconds if t.task_type == TaskType.INTERVAL else None,
                    "last_run": t.last_run.isoformat() if t.last_run else None,
                    "run_count": t.run_count,
                    "error_count": t.error_count,
                    "last_error": t.last_error,
                }
                for t in self._tasks.values()
            ],
        }
