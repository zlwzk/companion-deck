"""适配器注册表：管理已注册适配器与当前激活的适配器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deck.adapters.base import BaseAdapter


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, BaseAdapter] = {}
        self._active: BaseAdapter | None = None

    def register(self, adapter: "BaseAdapter") -> None:
        self._adapters[adapter.name] = adapter

    def activate(self, name: str) -> "BaseAdapter":
        if name not in self._adapters:
            raise KeyError(name)
        if self._active is not None:
            self._active.deactivate()
        self._active = self._adapters[name]
        self._active.activate()
        return self._active

    @property
    def active(self) -> "BaseAdapter | None":
        return self._active

    def all(self) -> list["BaseAdapter"]:
        return list(self._adapters.values())
