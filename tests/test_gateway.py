from datetime import datetime, timedelta, timezone
import pytest
from valo_gateway import (
    ActionEnvelope, AuthorityEnvelope, AuthoritySource, Clearance, Decision,
    DecisionContract, ValoGateway, issue_execution_permit,
)
from valo_gateway.gateway import ControlEvent, ControlEventType, RuntimeControlPlane
from valo_gateway.tool_adapters import FunctionTool


def fixture():
    now = datetime.now(timezone.utc)
    authority = AuthorityEnvelope(
        principal_id="human:owner", actor_id="agent:worker",
        source=AuthoritySource.INTERNAL, issuer="valo", issued_at=now,
        capability_grants=["payment.submit"], resource_scope=["invoice:123"],
        valid_until=now + timedelta(minutes=10),
    )
    action = ActionEnvelope(
        action_type="payment.submit", target="invoice:123",
        parameters={"amount": 1250}, context_digest="ctx",
        policy_digest="policy", authority_envelope_id=authority.envelope_id,
    )
    contract = DecisionContract(
        decision=Decision.ALLOW, principal_id=authority.principal_id,
        actor_id=authority.actor_id, action_type=action.action_type,
        target=action.target,
    )
    clearance = Clearance(
        action_digest=action.digest, authority_envelope_id=authority.envelope_id,
        decision_contract=contract, valid_until=now + timedelta(minutes=5),
        reht_ref="reht:1",
    )
    permit = issue_execution_permit(
        clearance=clearance, authority=authority, action=action,
        expires_at=now + timedelta(minutes=1), now=now,
    )
    return now, authority, action, clearance, permit


def test_success_consumes_permit_and_receipts():
    now, authority, action, clearance, permit = fixture()
    result = ValoGateway().execute(
        authority=authority, clearance=clearance, permit=permit,
        action=action, executor_id="tool:payments",
        tool=FunctionTool("payments", lambda amount: {"accepted": True, "amount": amount}),
        arguments={"amount": 1250}, now=now,
    )
    assert result.response["accepted"] is True
    assert result.consumed_permit.consumed_at == now
    assert result.receipt.status.value == "succeeded"


def test_replay_blocked_before_invocation():
    now, authority, action, clearance, permit = fixture()
    called = False
    def tool():
        nonlocal called
        called = True
    with pytest.raises(ValueError, match="already consumed"):
        ValoGateway().execute(
            authority=authority, clearance=clearance, permit=permit.consume(now),
            action=action, executor_id="tool", tool=FunctionTool("x", tool), now=now,
        )
    assert called is False


def test_global_halt_overrides_permit():
    now, authority, action, clearance, permit = fixture()
    control = RuntimeControlPlane()
    control.apply(ControlEvent(
        event_type=ControlEventType.HALT_GLOBAL,
        issuer_id="human:veto", reason="incident",
    ))
    with pytest.raises(ValueError, match="revocation or HALT"):
        ValoGateway(control).execute(
            authority=authority, clearance=clearance, permit=permit,
            action=action, executor_id="tool",
            tool=FunctionTool("x", lambda: None), now=now,
        )
    assert permit.consumed_at is None
