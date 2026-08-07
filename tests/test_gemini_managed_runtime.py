import pytest

from valo_gateway.runtime_adapters import GeminiExecutionContext, GeminiManagedRuntime


def _context(**changes):
    values = {
        "interaction_id": "interaction-123",
        "environment_id": "environment-456",
        "background": True,
        "credential_context_fingerprint": "sha256:" + "a" * 64,
        "substrate_grant_ref": "grant-ref-opaque",
    }
    values.update(changes)
    return GeminiExecutionContext(**values)


def test_requires_action_normalizes_proposal_without_authority():
    runtime = GeminiManagedRuntime()
    proposal = runtime.normalize_requires_action(
        context=_context(),
        tool_name="send_payment",
        action_type="payment.send",
        target="account:vendor-7",
        arguments={"amount": 125, "currency": "EUR"},
    )

    action = proposal.to_runtime_action()
    assert action["type"] == "payment.send"
    assert action["runtime_context"]["source_kind"] == "requires_action"
    assert action["runtime_context"]["route"] == "valo-gateway"
    assert action["execution_context_hash"].startswith("sha256:")

    forbidden = {
        "authority_envelope_id",
        "clearance_id",
        "permit_id",
        "decision",
        "policy_digest",
    }
    assert forbidden.isdisjoint(action)
    assert forbidden.isdisjoint(action["runtime_context"])


def test_execution_context_hash_is_deterministic_and_context_sensitive():
    runtime = GeminiManagedRuntime()

    def normalize(context, arguments):
        return runtime.normalize_requires_action(
            context=context,
            tool_name="write_record",
            action_type="record.write",
            target="records:42",
            arguments=arguments,
        ).execution_context_hash

    baseline = normalize(_context(), {"b": 2, "a": 1})
    reordered = normalize(_context(), {"a": 1, "b": 2})
    assert baseline == reordered
    assert baseline != normalize(_context(environment_id="environment-new"), {"a": 1, "b": 2})
    assert baseline != normalize(_context(background=False), {"a": 1, "b": 2})
    assert baseline != normalize(
        _context(credential_context_fingerprint="sha256:" + "b" * 64),
        {"a": 1, "b": 2},
    )
    assert baseline != normalize(_context(), {"a": 1, "b": 3})


def test_remote_mcp_is_marked_for_gateway_routing():
    runtime = GeminiManagedRuntime()
    proposal = runtime.normalize_remote_mcp(
        context=_context(),
        server_name="internal-finance-mcp",
        tool_name="create_invoice",
        action_type="invoice.create",
        target="ledger:customer-8",
        arguments={"amount": 900},
    )

    action = proposal.to_runtime_action()
    assert action["runtime_context"]["source_kind"] == "remote_mcp"
    assert action["runtime_context"]["source_ref"] == "internal-finance-mcp"
    assert action["runtime_context"]["route"] == "valo-gateway"


def test_credential_context_accepts_only_fingerprint_reference():
    with pytest.raises(ValueError, match="sha256 fingerprint"):
        GeminiExecutionContext(
            interaction_id="interaction-1",
            environment_id="environment-1",
            credential_context_fingerprint="raw-secret-value",
        )


def test_required_runtime_bindings_fail_closed():
    runtime = GeminiManagedRuntime()
    with pytest.raises(ValueError, match="interaction_id"):
        _context(interaction_id="")
    with pytest.raises(ValueError, match="environment_id"):
        _context(environment_id="")
    with pytest.raises(ValueError, match="tool_name"):
        runtime.normalize_requires_action(
            context=_context(),
            tool_name="",
            action_type="x",
            target="y",
        )
    with pytest.raises(ValueError, match="server_name"):
        runtime.normalize_remote_mcp(
            context=_context(),
            server_name="",
            tool_name="x",
            action_type="x",
            target="y",
        )
