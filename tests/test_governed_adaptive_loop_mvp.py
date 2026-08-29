from datetime import UTC, datetime

import pytest

from examples.governed_adaptive_loop.app import (
    DemoAuthorizer,
    InMemoryPermitStore,
    OutcomeRenewal,
    ResolutionLedger,
    _registry_for,
    build_authority,
    build_guidance,
    run_allowed_flow,
    run_demo,
    run_revoked_flow,
)
from valo_gateway import ValoGateway
from valo_gateway.tool_adapters import FunctionTool
from valo_gateway.veritas_handoff import build_veritas_execution_observation


NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def test_mvp_allowed_flow_executes_and_renews_from_effect_evidence():
    result = run_allowed_flow(now=NOW)

    assert result["guidance_authority_effect"] == "NONE"
    assert result["decision"] == "ALLOW"
    assert result["effect_status"] == "succeeded"
    assert result["effect_count"] == 1
    assert result["guidance_revision_before"] == 1
    assert result["guidance_revision_after"] == 2
    assert result["renewed_from_effect_evidence"] is True
    assert result["observation_digest"].startswith("sha256:")


def test_mvp_revocation_after_permit_issuance_has_null_effect():
    result = run_revoked_flow(now=NOW)

    assert result["decision_when_permit_issued"] == "ALLOW"
    assert result["authority_revoked_before_effect"] is True
    assert result["blocked"] is True
    assert result["effect_count"] == 0
    assert "inactive or revoked at execution time" in result["blocked_reason"]


def test_guidance_cannot_override_current_authority_limit():
    authority = build_authority(now=NOW, max_amount=50)
    guidance = build_guidance(amount=80)
    action = guidance.propose(authority_envelope_id=authority.envelope_id)
    authorizer = DemoAuthorizer()

    clearance = authorizer.clear(action=action, authority=authority, now=NOW)
    permit = authorizer.permit(
        action=action,
        authority=authority,
        clearance=clearance,
        now=NOW,
    )

    assert clearance.decision_contract.decision.value == "DENY"
    assert permit is None
    assert guidance.authority_effect == "NONE"


def test_direct_effector_path_remains_blocked():
    tool = FunctionTool(
        "case_resolution",
        lambda outcome, amount: {"outcome": outcome, "amount": amount},
    )

    with pytest.raises(PermissionError, match="NO_DIRECT_EFFECT_PATH"):
        tool.invoke({"outcome": "refund", "amount": 80})


def test_receipt_observation_is_idempotent_for_guidance_renewal():
    authority = build_authority(now=NOW)
    guidance = build_guidance()
    action = guidance.propose(authority_envelope_id=authority.envelope_id)
    authorizer = DemoAuthorizer()
    clearance = authorizer.clear(action=action, authority=authority, now=NOW)
    permit = authorizer.permit(
        action=action,
        authority=authority,
        clearance=clearance,
        now=NOW,
    )
    assert permit is not None

    ledger = ResolutionLedger()
    registry, handle = _registry_for(ledger, target=action.target)
    result = ValoGateway(permit_store=InMemoryPermitStore()).execute(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        executor_id="tool:case-resolution",
        effector_registry=registry,
        effector_handle=handle,
        arguments=action.parameters,
        now=NOW,
    )
    observation = build_veritas_execution_observation(
        authority=authority,
        clearance=clearance,
        action=action,
        result=result,
    )

    renewal = OutcomeRenewal()
    once = renewal.renew(guidance=guidance, observation=observation)
    twice = renewal.renew(guidance=once, observation=observation)

    assert once.revision == 2
    assert twice.revision == 2
    assert once.renewed_from_receipts == twice.renewed_from_receipts


def test_demo_contains_both_consequence_outcomes():
    result = run_demo(now=NOW)

    assert result["allowed_flow"]["effect_count"] == 1
    assert result["revoked_flow"]["effect_count"] == 0
    assert result["revoked_flow"]["blocked"] is True
