from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from valo_gateway import (
    ActionEnvelope,
    AuthorityEnvelope,
    AuthoritySource,
    Clearance,
    ConfidentialExecutionBinding,
    Decision,
    DecisionContract,
    GovernedWorkspaceLineage,
    ValoGateway,
    canonical_digest,
    issue_execution_permit,
)
from valo_gateway.tool_adapters import FunctionTool
from valo_gateway.veritas_handoff import build_veritas_execution_observation

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64
DIGEST_E = "sha256:" + "e" * 64


def _substrate(now: datetime, *, max_age: int = 120) -> ConfidentialExecutionBinding:
    return ConfidentialExecutionBinding(
        attested_workspace_digest=DIGEST_A,
        substrate_attestation_digest=DIGEST_B,
        attestation_evidence_digest=DIGEST_C,
        substrate_id="gpu-node-1",
        tee_type="NVIDIA_CC",
        gpu_identity="gpu:0000:01:00.0",
        cc_mode="CONFIDENTIAL_COMPUTE",
        measurement="sha384:trusted-measurement",
        attestation_verifier="verifier:enterprise-tee",
        attested_at=now - timedelta(seconds=1),
        valid_until=now + timedelta(minutes=5),
        max_attestation_age_seconds=max_age,
        model_digest=DIGEST_D,
        workload_digest=DIGEST_E,
    )


def _lineage(now: datetime, substrate: ConfidentialExecutionBinding):
    return GovernedWorkspaceLineage(
        tenant_id="tenant-tee",
        work_unit_id="work-tee",
        workspace_id="workspace-tee",
        workspace_digest=DIGEST_A,
        workspace_expires_at=now + timedelta(minutes=3),
        program_ref="program://confidential/run",
        program_digest=DIGEST_E,
        invocation_id="invocation-tee",
        candidate_id="candidate-tee",
        candidate_digest=DIGEST_A,
        proposed_action_digest=DIGEST_B,
        conformance_report_id="conformance-tee",
        conformance_digest=DIGEST_C,
        source_state_digest=DIGEST_A,
        conformed_state_digest=DIGEST_B,
        source_event_position=7,
        conformed_at=now,
        dependency_digest=DIGEST_C,
        workspace_binding_digest=DIGEST_D,
        kernel_context_digest=DIGEST_E,
        execution_substrate_binding=substrate,
    )


def _chain(now: datetime | None = None, *, max_age: int = 120):
    now = now or datetime.now(UTC)
    substrate = _substrate(now, max_age=max_age)
    lineage = _lineage(now, substrate)
    authority = AuthorityEnvelope(
        principal_id="human:owner",
        actor_id="agent:worker",
        source=AuthoritySource.INTERNAL,
        issuer="valo",
        capability_grants=["compute.run"],
        resource_scope=["job:tee"],
        issued_at=now - timedelta(seconds=2),
        valid_until=now + timedelta(minutes=10),
    )
    action = ActionEnvelope(
        action_type="compute.run",
        target="job:tee",
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
        decided_at=now,
        valid_until=now + timedelta(minutes=5),
        reht_ref="reht:tee-clearance",
        workspace_binding_digest=lineage.workspace_binding_digest,
        kernel_context_digest=lineage.kernel_context_digest,
        execution_substrate_digest=substrate.binding_digest,
    )
    permit = issue_execution_permit(
        clearance=clearance,
        authority=authority,
        action=action,
        expires_at=now + timedelta(seconds=30),
        now=now,
    )
    return now, substrate, authority, action, clearance, permit


def test_tee_binding_propagates_action_clearance_permit_receipt_and_veritas():
    now, substrate, authority, action, clearance, permit = _chain()
    result = ValoGateway().execute(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        executor_id="tool:confidential-compute",
        tool=FunctionTool("compute", lambda: {"ok": True}),
        now=now,
    )

    assert action.execution_substrate_digest == substrate.binding_digest
    assert clearance.execution_substrate_digest == substrate.binding_digest
    assert permit.execution_substrate_digest == substrate.binding_digest
    assert result.receipt.execution_substrate_digest == substrate.binding_digest

    observation = build_veritas_execution_observation(
        authority=authority,
        clearance=clearance,
        action=action,
        result=result,
    )
    assert observation["execution_substrate_digest"] == substrate.binding_digest
    assert observation["execution_substrate_binding"]["tee_type"] == "NVIDIA_CC"
    assert observation["execution_substrate_binding"]["gpu_identity"] == (
        "gpu:0000:01:00.0"
    )
    assert observation["execution_substrate_binding"]["authority_effect"] == (
        "NO_AUTHORITY_CREATION"
    )
    assert observation["authority_granted"] is False


