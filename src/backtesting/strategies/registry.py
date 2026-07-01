"""Strategy discovery + registration."""

from __future__ import annotations

from typing import Type


class _Registry:
    def __init__(self):
        self._strategies: dict[str, Type] = {}

    def register(self, cls: Type) -> None:
        name = getattr(cls, "name", None) or cls.__name__
        self._strategies[name] = cls

    def get(self, name: str):
        return self._strategies.get(name)

    def list_names(self) -> list[str]:
        return sorted(self._strategies.keys())

    def list_strategies(self) -> list[Type]:
        return [self._strategies[n] for n in self.list_names()]


registry = _Registry()
