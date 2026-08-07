from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.conftest import make_chain
from valo_gateway.runtime_adapters import (
    ADKGoInvocationContext,
    ADKTaskRunnerGate,
    ADKToolConfirmation,
)
from valo_gateway.tool_adapters import FunctionTool


def test_adk_taskrunner_gate_uses_the_existing_one_shot_reht_permit() -> None:
    now, authority, action, clearance, permit = make_chain()
    calls: list[int] = []
    gate = ADKTaskRunnerGate()
    context = ADKGoInvocationContext(runtime_version="2.1.0", agent_ref="agent://worker")
    tool = FunctionTool("payment", lambda amount: calls.append(amount) or {"ok": True})

    result = gate.execute_authorized(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        context=context,
        tool=tool,
        arguments={"amount": 1250},
        now=now,
    )

    assert calls == [1250]
    assert result.receipt.executor_id == "google-adk-go:agent://worker"
    assert result.consumed_permit.consumed_at is not None

    with pytest.raises(ValueError, match="already consumed"):
        gate.execute_authorized(
            authority=authority,
            clearance=clearance,
            permit=permit,
            action=action,
            context=context,
            tool=tool,
            arguments={"amount": 1250},
            now=now,
        )
    assert calls == [1250]


def test_adk_confirmation_cannot_change_the_authorized_action() -> None:
    now, authority, action, clearance, permit = make_chain()
    calls: list[int] = []
    gate = ADKTaskRunnerGate()
    context = ADKGoInvocationContext(
        runtime_version="2.1.0",
        agent_ref="agent://worker",
        confirmation_ref="confirmation://1",
    )
    confirmation = ADKToolConfirmation(
        confirmation_ref="confirmation://1",
        action_digest="different-action",
    )

    with pytest.raises(ValueError, match="action binding mismatch"):
        gate.execute_authorized(
            authority=authority,
            clearance=clearance,
            permit=permit,
            action=action,
            context=context,
            confirmation=confirmation,
            tool=FunctionTool("payment", lambda amount: calls.append(amount)),
            arguments={"amount": 1250},
            now=now,
        )

    assert calls == []
    assert permit.consumed_at is None


def test_adk_runtime_metadata_cannot_mint_authority_or_permits() -> None:
    with pytest.raises(ValidationError, match="cannot supply authority field"):
        ADKGoInvocationContext(
            runtime_version="2.1.0",
            metadata={
                "agent_registry": {
                    "decision": "ALLOW",
                    "clearance_id": "runtime-clearance",
                    "permit_id": "runtime-permit",
                }
            },
        )


def test_adk_credentials_are_opaque_references_not_bearer_material() -> None:
    context = ADKGoInvocationContext.model_validate({
        "runtime_version": "2.1.0",
        "credential": {"credential_ref": "credential://vault/item/42"},
    })
    assert context.credential is not None
    assert context.credential.credential_ref == "credential://vault/item/42"

    with pytest.raises(ValidationError):
        ADKGoInvocationContext.model_validate({
            "runtime_version": "2.1.0",
            "credential": {
                "credential_ref": "credential://vault/item/42",
                "authorization": "Bearer raw-secret",
            },
        })
