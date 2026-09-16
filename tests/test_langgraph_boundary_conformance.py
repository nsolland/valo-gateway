from datetime import UTC, datetime, timedelta

import pytest

from valo_gateway import (
    ActionEnvelope,
    AuthorityEnvelope,
    AuthoritySource,
    Clearance,
    Decision,
    DecisionContract,
    ValoGateway,
    issue_execution_permit,
)
from valo_gateway.tool_adapters import FunctionTool


class InMemoryPermitStore:
    def __init__(self) -> None:
        self._consumed: set[str] = set()

    def consume_once(self, permit_id: str, consumed_at: datetime) -> bool:
        del consumed_at
        if permit_id in self._consumed:
            return False
        self._consumed.add(permit_id)
        return True


def _chain(*, amount: int = 45_000):
    now = datetime(2026, 9, 14, 4, 0, tzinfo=UTC)
    authority = AuthorityEnvelope(
        principal_id="human:owner",
        actor_id="agent:langgraph",
        source=AuthoritySource.INTERNAL,
        issuer="heimel-test",
        issued_at=now,
        valid_until=now + timedelta(minutes=5),
        capability_grants=["transfer_funds"],
        resource_scope=["acct:xyz"],
    )
    action = ActionEnvelope(
        action_type="transfer_funds",
        target="acct:xyz",
        parameters={"amount": amount, "purpose": "vendor_payment"},
        context_digest="langgraph:thread:42",
        policy_digest="policy:payments:v1",
        authority_envelope_id=authority.envelope_id,
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
        decided_at=now,
        valid_until=now + timedelta(seconds=30),
        reht_ref="reht:fresh:langgraph-test",
        policy_refs=["policy:payments:v1"],
    )
    permit = issue_execution_permit(
        clearance=clearance,
        authority=authority,
        action=action,
        expires_at=now + timedelta(seconds=10),
        now=now,
    )
    return now, authority, action, clearance, permit


def _execute(*, gateway, authority, action, clearance, permit, calls, now):
    return gateway.execute(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        executor_id="tool:bank-transfer",
        tool=FunctionTool(
            "bank-transfer",
            lambda amount, purpose: calls.append((amount, purpose))
            or {"accepted": True},
        ),
        arguments=action.parameters,
        now=now,
    )


def test_restored_langgraph_checkpoint_cannot_replay_consumed_permit():
    now, authority, action, clearance, permit = _chain()
    calls = []
    permit_store = InMemoryPermitStore()
    gateway = ValoGateway(permit_store=permit_store)

    graph_state = {
        "proposed_effect": action,
        "authority_decision": "ALLOW",
        "permit": permit,
    }

    _execute(
        gateway=gateway,
        authority=authority,
        action=graph_state["proposed_effect"],
        clearance=clearance,
        permit=graph_state["permit"],
        calls=calls,
        now=now,
    )

    restored_checkpoint = dict(graph_state)
    with pytest.raises(ValueError, match="already consumed"):
        _execute(
            gateway=gateway,
            authority=authority,
            action=restored_checkpoint["proposed_effect"],
            clearance=clearance,
            permit=restored_checkpoint["permit"],
            calls=calls,
            now=now + timedelta(seconds=1),
        )

    assert calls == [(45_000, "vendor_payment")]


def test_langgraph_cannot_mutate_effect_after_exact_binding():
    now, authority, action, clearance, permit = _chain(amount=45_000)
    calls = []
    gateway = ValoGateway(permit_store=InMemoryPermitStore())

    mutated_effect = action.model_copy(
        update={"parameters": {"amount": 50_000, "purpose": "vendor_payment"}}
    )

    with pytest.raises(ValueError, match="action binding mismatch"):
        _execute(
            gateway=gateway,
            authority=authority,
            action=mutated_effect,
            clearance=clearance,
            permit=permit,
            calls=calls,
            now=now,
        )

    assert calls == []


def test_graph_allow_state_is_not_authority_when_authority_is_revoked():
    now, authority, action, clearance, permit = _chain()
    calls = []
    gateway = ValoGateway(permit_store=InMemoryPermitStore())

    restored_graph_state = {
        "authority_decision": "ALLOW",
        "proposed_effect": action,
        "permit": permit,
    }
    revoked = authority.model_copy(
        update={
            "revoked_at": now + timedelta(seconds=1),
            "revocation_ref": "revocation:test",
        }
    )

    with pytest.raises(ValueError, match="inactive or revoked at execution time"):
        _execute(
            gateway=gateway,
            authority=revoked,
            action=restored_graph_state["proposed_effect"],
            clearance=clearance,
            permit=restored_graph_state["permit"],
            calls=calls,
            now=now + timedelta(seconds=2),
        )

    assert restored_graph_state["authority_decision"] == "ALLOW"
    assert calls == []
