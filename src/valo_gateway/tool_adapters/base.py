from __future__ import annotations

from collections.abc import Callable
from typing import Any


class FunctionTool:
    def __init__(self, name: str, function: Callable[..., Any],
                 capabilities: list[str] | None = None) -> None:
        self.name = name
        self.capabilities = list(capabilities or [])
        self._function = function

    def invoke(self, arguments: dict[str, Any]) -> Any:
        return self._function(**arguments)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, FunctionTool] = {}

    def register(self, tool: FunctionTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> FunctionTool:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"tool not registered: {name}") from exc
