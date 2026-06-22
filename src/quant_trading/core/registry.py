"""组件注册中心 - 管理系统中所有组件的生命周期。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class Component:
    """所有系统组件的基类。"""

    def __init__(self, name: str) -> None:
        self._name = name
        self._started = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_started(self) -> bool:
        return self._started

    def start(self) -> None:
        self._started = True
        logger.info(f"Component started: {self._name}")

    def stop(self) -> None:
        self._started = False
        logger.info(f"Component stopped: {self._name}")


class ComponentRegistry:
    """组件注册中心，统一管理组件的注册和生命周期。"""

    def __init__(self) -> None:
        self._components: dict[str, Any] = {}

    def register(self, name: str, component: Any) -> None:
        """按名称注册一个组件。"""
        if name in self._components:
            raise ValueError(f"Component already registered: {name}")
        self._components[name] = component
        logger.debug(f"Registered component: {name}")

    def get(self, name: str) -> Any:
        """按名称获取已注册的组件。"""
        component = self._components.get(name)
        if component is None:
            raise KeyError(f"Component not found: {name}")
        return component

    def get_optional(self, name: str) -> Any | None:
        """获取组件，如果未注册则返回 None。"""
        return self._components.get(name)

    def has(self, name: str) -> bool:
        return name in self._components

    def all(self) -> dict[str, Any]:
        return dict(self._components)

    def start_all(self) -> None:
        """启动所有已注册且具有 start 方法的组件。"""
        for name, component in self._components.items():
            if hasattr(component, "start") and callable(component.start):
                component.start()

    def stop_all(self) -> None:
        """按注册的逆序停止所有组件。"""
        for name in reversed(list(self._components.keys())):
            component = self._components[name]
            if hasattr(component, "stop") and callable(component.stop):
                component.stop()

    def clear(self) -> None:
        self.stop_all()
        self._components.clear()
