import pytest

from valo_gateway.runtime_adapters import (
    BlandExecutionContext,
    BlandExecutionSurface,
    BlandRuntime,
)


def _context(**changes):
    values = {
        "organization_ref": "org:primary",
        "call_ref": "call:42",
        "conversation_ref": "conversation:42",
        "persona_ref": "persona:support",
        "pathway_ref": "pathway:refunds",
        "pathway_version_ref": "pathway-version:17",
        "node_ref": "node:refund-tool",
        "channel": "voice",
        "release_ref": "release:canary-17",
        "memory_context_ref": "memory:customer-8",
        "credential_context_fingerprint": "sha256:" + "b" * 64,
    }
    values.update(changes)
    return BlandExecutionContext(**values)


def _assert_non_authoritative(action):
    forbidden = {
        "authority_envelope_id",
        "clearance_id",
        "permit_id",
        "decision",
        "policy_digest",
        "authorization",
        "api_token",
        "api_key",
    }
    assert forbidden.isdisjoint(action)
    assert forbidden.isdisjoint(action["runtime_context"])


def test_custom_tool_normalizes_to_gateway_without_authority():
    runtime = BlandRuntime()
    proposal = runtime.normalize_custom_tool(
        context=_context(),
        tool_name="refund_customer",
        action_type="payment.refund",
        target="payment:customer-8",
        arguments={"amount": 18000, "currency": "NOK"},
    )

    action = proposal.to_runtime_action()
    assert proposal.surface is BlandExecutionSurface.CUSTOM_TOOL
    assert action["runtime_context"]["substrate"] == "bland"
    assert action["runtime_context"]["surface"] == "custom_tool"
    assert action["runtime_context"]["route"] == "valo-gateway"
    assert action["execution_context_hash"].startswith("sha256:")
    _assert_non_authoritative(action)


def test_provider_native_consequences_share_the_same_boundary_contract():
    runtime = BlandRuntime()
    context = _context()

    outbound = runtime.normalize_outbound_call(
        context=context,
        agent_ref="persona:support",
        target="tel:+4712345678",
    ).to_runtime_action()
    message = runtime.normalize_message(
        context=context,
        agent_ref="persona:support",
        target="sms:+4712345678",
        arguments={"body_ref": "message:approved-template"},
    ).to_runtime_action()
    transfer = runtime.normalize_transfer(
        context=context,
        agent_ref="persona:support",
        target="queue:human-billing",
    ).to_runtime_action()

    assert outbound["runtime_context"]["surface"] == "outbound_call"
    assert message["runtime_context"]["surface"] == "message"
    assert transfer["runtime_context"]["surface"] == "transfer"
    for action in (outbound, message, transfer):
        assert action["runtime_context"]["route"] == "valo-gateway"
        _assert_non_authoritative(action)


def test_context_hash_binds_runtime_version_conversation_and_arguments():
    runtime = BlandRuntime()

    def normalize(context, arguments):
        return runtime.normalize_custom_tool(
            context=context,
            tool_name="update_crm",
            action_type="crm.record.update",
            target="crm:customer-8",
            arguments=arguments,
        ).execution_context_hash

    baseline = normalize(_context(), {"b": 2, "a": 1})
    reordered = normalize(_context(), {"a": 1, "b": 2})
    assert baseline == reordered
    assert baseline != normalize(
        _context(pathway_version_ref="pathway-version:18"), {"a": 1, "b": 2}
    )
    assert baseline != normalize(_context(node_ref="node:other"), {"a": 1, "b": 2})
    assert baseline != normalize(_context(channel="sms"), {"a": 1, "b": 2})
    assert baseline != normalize(_context(call_ref="call:43"), {"a": 1, "b": 2})
    assert baseline != normalize(_context(), {"a": 1, "b": 3})


def test_memory_release_and_provider_identity_are_context_not_authority():
    action = BlandRuntime().normalize_custom_tool(
        context=_context(),
        tool_name="create_ticket",
        action_type="ticket.create",
        target="support:ticket",
    ).to_runtime_action()

    context = action["runtime_context"]
    assert context["release_ref"] == "release:canary-17"
    assert context["memory_context_ref"] == "memory:customer-8"
    assert context["persona_ref"] == "persona:support"
    assert context["pathway_version_ref"] == "pathway-version:17"
    _assert_non_authoritative(action)


def test_transfer_kind_is_bound_and_cannot_be_empty():
    runtime = BlandRuntime()
    warm = runtime.normalize_transfer(
        context=_context(),
        agent_ref="persona:support",
        target="queue:human-billing",
        transfer_kind="warm_transfer",
    )
    cold = runtime.normalize_transfer(
        context=_context(),
        agent_ref="persona:support",
        target="queue:human-billing",
        transfer_kind="cold_transfer",
    )

    assert warm.execution_context_hash != cold.execution_context_hash
    with pytest.raises(ValueError, match="operation"):
        runtime.normalize_transfer(
            context=_context(),
            agent_ref="persona:support",
            target="queue:human-billing",
            transfer_kind="",
        )


def test_credentials_and_required_bindings_fail_closed():
    with pytest.raises(ValueError, match="organization_ref"):
        _context(organization_ref="")
    with pytest.raises(ValueError, match="sha256 fingerprint"):
        _context(credential_context_fingerprint="raw-bland-api-key")

    runtime = BlandRuntime()
    with pytest.raises(ValueError, match="source_ref"):
        runtime.normalize_custom_tool(
            context=_context(),
            tool_name="",
            action_type="x",
            target="y",
        )
    with pytest.raises(ValueError, match="action_type"):
        runtime.normalize_custom_tool(
            context=_context(),
            tool_name="tool",
            action_type="",
            target="y",
        )
    with pytest.raises(ValueError, match="target"):
        runtime.normalize_outbound_call(
            context=_context(),
            agent_ref="persona:support",
            target="",
        )