def test_clearance_missing_tee_binding_cannot_issue_permit():
    now, _, authority, action, clearance, _ = _chain()
    missing = clearance.model_copy(update={"execution_substrate_digest": None})
    with pytest.raises(
        ValueError, match="clearance execution substrate binding mismatch"
    ):
        issue_execution_permit(
            clearance=missing,
            authority=authority,
            action=action,
            expires_at=now + timedelta(seconds=30),
            now=now,
        )


def test_permit_tee_binding_drift_blocks_before_tool_and_consumption():
    now, _, authority, action, clearance, permit = _chain()
    tampered = permit.model_copy(update={"execution_substrate_digest": DIGEST_A})
    calls: list[int] = []

    with pytest.raises(ValueError, match="permit execution substrate binding mismatch"):
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


def test_revoked_or_unverified_tee_blocks_before_tool_and_consumption():
    now, substrate, authority, action, clearance, permit = _chain()
    revoked = substrate.model_copy(update={"verification_status": "REVOKED"})
    tampered_lineage = action.workspace_binding.model_copy(
        update={"execution_substrate_binding": revoked}
    )
    tampered_action = action.model_copy(update={"workspace_binding": tampered_lineage})
    tampered_clearance = clearance.model_copy(
        update={
            "action_digest": tampered_action.digest,
            "execution_substrate_digest": revoked.binding_digest,
        }
    )
    tampered_permit = permit.model_copy(
        update={
            "action_digest": tampered_action.digest,
            "execution_substrate_digest": revoked.binding_digest,
            "clearance_digest": canonical_digest(
                tampered_clearance.model_dump(mode="json")
            ),
        }
    )
    calls: list[int] = []

    with pytest.raises(ValueError, match="stale, expired, or unverified"):
        ValoGateway().execute(
            authority=authority,
            clearance=tampered_clearance,
            permit=tampered_permit,
            action=tampered_action,
            executor_id="tool:test",
            tool=FunctionTool("x", lambda: calls.append(1)),
            now=now,
        )
    assert calls == []
    assert tampered_permit.consumed_at is None


def test_stale_tee_blocks_before_tool_even_if_permit_was_extended():
    now, _, authority, action, clearance, permit = _chain(max_age=10)
    execution_time = now + timedelta(seconds=11)
    illegally_extended = permit.model_copy(
        update={"expires_at": now + timedelta(seconds=30)}
    )
    calls: list[int] = []

    with pytest.raises(ValueError, match="stale, expired, or unverified"):
        ValoGateway().execute(
            authority=authority,
            clearance=clearance,
            permit=illegally_extended,
            action=action,
            executor_id="tool:test",
            tool=FunctionTool("x", lambda: calls.append(1)),
            now=execution_time,
        )
    assert calls == []
    assert illegally_extended.consumed_at is None


def test_permit_cannot_outlive_tee_freshness_window():
    now = datetime.now(UTC)
    substrate = _substrate(now, max_age=10)
    lineage = _lineage(now, substrate)
    authority = AuthorityEnvelope(
        principal_id="human:owner",
        actor_id="agent:worker",
        source=AuthoritySource.INTERNAL,
        issuer="valo",
        issued_at=now - timedelta(seconds=1),
        valid_until=now + timedelta(minutes=5),
    )
    action = ActionEnvelope(
        action_type="compute.run",
        target="job:tee",
        context_digest="ctx",
        policy_digest="policy",
        authority_envelope_id=authority.envelope_id,
        workspace_binding=lineage,
    )
    clearance = Clearance(
        action_digest=action.digest,
        authority_envelope_id=authority.envelope_id,
        decision_contract=DecisionContract(
            decision=Decision.ALLOW,
            principal_id=authority.principal_id,
            actor_id=authority.actor_id,
            action_type=action.action_type,
            target=action.target,
        ),
        valid_until=now + timedelta(minutes=2),
        reht_ref="reht:tee-clearance",
        workspace_binding_digest=lineage.workspace_binding_digest,
        kernel_context_digest=lineage.kernel_context_digest,
        execution_substrate_digest=substrate.binding_digest,
    )

    with pytest.raises(
        ValueError, match="permit cannot outlive confidential execution freshness"
    ):
        issue_execution_permit(
            clearance=clearance,
            authority=authority,
            action=action,
            expires_at=now + timedelta(seconds=11),
            now=now,
        )
