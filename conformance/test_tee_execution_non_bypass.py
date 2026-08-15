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
    issue_execution_permit,
)
from valo_gateway.tool_adapters import FunctionTool

D = "sha256:" + "a" * 64


def _chain():
    now = datetime.now(UTC)
    substrate = ConfidentialExecutionBinding(
        attested_workspace_digest=D,
        substrate_attestation_digest=D,
        attestation_evidence_digest=D,
        substrate_id="node-1",
        tee_type="TEE",
        gpu_identity="gpu-1",
        cc_mode="CONFIDENTIAL",
        measurement="measurement-1",
        attestation_verifier="verifier-1",
        attested_at=now - timedelta(seconds=1),
        valid_until=now + timedelta(minutes=2),
        max_attestation_age_seconds=60,
    )
    lineage = GovernedWorkspaceLineage(
        tenant_id="tenant",
        work_unit_id="work",
        workspace_id="workspace",
        workspace_digest=D,
        workspace_expires_at=now + timedelta(minutes=2),
        program_ref="program",
        program_digest=D,
        invocation_id="invocation",
        candidate_id="candidate",
        candidate_digest=D,
        proposed_action_digest=D,
        conformance_report_id="conformance",
        conformance_digest=D,
        source_state_digest=D,
        conformed_state_digest=D,
        source_event_position=1,
        conformed_at=now,
        dependency_digest=D,
        workspace_binding_digest=D,
        kernel_context_digest=D,
        execution_substrate_binding=substrate,
    )
    authority = AuthorityEnvelope(
        principal_id="principal",
        actor_id="actor",
        source=AuthoritySource.INTERNAL,
        issuer="issuer",
        issued_at=now - timedelta(seconds=2),
        valid_until=now + timedelta(minutes=5),
    )
    action = ActionEnvelope(
        action_type="compute",
        target="job",
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
        reht_ref="reht:1",
        workspace_binding_digest=D,
        kernel_context_digest=D,
        execution_substrate_digest=substrate.binding_digest,
    )
    permit = issue_execution_permit(
        clearance=clearance,
        authority=authority,
        action=action,
        expires_at=now + timedelta(seconds=30),
        now=now,
    )
    return now, authority, action, clearance, permit


def test_confidential_effect_has_no_path_when_attestation_binding_is_invalid():
    now, authority, action, clearance, permit = _chain()
    calls: list[str] = []
    invalid = permit.model_copy(
        update={"execution_substrate_digest": "sha256:" + "0" * 64}
    )

    with pytest.raises(ValueError, match="execution substrate binding mismatch"):
        ValoGateway().execute(
            authority=authority,
            clearance=clearance,
            permit=invalid,
            action=action,
            executor_id="tool",
            tool=FunctionTool("tool", lambda: calls.append("effect")),
            now=now,
        )

    assert calls == []
    assert invalid.consumed_at is None
