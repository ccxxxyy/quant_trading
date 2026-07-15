"""进程守护器 - 监控子进程健康状况，崩溃时自动重启。

支持功能：
    - 启动并监控多个子进程（策略运行器、行情服务、Web 服务等）
    - 崩溃自动重启（带指数退避冷却）
    - 最大重启次数限制
    - 健康检查（HTTP endpoint / 心跳文件）
    - 运行状态查询
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ProcessState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    CRASHED = "crashed"
    RESTARTING = "restarting"
    MAX_RESTARTS = "max_restarts_reached"


@dataclass
class GuardedProcess:
    """被守护的进程定义。"""

    name: str
    command: list[str]
    max_restarts: int = 10
    cooldown_base: float = 2.0
    cooldown_max: float = 120.0
    health_url: str | None = None
    heartbeat_file: str | None = None

    state: ProcessState = ProcessState.STOPPED
    process: Any = None
    pid: int | None = None
    restart_count: int = 0
    last_start: float | None = None
    last_crash: float | None = None
    uptime_seconds: float = 0
    _exit_codes: list[int] = field(default_factory=list)


class ProcessGuardian:
    """进程守护器：监控子进程，崩溃时自动重启。

    使用方式::

        guardian = ProcessGuardian()

        guardian.add_process(
            name="web-server",
            command=["uv", "run", "quant-web"],
            max_restarts=5,
        )
        guardian.add_process(
            name="strategy-runner",
            command=["uv", "run", "python", "-m", "quant_trading.strategy.runner"],
            max_restarts=10,
        )

        await guardian.start()
    """

    def __init__(self) -> None:
        self._processes: dict[str, GuardedProcess] = {}
        self._running = False
        self._monitor_tasks: dict[str, asyncio.Task] = {}

    @property
    def running(self) -> bool:
        return self._running

    def add_process(
        self,
        name: str,
        command: list[str],
        max_restarts: int = 10,
        cooldown_base: float = 2.0,
        cooldown_max: float = 120.0,
        health_url: str | None = None,
        heartbeat_file: str | None = None,
    ) -> None:
        """注册一个需要守护的进程。"""
        self._processes[name] = GuardedProcess(
            name=name,
            command=command,
            max_restarts=max_restarts,
            cooldown_base=cooldown_base,
            cooldown_max=cooldown_max,
            health_url=health_url,
            heartbeat_file=heartbeat_file,
        )

    async def start(self) -> None:
        """启动所有已注册的进程并开始监控。"""
        if self._running:
            return
        self._running = True

        for name, proc in self._processes.items():
            task = asyncio.create_task(self._monitor_process(proc))
            self._monitor_tasks[name] = task

        logger.info(f"ProcessGuardian started, monitoring {len(self._processes)} processes")

    async def stop(self) -> None:
        """停止所有进程和监控。"""
        self._running = False

        for task in self._monitor_tasks.values():
            task.cancel()
        self._monitor_tasks.clear()

        for proc in self._processes.values():
            await self._kill_process(proc)

        logger.info("ProcessGuardian stopped")

    async def restart_process(self, name: str) -> dict:
        """手动重启指定进程。"""
        proc = self._processes.get(name)
        if not proc:
            return {"error": f"Process not found: {name}"}

        await self._kill_process(proc)
        proc.restart_count = 0
        proc.state = ProcessState.STOPPED

        if name in self._monitor_tasks:
            self._monitor_tasks[name].cancel()
        self._monitor_tasks[name] = asyncio.create_task(self._monitor_process(proc))

        return {"status": "restarting", "name": name}

    async def stop_process(self, name: str) -> dict:
        """停止指定进程（不自动重启）。"""
        proc = self._processes.get(name)
        if not proc:
            return {"error": f"Process not found: {name}"}

        if name in self._monitor_tasks:
            self._monitor_tasks[name].cancel()
            del self._monitor_tasks[name]

        await self._kill_process(proc)
        proc.state = ProcessState.STOPPED
        return {"status": "stopped", "name": name}

    # ------------------------------------------------------------------
    # 进程监控循环
    # ------------------------------------------------------------------

    async def _monitor_process(self, proc: GuardedProcess) -> None:
        """单个进程的监控循环：启动 → 等待退出 → 判断重启。"""
        try:
            while self._running:
                if proc.restart_count >= proc.max_restarts:
                    proc.state = ProcessState.MAX_RESTARTS
                    logger.error(
                        f"Process '{proc.name}' reached max restarts "
                        f"({proc.max_restarts}), giving up"
                    )
                    return

                await self._start_process(proc)

                if proc.process is None:
                    await asyncio.sleep(5)
                    continue

                exit_code = await proc.process.wait()
                proc._exit_codes.append(exit_code)
                crash_time = time.time()
                proc.last_crash = crash_time

                if proc.last_start:
                    proc.uptime_seconds = crash_time - proc.last_start

                if not self._running:
                    break

                if exit_code == 0:
                    logger.info(f"Process '{proc.name}' exited normally (code 0)")
                    proc.state = ProcessState.STOPPED
                    return

                proc.state = ProcessState.CRASHED
                proc.restart_count += 1
                delay = self._cooldown_delay(proc)

                logger.warning(
                    f"Process '{proc.name}' crashed (code {exit_code}), "
                    f"restart #{proc.restart_count} in {delay:.1f}s"
                )

                proc.state = ProcessState.RESTARTING
                await asyncio.sleep(delay)

        except asyncio.CancelledError:
            pass

    async def _start_process(self, proc: GuardedProcess) -> None:
        """启动子进程。"""
        proc.state = ProcessState.STARTING
        try:
            proc.process = await asyncio.create_subprocess_exec(
                *proc.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            proc.pid = proc.process.pid
            proc.last_start = time.time()
            proc.state = ProcessState.RUNNING
            logger.info(f"Started process '{proc.name}' (PID {proc.pid}): {' '.join(proc.command)}")
        except Exception as e:
            proc.state = ProcessState.CRASHED
            proc.process = None
            logger.error(f"Failed to start '{proc.name}': {e}")

    async def _kill_process(self, proc: GuardedProcess) -> None:
        """终止子进程。"""
        if proc.process is None:
            return
        try:
            proc.process.terminate()
            try:
                await asyncio.wait_for(proc.process.wait(), timeout=5.0)
            except TimeoutError:
                proc.process.kill()
                await proc.process.wait()
            logger.info(f"Killed process '{proc.name}' (PID {proc.pid})")
        except Exception as e:
            logger.warning(f"Error killing '{proc.name}': {e}")
        finally:
            proc.process = None
            proc.pid = None

    def _cooldown_delay(self, proc: GuardedProcess) -> float:
        """指数退避冷却延迟。"""
        delay = min(
            proc.cooldown_base * (2 ** (proc.restart_count - 1)),
            proc.cooldown_max,
        )
        return delay

    # ------------------------------------------------------------------
    # 健康检查
    # ------------------------------------------------------------------

    async def check_health(self, name: str) -> dict:
        """检查指定进程的健康状态。"""
        proc = self._processes.get(name)
        if not proc:
            return {"name": name, "healthy": False, "reason": "not found"}

        if proc.state != ProcessState.RUNNING:
            return {"name": name, "healthy": False, "reason": proc.state.value}

        if proc.heartbeat_file:
            hb_path = Path(proc.heartbeat_file)
            if hb_path.exists():
                age = time.time() - hb_path.stat().st_mtime
                if age > 60:
                    return {
                        "name": name,
                        "healthy": False,
                        "reason": f"heartbeat stale ({age:.0f}s)",
                    }
            else:
                return {"name": name, "healthy": False, "reason": "no heartbeat file"}

        if proc.health_url:
            try:
                import urllib.request

                with urllib.request.urlopen(proc.health_url, timeout=5) as resp:
                    if resp.status != 200:
                        return {"name": name, "healthy": False, "reason": f"HTTP {resp.status}"}
            except Exception as e:
                return {"name": name, "healthy": False, "reason": str(e)}

        return {"name": name, "healthy": True, "pid": proc.pid}

    def get_status(self) -> dict:
        """返回所有进程的状态摘要。"""
        return {
            "running": self._running,
            "process_count": len(self._processes),
            "processes": [
                {
                    "name": p.name,
                    "state": p.state.value,
                    "pid": p.pid,
                    "restart_count": p.restart_count,
                    "max_restarts": p.max_restarts,
                    "uptime_seconds": round(
                        time.time() - p.last_start
                        if p.last_start and p.state == ProcessState.RUNNING
                        else 0,
                        1,
                    ),
                    "last_crash": (
                        datetime.fromtimestamp(p.last_crash).isoformat() if p.last_crash else None
                    ),
                    "exit_codes": p._exit_codes[-5:],
                }
                for p in self._processes.values()
            ],
        }
