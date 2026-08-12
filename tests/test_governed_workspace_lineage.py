from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from valo_gateway import (
    ActionEnvelope,
    AuthorityEnvelope,
    AuthoritySource,
    Clearance,
    Decision,
    DecisionContract,
    ExecutionPermit,
    GovernedWorkspaceLineage,
    ValoGateway,
    canonical_digest,
    issue_execution_permit,
)
from valo_gateway.tool_adapters import FunctionTool
from valo_gateway.veritas_handoff import build_veritas_execution_observation

DIGEST = "sha256:" + "a" * 64
WORKSPACE_DIGEST = "sha256:" + "b" * 64
KERNEL_CONTEXT_DIGEST = "sha256:" + "c" * 64


def _lineage(now: datetime) -> GovernedWorkspaceLineage:
    return GovernedWorkspaceLineage(
        tenant_id="tenant-1",
        work_unit_id="work-1",
        workspace_id="workspace-1",
        workspace_digest=DIGEST,
        workspace_expires_at=now + timedelta(minutes=2),
        program_ref="program://workspace-1/function-1",
        program_digest=DIGEST,
        invocation_id="invocation-1",
        candidate_id="candidate-1",
        candidate_digest=DIGEST,
        proposed_action_digest=DIGEST,
        conformance_report_id="conformance-1",
        conformance_digest=DIGEST,
        source_state_digest=DIGEST,
        conformed_state_digest=DIGEST,
        source_event_position=42,
        conformed_at=now - timedelta(seconds=1),
        dependency_digest=DIGEST,
        workspace_binding_digest=WORKSPACE_DIGEST,
        kernel_context_digest=KERNEL_CONTEXT_DIGEST,
    )


def _governed_chain(now: datetime | None = None):
    now = now or datetime.now(UTC)
    authority = AuthorityEnvelope(
        principal_id="human:owner",
        actor_id="agent:worker",
        source=AuthoritySource.INTERNAL,
        issuer="valo",
        capability_grants=["payment.submit"],
        resource_scope=["invoice:123"],
        issued_at=now,
        valid_until=now + timedelta(minutes=10),
    )
    lineage = _lineage(now)
    action = ActionEnvelope(
        action_type="payment.submit",
        target="invoice:123",
        parameters={"amount": 1250},
        context_digest="ctx",
        policy_digest="policy",
        authority_envelope_id=authority.envelope_id,
        workspace_binding=lineage,
    )
    contract = DecisionContract(
        decision=Decision.ALLOW,
        principal_id=authority.principal_id,
        actor_id=authority.actor_id,
        action_type=action.action_type,
        target=action.target,
    )
    clearance = Clearance(
        action_digest=action.digest,
        authority_envelope_id=authority.envelope_id,
        decision_contract=contract,
        valid_until=now + timedelta(minutes=5),
        reht_ref="reht:workspace-clearance-1",
        workspace_binding_digest=lineage.workspace_binding_digest,
        kernel_context_digest=lineage.kernel_context_digest,
    )
    permit = issue_execution_permit(
        clearance=clearance,
        authority=authority,
        action=action,
        expires_at=now + timedelta(minutes=1),
        now=now,
    )
    return now, authority, action, clearance, permit


def test_governed_workspace_lineage_propagates_to_receipt_and_veritas_handoff():
    now, authority, action, clearance, permit = _governed_chain()
    result = ValoGateway().execute(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        executor_id="tool:payments",
        tool=FunctionTool("payments", lambda amount: {"accepted": amount}),
        arguments={"amount": 1250},
        now=now,
    )

    expected_clearance_digest = canonical_digest(clearance.model_dump(mode="json"))
    assert permit.workspace_binding_pair == action.workspace_binding_pair
    assert permit.clearance_digest == expected_clearance_digest
    assert result.receipt.workspace_binding_digest == WORKSPACE_DIGEST
    assert result.receipt.kernel_context_digest == KERNEL_CONTEXT_DIGEST
    assert result.receipt.clearance_digest == expected_clearance_digest

    observation = build_veritas_execution_observation(
        authority=authority,
        clearance=clearance,
        action=action,
        result=result,
    )
    assert observation["workspace_binding_digest"] == WORKSPACE_DIGEST
    assert observation["kernel_context_digest"] == KERNEL_CONTEXT_DIGEST
    assert observation["workspace_binding"]["source_event_position"] == 42
    assert observation["workspace_binding"]["candidate_id"] == "candidate-1"
    assert observation["authority_granted"] is False


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (
            Clearance,
            {
                "action_digest": "action",
                "authority_envelope_id": "authority",
                "decision_contract": {
                    "decision": "ALLOW",
                    "principal_id": "principal",
                    "actor_id": "actor",
                    "action_type": "write",
                    "target": "target",
                },
                "valid_until": "2026-08-12T12:00:00Z",
                "reht_ref": "reht:1",
                "workspace_binding_digest": WORKSPACE_DIGEST,
            },
        ),
        (
            ExecutionPermit,
            {
                "clearance_id": "clearance",
                "action_digest": "action",
                "authority_envelope_id": "authority",
                "workspace_binding_digest": WORKSPACE_DIGEST,
                "issued_at": "2026-08-12T11:00:00Z",
                "expires_at": "2026-08-12T11:01:00Z",
            },
        ),
    ],
)
def test_partial_workspace_binding_is_rejected(model, values):
    with pytest.raises(ValidationError, match="must be bound together"):
        model.model_validate(values)


