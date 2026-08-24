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
from valo_gateway.gateway.permit_consumption import SQLitePermitConsumptionStore
from valo_gateway.tool_adapters import FunctionTool


def _fixture():
    now = datetime.now(UTC)
    authority = AuthorityEnvelope(
        principal_id="human:owner",
        actor_id="agent:worker",
        source=AuthoritySource.INTERNAL,
        issuer="valo",
        issued_at=now,
        capability_grants=["payment.submit"],
        resource_scope=["invoice:123"],
        valid_until=now + timedelta(minutes=10),
    )
    action = ActionEnvelope(
        action_type="payment.submit",
        target="invoice:123",
        parameters={"amount": 1250},
        context_digest="ctx",
        policy_digest="policy",
        authority_envelope_id=authority.envelope_id,
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
        reht_ref="reht:durable-permit",
    )
    permit = issue_execution_permit(
        clearance=clearance,
        authority=authority,
        action=action,
        expires_at=now + timedelta(minutes=1),
        now=now,
    )
    return now, authority, action, clearance, permit


def _execute(gateway, chain, calls):
    now, authority, action, clearance, permit = chain
    return gateway.execute(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        executor_id="tool:payments",
        tool=FunctionTool(
            "payments",
            lambda amount: calls.append(amount) or {"accepted": True},
        ),
        arguments={"amount": 1250},
        now=now,
    )


def test_consumption_survives_gateway_restart(tmp_path):
    chain = _fixture()
    db = tmp_path / "permits.sqlite3"
    calls = []

    first = ValoGateway(permit_store=SQLitePermitConsumptionStore(db))
    _execute(first, chain, calls)

    restarted = ValoGateway(permit_store=SQLitePermitConsumptionStore(db))
    with pytest.raises(ValueError, match="already consumed"):
        _execute(restarted, chain, calls)

    assert calls == [1250]


def test_two_gateway_instances_share_atomic_consumption(tmp_path):
    chain = _fixture()
    db = tmp_path / "permits.sqlite3"
    calls = []

    gateway_a = ValoGateway(permit_store=SQLitePermitConsumptionStore(db))
    gateway_b = ValoGateway(permit_store=SQLitePermitConsumptionStore(db))

    _execute(gateway_a, chain, calls)
    with pytest.raises(ValueError, match="already consumed"):
        _execute(gateway_b, chain, calls)

    assert calls == [1250]


def test_store_consumes_exactly_once_across_reopened_connections(tmp_path):
    db = tmp_path / "permits.sqlite3"
    now = datetime.now(UTC)

    assert SQLitePermitConsumptionStore(db).consume_once("permit:1", now) is True
    assert SQLitePermitConsumptionStore(db).consume_once("permit:1", now) is False
