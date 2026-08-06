from __future__ import annotations

from typing import Any

from .runtime import RuntimeAdapter


class HarnessRouter:
    def __init__(self, runtimes: dict[str, RuntimeAdapter], default: str = "local") -> None:
        if default not in runtimes:
            raise ValueError("default runtime is not registered")
        self._runtimes = dict(runtimes)
        self.default = default
    def select(self, name: str | None = None) -> RuntimeAdapter:
        key = name or self.default
        try:
            return self._runtimes[key]
        except KeyError as exc:
            raise KeyError(f"runtime adapter not registered: {key}") from exc
    def submit(self, action: dict[str, Any], runtime: str | None = None) -> str:
        return self.select(runtime).submit(action)
