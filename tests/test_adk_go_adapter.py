from __future__ import annotations

import pytest
from pydantic import ValidationError

from valo_gateway.protocols import ADKGoIngress
from valo_gateway.runtime_adapters import (
    ADKCredentialBinding,
    ADKGoInvocationContext,
    ADKGoRuntime,
    ADKRegistryRecord,
    ADKTaskBinding,
    ADKToolConfirmation,
    assert_confirmation_matches,
    validate_task_fanout,
)


def _payload() -> dict:
    return {
        "valo_action": {
            "action_type": "mcp.tool.call",
            "target": "crm://customer/42",
            "parameters": {"tool": "update_customer", "name": "Ada"},
            "context_digest": "ctx-1",
            "policy_digest": "policy-1",
            "authority_envelope_id": "auth-1",
            "nonce": "nonce-1",
        },
        "adk": {
            "runtime_version": "2.1.0",
            "agent_ref": "agent://sales",
            "registry_ref": "registry://prod",
            "model_ref": "openai://gpt",
            "tool_ref": "mcp://crm/update_customer",
            "mcp_server_ref": "mcp://crm",
            "principal_ref": "principal://user/7",
            "actor_ref": "agent://sales",
            "credential": {
                "credential_ref": "credential://vault/crm/user-7",
                "provider_ref": "provider://oauth/crm",
            },
            "task_run_id": "run-1",
            "node_id": "node-1",
            "span_id": "span-1",
            "cancellation_state": "none",
            "confirmation_ref": "confirmation://123",
        },
    }


def test_adk_ingress_keeps_runtime_context_separate_from_action_authority() -> None:
    action, context = ADKGoIngress().normalize_with_context(_payload())
    assert action.authority_envelope_id == "auth-1"
    assert context.runtime == "google-adk-go"
    assert context.credential is not None
    assert context.credential.credential_ref == "credential://vault/crm/user-7"
    assert "credential" not in action.model_dump()


def test_adk_runtime_rejects_authority_fields_in_metadata() -> None:
    with pytest.raises(ValidationError, match="cannot supply authority field"):
        ADKGoInvocationContext(metadata={"nested": {"permit_id": "permit-from-runtime"}})


def test_adk_runtime_rejects_raw_credentials() -> None:
    with pytest.raises(ValidationError, match="cannot carry raw credential material"):
        ADKGoInvocationContext(metadata={"auth": {"access_token": "secret-value"}})

    with pytest.raises(ValidationError):
        ADKCredentialBinding(credential_ref="credential://ref", access_token="secret-value")


def test_registry_is_discovery_metadata_not_authority() -> None:
    record = ADKRegistryRecord(kind="mcp_server", ref="mcp://crm", name="CRM")
    assert record.ref == "mcp://crm"

    with pytest.raises(ValidationError, match="cannot supply authority field"):
        ADKRegistryRecord(kind="agent", ref="agent://x", metadata={"clearance_id": "fake"})


def test_taskrunner_fanout_requires_distinct_permits() -> None:
    bindings = [
        ADKTaskBinding(child_id="a", action_digest="digest-a", permit_id="permit-a"),
        ADKTaskBinding(child_id="b", action_digest="digest-b", permit_id="permit-b"),
    ]
    assert validate_task_fanout(bindings) == tuple(bindings)

    with pytest.raises(ValueError, match="cannot reuse one execution permit"):
        validate_task_fanout([
            bindings[0],
            ADKTaskBinding(child_id="b", action_digest="digest-b", permit_id="permit-a"),
        ])


def test_tool_confirmation_is_only_exact_action_evidence() -> None:
    confirmation = ADKToolConfirmation(confirmation_ref="confirmation://123", action_digest="digest-a")
    assert_confirmation_matches("digest-a", confirmation)

    with pytest.raises(ValueError, match="action binding mismatch"):
        assert_confirmation_matches("digest-b", confirmation)


def test_adk_runtime_adapter_preserves_context_as_non_authoritative_runtime_data() -> None:
    runtime = ADKGoRuntime()
    context = ADKGoInvocationContext(
        runtime_version="2.1.0",
        model_ref="openai://gpt",
        task_run_id="run-1",
        registry_records=(ADKRegistryRecord(kind="model_endpoint", ref="model://openai"),),
    )
    action_id = runtime.submit_with_context({"type": "tool.call"}, context)
    events = runtime.stream(action_id)
    result = runtime.result(action_id)

    assert events[0].kind == "ACTION_REQUESTED"
    assert events[0].payload["backend"] == "google-adk-go"
    assert result.outputs["executed_by"] == "google-adk-go"
