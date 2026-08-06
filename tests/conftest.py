"""Shared fixtures for valo-gateway tests."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from valo_gateway import (
    ActionEnvelope,
    AuthorityEnvelope,
    AuthoritySource,
    Clearance,
    Decision,
    DecisionContract,
    issue_execution_permit,
)


def make_chain(*, decision: Decision = Decision.ALLOW, now: datetime | None = None):
    """Build an authority/action/clearance chain with valid bindings.

    For ALLOW/MODIFY an execution permit is issued; for DENY/DEFER/HALT the
    permit is None (those decisions must not issue a permit).
    """
    now = now or datetime.now(UTC)
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
        decision=decision, principal_id=authority.principal_id,
        actor_id=authority.actor_id, action_type=action.action_type,
        target=action.target,
    )
    clearance = Clearance(
        action_digest=action.digest, authority_envelope_id=authority.envelope_id,
        decision_contract=contract, valid_until=now + timedelta(minutes=5),
        reht_ref="reht:1",
    )
    if decision not in {Decision.ALLOW, Decision.MODIFY}:
        return now, authority, action, clearance, None
    permit = issue_execution_permit(
        clearance=clearance, authority=authority, action=action,
        expires_at=now + timedelta(minutes=1), now=now,
    )
    return now, authority, action, clearance, permit
