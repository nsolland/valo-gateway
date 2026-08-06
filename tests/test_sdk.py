"""End-to-end SDK composition: ingress -> harness -> gateway -> receipt."""
from __future__ import annotations

import pytest

from tests.conftest import make_chain
from valo_gateway import ExecutionStatus
from valo_gateway.gateway import RuntimeControlPlane
from valo_gateway.harness import HarnessRouter
from valo_gateway.protocols import MCPIngress
from valo_gateway.runtime_adapters import LocalRuntime
from valo_gateway.sdk import GatewaySDK
from valo_gateway.tool_adapters import FunctionTool, ToolRegistry


def build_sdk():
    ingress = MCPIngress()
    router = HarnessRouter({"local": LocalRuntime()}, default="local")
    tools = ToolRegistry()
    tools.register(FunctionTool("payments", lambda amount: {"accepted": True, "amount": amount}))
    sdk = GatewaySDK.compose(ingress=ingress, harness=router, tools=tools)
    return sdk


def test_sdk_end_to_end_success():
    now, authority, action, clearance, permit = make_chain()
    sdk = build_sdk()
    action_id = sdk.harness.submit(action.model_dump(), runtime="local")
    result = sdk.gateway.execute(
        authority=authority, clearance=clearance, permit=permit,
        action=action, executor_id="tool:payments",
        tool=sdk.tools.get("payments"), arguments={"amount": 1250}, now=now,
    )
    assert result.consumed_permit.consumed_at == now
    assert result.receipt.status == ExecutionStatus.SUCCEEDED
    assert result.receipt.permit_id == permit.permit_id
    assert action_id.startswith("act-")


def test_sdk_fail_closed_on_missing_tool():
    sdk = build_sdk()
    with pytest.raises(KeyError, match="tool not registered"):
        sdk.tools.get("nonexistent")


def test_sdk_fail_closed_on_unknown_runtime():
    sdk = build_sdk()
    with pytest.raises(KeyError, match="runtime adapter not registered"):
        sdk.harness.submit({"type": "x"}, runtime="unknown")


def test_sdk_compose_wires_control_plane():
    control = RuntimeControlPlane()
    sdk = GatewaySDK.compose(
        ingress=MCPIngress(),
        harness=HarnessRouter({"local": LocalRuntime()}),
        tools=ToolRegistry(),
        control_plane=control,
    )
    assert sdk.gateway._control_plane is control


def test_sdk_ingress_normalizes_to_action_envelope():
    sdk = build_sdk()
    normalized = sdk.ingress.normalize({
        "action_type": "payment.submit", "target": "invoice:123",
        "parameters": {}, "context_digest": "ctx", "policy_digest": "p",
        "authority_envelope_id": "env",
    })
    assert normalized.action_type == "payment.submit"
    assert normalized.target == "invoice:123"
