from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from tests.conftest import make_chain
from valo_gateway import (
    RESOURCE_BUDGET_IDS_PARAMETER,
    Clearance,
    Decision,
    DecisionContract,
    ResourceBudget,
    ResourceBudgetLedger,
    ValoGateway,
    issue_execution_permit,
)
from valo_gateway.tool_adapters import FunctionTool


def _resource_chain(*budget_ids: str):
    now, authority, base_action, _, _ = make_chain()
    parameters = dict(base_action.parameters)
    parameters[RESOURCE_BUDGET_IDS_PARAMETER] = list(budget_ids)
    action = base_action.model_copy(update={"parameters": parameters})
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
        reht_ref="reht:resource-stage2",
    )
    permit = issue_execution_permit(
        clearance=clearance,
        authority=authority,
        action=action,
        expires_at=now + timedelta(minutes=1),
        now=now,
    )
    return now, authority, action, clearance, permit


def _ledger(*budget_ids: str) -> ResourceBudgetLedger:
    budgets = tuple(
        ResourceBudget(
            budget_id=budget_id,
            dimension=budget_id,
            hard_limit=Decimal("10000"),
        )
        for budget_id in budget_ids
    )
    return ResourceBudgetLedger(budgets)


def _reserve(
    ledger: ResourceBudgetLedger,
    *,
    budget_id: str,
    amount: str,
    action,
    clearance,
    permit,
):
    return ledger.reserve(
        budget_id=budget_id,
        window_id="session:stage2",
        amount=Decimal(amount),
        action_digest=action.digest,
        clearance_id=clearance.clearance_id,
        permit_id=permit.permit_id,
    )


def test_exact_resource_reservation_is_consumed_before_single_effect() -> None:
    now, authority, action, clearance, permit = _resource_chain("tool_calls")
    ledger = _ledger("tool_calls")
    reservation = _reserve(
        ledger,
        budget_id="tool_calls",
        amount="1",
        action=action,
        clearance=clearance,
        permit=permit,
    )
    calls: list[int] = []
    result = ValoGateway().execute(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        executor_id="executor:stage2",
        tool=FunctionTool("payment", lambda: calls.append(1) or "ok"),
        now=now,
        resource_ledger=ledger,
        resource_reservations=(reservation,),
    )
    assert calls == [1]
    assert result.consumed_permit.consumed_at is not None
    assert len(result.consumed_resources) == 1
    assert result.consumed_resources[0].reservation.reservation_id == reservation.reservation_id
    assert not ledger.is_pending(reservation.reservation_id)


def test_required_resource_without_ledger_blocks_before_permit_and_tool() -> None:
    now, authority, action, clearance, permit = _resource_chain("tool_calls")
    calls: list[int] = []
    with pytest.raises(ValueError, match="resource ledger is required"):
        ValoGateway().execute(
            authority=authority,
            clearance=clearance,
            permit=permit,
            action=action,
            executor_id="executor:stage2",
            tool=FunctionTool("payment", lambda: calls.append(1)),
            now=now,
        )
    assert calls == []
    assert permit.consumed_at is None


def test_missing_one_of_multiple_resource_reservations_blocks_atomically() -> None:
    now, authority, action, clearance, permit = _resource_chain(
        "tool_calls", "transaction_value_minor"
    )
    ledger = _ledger("tool_calls", "transaction_value_minor")
    tool_calls = _reserve(
        ledger,
        budget_id="tool_calls",
        amount="1",
        action=action,
        clearance=clearance,
        permit=permit,
    )
    calls: list[int] = []
    with pytest.raises(ValueError, match="does not match permit requirements"):
        ValoGateway().execute(
            authority=authority,
            clearance=clearance,
            permit=permit,
            action=action,
            executor_id="executor:stage2",
            tool=FunctionTool("payment", lambda: calls.append(1)),
            now=now,
            resource_ledger=ledger,
            resource_reservations=(tool_calls,),
        )
    assert calls == []
    assert permit.consumed_at is None
    assert ledger.is_pending(tool_calls.reservation_id)


def test_reservation_bound_to_other_permit_cannot_authorize_effect() -> None:
    now, authority, action, clearance, permit = _resource_chain("tool_calls")
    ledger = _ledger("tool_calls")
    reservation = ledger.reserve(
        budget_id="tool_calls",
        window_id="session:stage2",
        amount=Decimal("1"),
        action_digest=action.digest,
        clearance_id=clearance.clearance_id,
        permit_id="permit:other",
    )
    calls: list[int] = []
    with pytest.raises(ValueError, match="permit binding mismatch"):
        ValoGateway().execute(
            authority=authority,
            clearance=clearance,
            permit=permit,
            action=action,
            executor_id="executor:stage2",
            tool=FunctionTool("payment", lambda: calls.append(1)),
            now=now,
            resource_ledger=ledger,
            resource_reservations=(reservation,),
        )
    assert calls == []
    assert permit.consumed_at is None
    assert ledger.is_pending(reservation.reservation_id)


def test_resource_requirement_cannot_be_removed_after_permit_issuance() -> None:
    now, authority, action, clearance, permit = _resource_chain("tool_calls")
    mutated_parameters = dict(action.parameters)
    mutated_parameters.pop(RESOURCE_BUDGET_IDS_PARAMETER)
    mutated_action = action.model_copy(update={"parameters": mutated_parameters})
    calls: list[int] = []
    with pytest.raises(ValueError, match="action binding mismatch"):
        ValoGateway().execute(
            authority=authority,
            clearance=clearance,
            permit=permit,
            action=mutated_action,
            executor_id="executor:stage2",
            tool=FunctionTool("payment", lambda: calls.append(1)),
            now=now,
        )
    assert calls == []
    assert permit.consumed_at is None


def test_failed_external_call_still_consumes_resource_and_permit() -> None:
    now, authority, action, clearance, permit = _resource_chain("tool_calls")
    ledger = _ledger("tool_calls")
    reservation = _reserve(
        ledger,
        budget_id="tool_calls",
        amount="1",
        action=action,
        clearance=clearance,
        permit=permit,
    )

    def fail() -> None:
        raise RuntimeError("provider failed")

    result = ValoGateway().execute(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        executor_id="executor:stage2",
        tool=FunctionTool("payment", fail),
        now=now,
        resource_ledger=ledger,
        resource_reservations=(reservation,),
    )
    assert result.error == "RuntimeError: provider failed"
    assert result.consumed_permit.consumed_at is not None
    assert len(result.consumed_resources) == 1
    assert not ledger.is_pending(reservation.reservation_id)


def test_unrequired_reservation_cannot_be_smuggled_into_action() -> None:
    now, authority, action, clearance, permit = _resource_chain()
    ledger = _ledger("tool_calls")
    reservation = _reserve(
        ledger,
        budget_id="tool_calls",
        amount="1",
        action=action,
        clearance=clearance,
        permit=permit,
    )
    calls: list[int] = []
    with pytest.raises(ValueError, match="does not authorize resource reservations"):
        ValoGateway().execute(
            authority=authority,
            clearance=clearance,
            permit=permit,
            action=action,
            executor_id="executor:stage2",
            tool=FunctionTool("payment", lambda: calls.append(1)),
            now=now,
            resource_ledger=ledger,
            resource_reservations=(reservation,),
        )
    assert calls == []
    assert permit.consumed_at is None
