from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from valo_gateway import ResourceBudget, ResourceBudgetLedger, ResourceBudgetMode

NOW = datetime(2026, 8, 13, 20, 0, tzinfo=UTC)


def _reserve(
    ledger,
    budget_id,
    amount,
    *,
    action="action:1",
    clearance="clearance:1",
    permit="permit:1",
):
    return ledger.reserve(
        budget_id=budget_id,
        window_id="workflow:1",
        amount=Decimal(amount),
        action_digest=action,
        clearance_id=clearance,
        permit_id=permit,
        now=NOW,
    )


def _consume(ledger, reservation, *, action="action:1", clearance="clearance:1", permit="permit:1"):
    return ledger.consume_many(
        reservations=(reservation,),
        expected_budget_ids=(reservation.budget_id,),
        action_digest=action,
        clearance_id=clearance,
        permit_id=permit,
        now=NOW,
    )


def test_child_budget_can_narrow_but_never_widen_parent() -> None:
    ledger = ResourceBudgetLedger(
        (
            ResourceBudget(
                budget_id="parent",
                dimension="cost_minor",
                hard_limit=Decimal(1000),
            ),
        )
    )
    ledger.register(
        ResourceBudget(
            budget_id="child",
            dimension="cost_minor",
            hard_limit=Decimal(600),
            parent_budget_id="parent",
        )
    )
    with pytest.raises(ValueError, match="cannot widen parent hard limit"):
        ledger.register(
            ResourceBudget(
                budget_id="wider-child",
                dimension="cost_minor",
                hard_limit=Decimal(1001),
                parent_budget_id="parent",
            )
        )


def test_sibling_children_share_parent_capacity() -> None:
    ledger = ResourceBudgetLedger(
        (
            ResourceBudget(
                budget_id="parent",
                dimension="child_agents",
                hard_limit=Decimal(2),
            ),
            ResourceBudget(
                budget_id="child-a",
                dimension="child_agents",
                hard_limit=Decimal(2),
                parent_budget_id="parent",
            ),
            ResourceBudget(
                budget_id="child-b",
                dimension="child_agents",
                hard_limit=Decimal(2),
                parent_budget_id="parent",
            ),
        )
    )
    first = _reserve(ledger, "child-a", "1", permit="permit:a")
    second = _reserve(ledger, "child-b", "1", permit="permit:b")
    assert first.amount == second.amount == Decimal(1)
    assert ledger.remaining(budget_id="parent", window_id="workflow:1") == 0
    with pytest.raises(ValueError, match="hard limit exceeded"):
        _reserve(ledger, "child-a", "1", permit="permit:c")


def test_cumulative_transaction_limit_spans_multiple_valid_actions() -> None:
    ledger = ResourceBudgetLedger(
        (
            ResourceBudget(
                budget_id="transaction-value",
                dimension="transaction_value_minor",
                hard_limit=Decimal(1000),
            ),
        )
    )
    first = _reserve(
        ledger,
        "transaction-value",
        "600",
        action="action:1",
        clearance="clearance:1",
        permit="permit:1",
    )
    _consume(ledger, first)
    second = _reserve(
        ledger,
        "transaction-value",
        "400",
        action="action:2",
        clearance="clearance:2",
        permit="permit:2",
    )
    _consume(
        ledger,
        second,
        action="action:2",
        clearance="clearance:2",
        permit="permit:2",
    )
    assert ledger.remaining(
        budget_id="transaction-value", window_id="workflow:1"
    ) == 0
    with pytest.raises(ValueError, match="hard limit exceeded"):
        _reserve(
            ledger,
            "transaction-value",
            "1",
            action="action:3",
            clearance="clearance:3",
            permit="permit:3",
        )


def test_same_reservation_cannot_be_double_spent_concurrently() -> None:
    ledger = ResourceBudgetLedger(
        (
            ResourceBudget(
                budget_id="tool-calls",
                dimension="tool_calls",
                hard_limit=Decimal(10),
            ),
        )
    )
    reservation = _reserve(ledger, "tool-calls", "5")

    def consume_once():
        try:
            _consume(ledger, reservation)
            return "consumed"
        except ValueError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(lambda _: consume_once(), range(2)))
    assert outcomes == ["consumed", "rejected"]
    state = ledger.snapshot(
        budget_id="tool-calls", window_id="workflow:1", now=NOW
    )
    assert state.committed == Decimal(5)
    assert state.remaining == Decimal(5)


def test_recursive_depth_obeys_parent_ceiling() -> None:
    ledger = ResourceBudgetLedger(
        (
            ResourceBudget(
                budget_id="depth-parent",
                dimension="recursion_depth",
                hard_limit=Decimal(3),
                mode=ResourceBudgetMode.MAX_PER_ACTION,
            ),
            ResourceBudget(
                budget_id="depth-child",
                dimension="recursion_depth",
                hard_limit=Decimal(2),
                mode=ResourceBudgetMode.MAX_PER_ACTION,
                parent_budget_id="depth-parent",
            ),
        )
    )
    assert _reserve(ledger, "depth-child", "2").amount == Decimal(2)
    with pytest.raises(ValueError, match="hard limit exceeded"):
        _reserve(ledger, "depth-child", "3", permit="permit:2")


def test_resource_state_snapshot_is_deterministic_non_authority_evidence() -> None:
    ledger = ResourceBudgetLedger(
        (
            ResourceBudget(
                budget_id="tokens",
                dimension="tokens",
                hard_limit=Decimal(100),
            ),
        )
    )
    _reserve(ledger, "tokens", "25")
    first = ledger.snapshot(budget_id="tokens", window_id="workflow:1", now=NOW)
    second = ledger.snapshot(budget_id="tokens", window_id="workflow:1", now=NOW)
    assert first.digest == second.digest
    assert first.pending == Decimal(25)
    assert first.remaining == Decimal(75)
    assert first.grants_authority is False


def test_action_cannot_reserve_parent_and_child_as_separate_spend() -> None:
    ledger = ResourceBudgetLedger(
        (
            ResourceBudget(
                budget_id="parent",
                dimension="cost_minor",
                hard_limit=Decimal(100),
            ),
            ResourceBudget(
                budget_id="child",
                dimension="cost_minor",
                hard_limit=Decimal(100),
                parent_budget_id="parent",
            ),
        )
    )
    parent = _reserve(ledger, "parent", "10")
    child = _reserve(ledger, "child", "10", permit="permit:2")
    with pytest.raises(ValueError, match="both a budget and its parent"):
        ledger.consume_many(
            reservations=(parent, child),
            expected_budget_ids=("parent", "child"),
            action_digest="action:1",
            clearance_id="clearance:1",
            permit_id="permit:1",
            now=NOW,
        )
