"""Gateway core edge cases: binding mismatches, failed calls, MODIFY, receipts."""
from __future__ import annotations

from datetime import timedelta

import pytest

from tests.conftest import make_chain
from valo_gateway import (
    ActionEnvelope,
    Decision,
    ExecutionStatus,
    ValoGateway,
)
from valo_gateway.tool_adapters import FunctionTool


def failing_tool():
    return FunctionTool("boom", lambda: (_ for _ in ()).throw(RuntimeError("kaboom")))


def test_failed_external_call_consumes_permit_and_failure_receipt():
    now, authority, action, clearance, permit = make_chain()
    result = ValoGateway().execute(
        authority=authority, clearance=clearance, permit=permit, action=action,
        executor_id="tool:boom", tool=failing_tool(), now=now,
    )
    assert result.consumed_permit.consumed_at == now
    assert result.receipt.status == ExecutionStatus.FAILED
    assert result.error is not None
    assert "kaboom" in result.error


def test_failed_call_produces_response_digest():
    now, authority, action, clearance, permit = make_chain()
    result = ValoGateway().execute(
        authority=authority, clearance=clearance, permit=permit, action=action,
        executor_id="tool:boom", tool=failing_tool(), now=now,
    )
    assert result.receipt.response_digest is not None
    assert isinstance(result.receipt.response_digest, str)


def test_action_authority_binding_mismatch_rejected():
    now, authority, action, clearance, permit = make_chain()
    wrong = ActionEnvelope(
        action_type=action.action_type, target=action.target,
        parameters=action.parameters, context_digest=action.context_digest,
        policy_digest=action.policy_digest, authority_envelope_id="other-env",
    )
    with pytest.raises(ValueError, match="action authority binding mismatch"):
        ValoGateway().execute(
            authority=authority, clearance=clearance, permit=permit,
            action=wrong, executor_id="t", tool=FunctionTool("x", lambda: None), now=now,
        )


def test_clearance_action_binding_mismatch_rejected():
    now, authority, action, clearance, permit = make_chain()
    tampered = clearance.model_copy(update={"action_digest": "different"})
    with pytest.raises(ValueError, match="clearance action binding mismatch"):
        ValoGateway().execute(
            authority=authority, clearance=tampered, permit=permit, action=action,
            executor_id="t", tool=FunctionTool("x", lambda: None), now=now,
        )


def test_clearance_authority_binding_mismatch_rejected():
    now, authority, action, clearance, permit = make_chain()
    tampered = clearance.model_copy(update={"authority_envelope_id": "other"})
    with pytest.raises(ValueError, match="clearance authority binding mismatch"):
        ValoGateway().execute(
            authority=authority, clearance=tampered, permit=permit, action=action,
            executor_id="t", tool=FunctionTool("x", lambda: None), now=now,
        )


def test_permit_clearance_binding_mismatch_rejected():
    now, authority, action, clearance, permit = make_chain()
    tampered = permit.model_copy(update={"clearance_id": "other"})
    with pytest.raises(ValueError, match="permit clearance binding mismatch"):
        ValoGateway().execute(
            authority=authority, clearance=clearance, permit=tampered, action=action,
            executor_id="t", tool=FunctionTool("x", lambda: None), now=now,
        )


def test_inactive_authority_rejected():
    now, authority, action, clearance, permit = make_chain()
    expired = authority.model_copy(update={"valid_until": now - timedelta(seconds=1)})
    with pytest.raises(ValueError, match="inactive or revoked"):
        ValoGateway().execute(
            authority=expired, clearance=clearance, permit=permit, action=action,
            executor_id="t", tool=FunctionTool("x", lambda: None), now=now,
        )


def test_expired_clearance_rejected():
    now, authority, action, clearance, permit = make_chain()
    expired = clearance.model_copy(update={"valid_until": now - timedelta(seconds=1)})
    with pytest.raises(ValueError, match="no longer valid"):
        ValoGateway().execute(
            authority=authority, clearance=expired, permit=permit, action=action,
            executor_id="t", tool=FunctionTool("x", lambda: None), now=now,
        )


def test_scope_halt_blocks_without_consuming_permit():
    now, authority, action, clearance, permit = make_chain()
    from valo_gateway.gateway import ControlEvent, ControlEventType, RuntimeControlPlane
    control = RuntimeControlPlane()
    control.apply(ControlEvent(
        event_type=ControlEventType.HALT_SCOPE, issuer_id="human:veto",
        reason="test", scope="invoice:123",
    ))
    with pytest.raises(ValueError, match="revocation or HALT"):
        ValoGateway(control).execute(
            authority=authority, clearance=clearance, permit=permit, action=action,
            executor_id="t", tool=FunctionTool("x", lambda: None), now=now,
        )
    assert permit.consumed_at is None


def test_modify_decision_authorizes_permit():
    now, authority, action, clearance, permit = make_chain(decision=Decision.MODIFY)
    result = ValoGateway().execute(
        authority=authority, clearance=clearance, permit=permit, action=action,
        executor_id="t", tool=FunctionTool("x", lambda: "ok"), now=now,
    )
    assert result.receipt.status == ExecutionStatus.SUCCEEDED


def test_receipt_hash_is_deterministic():
    now, authority, action, clearance, permit = make_chain()
    g = ValoGateway()
    r1 = g.execute(authority=authority, clearance=clearance, permit=permit, action=action,
                   executor_id="t", tool=FunctionTool("x", lambda: "v"), now=now)
    # replay with fresh permit on the same authority/action -> identical digests
    permit2 = _reissue(now, authority, action, clearance)
    r2 = g.execute(authority=authority, clearance=clearance, permit=permit2, action=action,
                   executor_id="t", tool=FunctionTool("x", lambda: "v"), now=now)
    assert r1.receipt.response_digest == r2.receipt.response_digest
    assert r1.receipt.action_digest == r2.receipt.action_digest
    assert r1.receipt.receipt_hash != r2.receipt.receipt_hash  # permit_id differ


def _reissue(now, authority, action, clearance):
    from valo_gateway import issue_execution_permit
    return issue_execution_permit(
        clearance=clearance, authority=authority, action=action,
        expires_at=now + timedelta(minutes=1), now=now,
    )
