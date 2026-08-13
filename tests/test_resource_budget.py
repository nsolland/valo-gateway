from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from valo_gateway import (
    ResourceBudget,
    ResourceBudgetLedger,
    ResourceBudgetMode,
)


def _reserve(
    ledger: ResourceBudgetLedger,
    *,
    budget_id: str,
    amount: str,
    window: str = "window:1",
    action: str = "action:1",
    clearance: str = "clearance:1",
    permit: str = "permit:1",
):
    return ledger.reserve(
        budget_id=budget_id,
        window_id=window,
        amount=Decimal(amount),
        action_digest=action,
        clearance_id=clearance,
        permit_id=permit,
        now=datetime.now(UTC),
    )


def test_cumulative_budget_reserves_pending_capacity_fail_closed() -> None:
    ledger = ResourceBudgetLedger(
        (
            ResourceBudget(
                budget_id="tool-calls",
                dimension="tool_calls",
                hard_limit=Decimal("3"),
            ),
        )
    )
    first = _reserve(ledger, budget_id="tool-calls", amount="2")
    assert ledger.remaining(budget_id="tool-calls", window_id="window:1") == Decimal("1")
    with pytest.raises(ValueError, match="hard limit exceeded"):
        _reserve(ledger, budget_id="tool-calls", amount="2")
    assert ledger.is_pending(first.reservation_id)


def test_consumption_commits_capacity_and_cannot_be_replayed() -> None:
    ledger = ResourceBudgetLedger(
        (
            ResourceBudget(
                budget_id="cost",
                dimension="cost_minor",
                hard_limit=Decimal("1000"),
            ),
        )
    )
    reservation = _reserve(ledger, budget_id="cost", amount="400")
    consumed = ledger.consume_many(
        reservations=(reservation,),
        expected_budget_ids=("cost",),
        action_digest="action:1",
        clearance_id="clearance:1",
        permit_id="permit:1",
    )
    assert len(consumed) == 1
    assert consumed[0].digest
    assert not ledger.is_pending(reservation.reservation_id)
    assert ledger.remaining(budget_id="cost", window_id="window:1") == Decimal("600")
    with pytest.raises(ValueError, match="missing, unknown, or already consumed"):
        ledger.consume_many(
            reservations=(reservation,),
            expected_budget_ids=("cost",),
            action_digest="action:1",
            clearance_id="clearance:1",
            permit_id="permit:1",
        )


def test_max_per_action_enforces_recursion_depth_without_accumulating() -> None:
    ledger = ResourceBudgetLedger(
        (
            ResourceBudget(
                budget_id="depth",
                dimension="recursion_depth",
                hard_limit=Decimal("3"),
                mode=ResourceBudgetMode.MAX_PER_ACTION,
            ),
        )
    )
    first = _reserve(ledger, budget_id="depth", amount="3", permit="permit:1")
    ledger.consume_many(
        reservations=(first,),
        expected_budget_ids=("depth",),
        action_digest="action:1",
        clearance_id="clearance:1",
        permit_id="permit:1",
    )
    second = _reserve(ledger, budget_id="depth", amount="2", permit="permit:2")
    assert second.amount == Decimal("2")
    with pytest.raises(ValueError, match="hard limit exceeded"):
        _reserve(ledger, budget_id="depth", amount="4", permit="permit:3")


def test_multi_budget_consumption_is_atomic_on_binding_failure() -> None:
    ledger = ResourceBudgetLedger(
        (
            ResourceBudget(
                budget_id="tool",
                dimension="tool_calls",
                hard_limit=Decimal("10"),
            ),
            ResourceBudget(
                budget_id="value",
                dimension="transaction_value_minor",
                hard_limit=Decimal("10000"),
            ),
        )
    )
    tool = _reserve(ledger, budget_id="tool", amount="1")
    value = _reserve(ledger, budget_id="value", amount="500", permit="wrong-permit")
    with pytest.raises(ValueError, match="permit binding mismatch"):
        ledger.consume_many(
            reservations=(tool, value),
            expected_budget_ids=("tool", "value"),
            action_digest="action:1",
            clearance_id="clearance:1",
            permit_id="permit:1",
        )
    assert ledger.is_pending(tool.reservation_id)
    assert ledger.is_pending(value.reservation_id)


def test_unknown_budget_fails_closed() -> None:
    ledger = ResourceBudgetLedger()
    with pytest.raises(ValueError, match="unknown resource budget"):
        _reserve(ledger, budget_id="unknown", amount="1")