def test_clearance_workspace_drift_fails_before_permit_issuance():
    now, authority, action, clearance, _ = _governed_chain()
    tampered = clearance.model_copy(
        update={"workspace_binding_digest": "sha256:" + "0" * 64}
    )
    with pytest.raises(ValueError, match="clearance workspace binding mismatch"):
        issue_execution_permit(
            clearance=tampered,
            authority=authority,
            action=action,
            expires_at=now + timedelta(minutes=1),
            now=now,
        )


def test_permit_workspace_drift_fails_before_invoke_or_consumption():
    now, authority, action, clearance, permit = _governed_chain()
    tampered = permit.model_copy(
        update={"kernel_context_digest": "sha256:" + "0" * 64}
    )
    calls: list[int] = []

    with pytest.raises(ValueError, match="permit workspace binding mismatch"):
        ValoGateway().execute(
            authority=authority,
            clearance=clearance,
            permit=tampered,
            action=action,
            executor_id="tool:test",
            tool=FunctionTool("x", lambda: calls.append(1)),
            now=now,
        )
    assert calls == []
    assert tampered.consumed_at is None


def test_permit_clearance_digest_drift_fails_before_invoke_or_consumption():
    now, authority, action, clearance, permit = _governed_chain()
    tampered = permit.model_copy(update={"clearance_digest": "tampered"})
    calls: list[int] = []

    with pytest.raises(ValueError, match="permit clearance digest mismatch"):
        ValoGateway().execute(
            authority=authority,
            clearance=clearance,
            permit=tampered,
            action=action,
            executor_id="tool:test",
            tool=FunctionTool("x", lambda: calls.append(1)),
            now=now,
        )
    assert calls == []
    assert tampered.consumed_at is None


def test_expired_workspace_fails_before_invoke_or_consumption():
    now, authority, action, clearance, permit = _governed_chain()
    expired_at = now + timedelta(minutes=3)
    expired_action = action.model_copy(
        update={
            "workspace_binding": action.workspace_binding.model_copy(
                update={"workspace_expires_at": now + timedelta(seconds=30)}
            )
        }
    )
    expired_clearance = clearance.model_copy(update={"action_digest": expired_action.digest})
    expired_permit = permit.model_copy(
        update={
            "action_digest": expired_action.digest,
            "clearance_digest": canonical_digest(
                expired_clearance.model_dump(mode="json")
            ),
            "expires_at": now + timedelta(minutes=4),
        }
    )
    calls: list[int] = []

    with pytest.raises(ValueError, match="workspace is expired"):
        ValoGateway().execute(
            authority=authority,
            clearance=expired_clearance,
            permit=expired_permit,
            action=expired_action,
            executor_id="tool:test",
            tool=FunctionTool("x", lambda: calls.append(1)),
            now=expired_at,
        )
    assert calls == []
    assert expired_permit.consumed_at is None


def test_veritas_handoff_rejects_workspace_binding_drift():
    now, authority, action, clearance, permit = _governed_chain()
    result = ValoGateway().execute(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        executor_id="tool:test",
        tool=FunctionTool("x", lambda: {"ok": True}),
        now=now,
    )
    tampered = result.model_copy(
        update={
            "receipt": result.receipt.model_copy(
                update={"workspace_binding_digest": "sha256:" + "0" * 64}
            )
        }
    )

    with pytest.raises(ValueError, match="receipt workspace binding mismatch"):
        build_veritas_execution_observation(
            authority=authority,
            clearance=clearance,
            action=action,
            result=tampered,
        )
