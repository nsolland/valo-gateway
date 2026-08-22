"""Tool registry and harness router edge cases."""
from __future__ import annotations

import pytest

from valo_gateway.harness import HarnessRouter
from valo_gateway.runtime_adapters import ClaudeRuntime, LocalRuntime
from valo_gateway.tool_adapters import FunctionTool, ToolRegistry


def test_registry_register_duplicate_rejected():
    reg = ToolRegistry()
    reg.register(FunctionTool("x", lambda: None))
    with pytest.raises(ValueError, match="already registered"):
        reg.register(FunctionTool("x", lambda: None))


def test_registry_get_missing_rejected():
    reg = ToolRegistry()
    with pytest.raises(KeyError, match="tool not registered"):
        reg.get("missing")


def test_registry_returns_opaque_non_invocable_handle():
    reg = ToolRegistry()
    tool = FunctionTool("add", lambda a, b: a + b)
    handle = reg.register(tool, capability="math.add", target="sum:1")
    assert reg.get("add") == handle
    assert not hasattr(handle, "invoke")
    with pytest.raises(PermissionError, match="NO_DIRECT_EFFECT_PATH"):
        tool.invoke({"a": 1, "b": 2})


def test_tool_capabilities_exposed():
    tool = FunctionTool("x", lambda: None, capabilities=["c1", "c2"])
    assert tool.capabilities == ["c1", "c2"]
    assert tool.name == "x"


def test_router_default_runtime_must_be_registered():
    with pytest.raises(ValueError, match="default runtime is not registered"):
        HarnessRouter({"local": LocalRuntime()}, default="missing")


def test_router_select_unknown_rejected():
    router = HarnessRouter({"local": LocalRuntime()})
    with pytest.raises(KeyError, match="runtime adapter not registered"):
        router.select("missing")


def test_router_submit_uses_selected_backend():
    router = HarnessRouter({"local": LocalRuntime(), "claude": ClaudeRuntime()})
    aid = router.submit({"type": "x"}, runtime="claude")
    adapter = router.select("claude")
    assert adapter.stream(aid)[0].kind == "ACTION_REQUESTED"
    assert adapter.stream(aid)[0].source == "claude"


def test_router_default_used_when_none():
    router = HarnessRouter({"local": LocalRuntime()})
    aid = router.submit({"type": "x"})
    assert router.select().stream(aid)[0].source == "local"
