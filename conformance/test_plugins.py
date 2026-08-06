import pytest

from valo_gateway.harness import HarnessRouter
from valo_gateway.protocols import (
    A2AIngress,
    ExtAuthzIngress,
    GRPCIngress,
    HTTPIngress,
    MCPIngress,
)
from valo_gateway.runtime_adapters import (
    ClaudeRuntime,
    GoogleRuntime,
    LocalRuntime,
    OpenAIRuntime,
)


@pytest.mark.parametrize("adapter", [LocalRuntime(), OpenAIRuntime(), ClaudeRuntime(), GoogleRuntime()])
def test_runtime_contract(adapter):
    action_id = adapter.submit({"type": "test"})
    assert adapter.stream(action_id)[0].kind == "ACTION_REQUESTED"
    assert adapter.checkpoint(action_id).digest.startswith("sha256:")
    assert adapter.result(action_id).status == "SUCCESS"

@pytest.mark.parametrize("ingress", [MCPIngress(), A2AIngress(), HTTPIngress(), GRPCIngress(), ExtAuthzIngress()])
def test_protocols_only_normalize(ingress):
    action = ingress.normalize({"action_type":"x","target":"y","parameters":{},"context_digest":"c","policy_digest":"p","authority_envelope_id":"a"})
    assert action.action_type == "x"

def test_harness_router_is_vendor_neutral():
    router = HarnessRouter({"local": LocalRuntime(), "claude": ClaudeRuntime()})
    assert router.select("claude").backend == "claude"
