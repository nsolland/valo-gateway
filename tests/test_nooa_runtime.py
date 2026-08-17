from __future__ import annotations

import pytest

from valo_gateway.harness import HarnessRouter
from valo_gateway.runtime_adapters import (
    NOOAExecutionContext,
    NOOAMethodMode,
    NOOAObjectReference,
    NOOARuntime,
)


def _context() -> NOOAExecutionContext:
    return NOOAExecutionContext(
        agent_class="SupportAgent",
        agent_ref="agent:support:42",
        workspace_ref="workspace:customer-support",
        state_ref="state:customer-support:current",
        source_revision="git:abc123",
    )


def test_nooa_context_requires_governed_state_binding() -> None:
    with pytest.raises(ValueError, match="state_ref is required"):
        NOOAExecutionContext(
            agent_class="SupportAgent",
            agent_ref="agent:support:42",
            workspace_ref="workspace:customer-support",
            state_ref="",
        )


def test_nooa_object_reference_is_opaque_and_fresh_at_execution() -> None:
    ref = NOOAObjectReference("order:123", "Order")
    assert ref.to_binding() == {
        "ref": "order:123",
        "type_name": "Order",
        "resolver": "governed-state",
        "resolve_at_execution": True,
    }


def test_nooa_typed_method_projects_to_gateway_action() -> None:
    runtime = NOOARuntime()
    proposal = runtime.normalize_method(
        context=_context(),
        method_name="refund_order",
        method_mode=NOOAMethodMode.AGENTIC,
        signature="async def refund_order(order: Order, reason: str) -> Refund",
        action_type="REFUND_ORDER",
        target="order:123",
        arguments={"reason": "damaged"},
        object_refs={"order": NOOAObjectReference("order:123", "Order")},
        consequence_bearing=True,
    )

    action = proposal.to_runtime_action()
    context = action["runtime_context"]
    assert action["type"] == "REFUND_ORDER"
    assert action["parameters"] == {"reason": "damaged"}
    assert context["method_name"] == "refund_order"
    assert context["signature"].startswith("async def refund_order")
    assert context["object_refs"]["order"]["ref"] == "order:123"
    assert context["resolve_object_refs_at_execution"] is True
    assert context["fresh_state_required"] is True
    assert context["direct_effect_path"] is False
    assert context["route"] == "valo-gateway"


def test_nooa_direct_effect_path_is_rejected() -> None:
    runtime = NOOARuntime()
    with pytest.raises(ValueError, match="direct effect path is forbidden"):
        runtime.normalize_method(
            context=_context(),
            method_name="refund_order",
            signature="def refund_order(order: Order) -> Refund",
            action_type="REFUND_ORDER",
            target="order:123",
            direct_effect=True,
        )


def test_nooa_state_mutation_requires_governed_admission() -> None:
    runtime = NOOARuntime()
    proposal = runtime.normalize_method(
        context=_context(),
        method_name="remember_preference",
        signature="def remember_preference(value: Preference) -> None",
        action_type="WRITE_MEMORY",
        target="agent:support:42",
        state_mutation=True,
    )

    context = proposal.to_runtime_action()["runtime_context"]
    assert context["state_mutation"] is True
    assert context["state_mutation_requires_admission"] is True
    assert context["direct_effect_path"] is False


def test_nooa_argument_cannot_bypass_reference_binding() -> None:
    runtime = NOOARuntime()
    with pytest.raises(ValueError, match="arguments and object_refs overlap: order"):
        runtime.normalize_method(
            context=_context(),
            method_name="inspect_order",
            signature="def inspect_order(order: Order) -> str",
            action_type="INSPECT_ORDER",
            target="order:123",
            arguments={"order": {"status": "stale-snapshot"}},
            object_refs={"order": NOOAObjectReference("order:123", "Order")},
        )


def test_harness_router_accepts_nooa_as_replaceable_runtime() -> None:
    runtime = NOOARuntime()
    router = HarnessRouter({"nooa": runtime}, default="nooa")
    proposal = runtime.normalize_method(
        context=_context(),
        method_name="triage",
        signature="async def triage(message: str) -> Ticket",
        action_type="TRIAGE",
        target="queue:support",
        arguments={"message": "shipping delay"},
    )

    action_id = router.submit(proposal.to_runtime_action())
    event = runtime.stream(action_id)[0]
    assert event.kind == "ACTION_REQUESTED"
    assert event.source == "nooa"
