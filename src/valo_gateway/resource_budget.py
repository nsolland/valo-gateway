from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from threading import RLock
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import ActionEnvelope, canonical_digest
from .contracts.models import utcnow

RESOURCE_BUDGET_IDS_PARAMETER = "_valo_resource_budget_ids"


def required_resource_budget_ids(action: ActionEnvelope) -> tuple[str, ...]:
    raw = action.parameters.get(RESOURCE_BUDGET_IDS_PARAMETER, ())
    if raw in (None, ()):
        return ()
    if not isinstance(raw, (list, tuple)):
        raise TypeError("resource budget ids must be an explicit list")
    values = tuple(raw)
    if not all(isinstance(value, str) and value for value in values):
        raise ValueError("resource budget ids must be non-empty strings")
    if len(values) != len(set(values)):
        raise ValueError("resource budget ids must be unique")
    return tuple(sorted(values))


class ResourceBudgetMode(str, Enum):
    CUMULATIVE = "cumulative"
    MAX_PER_ACTION = "max_per_action"


class ResourceBudget(BaseModel):
    budget_id: str = Field(min_length=1)
    dimension: str = Field(min_length=1)
    hard_limit: Decimal = Field(gt=0)
    mode: ResourceBudgetMode = ResourceBudgetMode.CUMULATIVE
    parent_budget_id: str | None = None
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_parent(self) -> ResourceBudget:
        if self.parent_budget_id == self.budget_id:
            raise ValueError("resource budget cannot be its own parent")
        return self


class ResourceReservation(BaseModel):
    reservation_id: str = Field(default_factory=lambda: str(uuid4()))
    budget_id: str = Field(min_length=1)
    window_id: str = Field(min_length=1)
    dimension: str = Field(min_length=1)
    amount: Decimal = Field(gt=0)
    action_digest: str = Field(min_length=1)
    clearance_id: str = Field(min_length=1)
    permit_id: str = Field(min_length=1)
    issued_at: datetime = Field(default_factory=utcnow)
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_time(self) -> ResourceReservation:
        if self.issued_at.utcoffset() is None:
            raise ValueError("issued_at must be timezone-aware")
        return self

    @property
    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class ConsumedResourceReservation(BaseModel):
    reservation: ResourceReservation
    consumed_at: datetime
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_time(self) -> ConsumedResourceReservation:
        if self.consumed_at.utcoffset() is None:
            raise ValueError("consumed_at must be timezone-aware")
        if self.consumed_at < self.reservation.issued_at:
            raise ValueError("resource reservation cannot be consumed before issuance")
        return self

    @property
    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class ResourceStateEvidence(BaseModel):
    budget_id: str
    window_id: str
    dimension: str
    hard_limit: Decimal
    committed: Decimal
    pending: Decimal
    remaining: Decimal
    parent_budget_ids: tuple[str, ...]
    observed_at: datetime
    grants_authority: bool = False
    model_config = ConfigDict(extra="forbid", frozen=True)

    @property
    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class ResourceBudgetLedger:
    def __init__(self, budgets: tuple[ResourceBudget, ...] = ()) -> None:
        self._lock = RLock()
        self._budgets: dict[str, ResourceBudget] = {}
        self._pending: dict[str, ResourceReservation] = {}
        self._committed: dict[tuple[str, str], Decimal] = {}
        for budget in budgets:
            self.register(budget)

    def register(self, budget: ResourceBudget) -> None:
        with self._lock:
            if budget.budget_id in self._budgets:
                raise ValueError(
                    f"resource budget already registered: {budget.budget_id}"
                )
            if budget.parent_budget_id is not None:
                parent = self._require_budget(budget.parent_budget_id)
                if budget.dimension != parent.dimension:
                    raise ValueError("child budget dimension must match parent")
                if budget.mode is not parent.mode:
                    raise ValueError("child budget mode must match parent")
                if budget.hard_limit > parent.hard_limit:
                    raise ValueError("child budget cannot widen parent hard limit")
            self._budgets[budget.budget_id] = budget
            self._budget_chain_ids(budget.budget_id)

    def reserve(
        self,
        *,
        budget_id: str,
        window_id: str,
        amount: Decimal,
        action_digest: str,
        clearance_id: str,
        permit_id: str,
        now: datetime | None = None,
    ) -> ResourceReservation:
        now = now or utcnow()
        with self._lock:
            budget = self._require_budget(budget_id)
            requested = Decimal(amount)
            if requested <= 0:
                raise ValueError("resource reservation amount must be positive")
            for chain_budget_id in self._budget_chain_ids(budget_id):
                chain_budget = self._budgets[chain_budget_id]
                if chain_budget.mode is ResourceBudgetMode.MAX_PER_ACTION:
                    if requested > chain_budget.hard_limit:
                        raise ValueError("resource budget hard limit exceeded")
                    continue
                committed = self._committed.get(
                    (chain_budget_id, window_id), Decimal(0)
                )
                pending = self._pending_amount(chain_budget_id, window_id)
                if committed + pending + requested > chain_budget.hard_limit:
                    raise ValueError("resource budget hard limit exceeded")
            reservation = ResourceReservation(
                budget_id=budget_id,
                window_id=window_id,
                dimension=budget.dimension,
                amount=requested,
                action_digest=action_digest,
                clearance_id=clearance_id,
                permit_id=permit_id,
                issued_at=now,
            )
            self._pending[reservation.reservation_id] = reservation
            return reservation

    def consume_many(
        self,
        *,
        reservations: tuple[ResourceReservation, ...],
        expected_budget_ids: tuple[str, ...],
        action_digest: str,
        clearance_id: str,
        permit_id: str,
        now: datetime | None = None,
    ) -> tuple[ConsumedResourceReservation, ...]:
        now = now or utcnow()
        with self._lock:
            if len(expected_budget_ids) != len(set(expected_budget_ids)):
                raise ValueError("required resource budget ids must be unique")
            provided_ids = [reservation.budget_id for reservation in reservations]
            if len(provided_ids) != len(set(provided_ids)):
                raise ValueError("resource reservations must use unique budget ids")
            if set(provided_ids) != set(expected_budget_ids):
                raise ValueError(
                    "resource reservation set does not match permit requirements"
                )
            self._reject_overlapping_hierarchy(tuple(provided_ids))

            checked: list[ResourceReservation] = []
            for reservation in reservations:
                pending = self._pending.get(reservation.reservation_id)
                if pending is None:
                    raise ValueError(
                        "resource reservation is missing, unknown, or already consumed"
                    )
                if pending != reservation:
                    raise ValueError("resource reservation payload mismatch")
                budget = self._require_budget(reservation.budget_id)
                if reservation.dimension != budget.dimension:
                    raise ValueError("resource reservation dimension mismatch")
                if reservation.action_digest != action_digest:
                    raise ValueError("resource reservation action binding mismatch")
                if reservation.clearance_id != clearance_id:
                    raise ValueError("resource reservation clearance binding mismatch")
                if reservation.permit_id != permit_id:
                    raise ValueError("resource reservation permit binding mismatch")
                checked.append(reservation)

            consumed: list[ConsumedResourceReservation] = []
            for reservation in checked:
                self._pending.pop(reservation.reservation_id)
                for chain_budget_id in self._budget_chain_ids(reservation.budget_id):
                    chain_budget = self._budgets[chain_budget_id]
                    if chain_budget.mode is ResourceBudgetMode.CUMULATIVE:
                        key = (chain_budget_id, reservation.window_id)
                        self._committed[key] = (
                            self._committed.get(key, Decimal(0))
                            + reservation.amount
                        )
                consumed.append(
                    ConsumedResourceReservation(
                        reservation=reservation,
                        consumed_at=now,
                    )
                )
            return tuple(consumed)

    def remaining(self, *, budget_id: str, window_id: str) -> Decimal:
        with self._lock:
            budget = self._require_budget(budget_id)
            if budget.mode is ResourceBudgetMode.MAX_PER_ACTION:
                return budget.hard_limit
            committed = self._committed.get((budget_id, window_id), Decimal(0))
            pending = self._pending_amount(budget_id, window_id)
            return max(budget.hard_limit - committed - pending, Decimal(0))

    def snapshot(
        self,
        *,
        budget_id: str,
        window_id: str,
        now: datetime | None = None,
    ) -> ResourceStateEvidence:
        observed_at = now or utcnow()
        with self._lock:
            budget = self._require_budget(budget_id)
            committed = self._committed.get((budget_id, window_id), Decimal(0))
            pending = self._pending_amount(budget_id, window_id)
            if budget.mode is ResourceBudgetMode.MAX_PER_ACTION:
                committed = Decimal(0)
                pending = Decimal(0)
            remaining = max(budget.hard_limit - committed - pending, Decimal(0))
            chain = self._budget_chain_ids(budget_id)
            return ResourceStateEvidence(
                budget_id=budget_id,
                window_id=window_id,
                dimension=budget.dimension,
                hard_limit=budget.hard_limit,
                committed=committed,
                pending=pending,
                remaining=remaining,
                parent_budget_ids=chain[1:],
                observed_at=observed_at,
            )

    def is_pending(self, reservation_id: str) -> bool:
        with self._lock:
            return reservation_id in self._pending

    def _pending_amount(self, budget_id: str, window_id: str) -> Decimal:
        return sum(
            (
                reservation.amount
                for reservation in self._pending.values()
                if reservation.window_id == window_id
                and budget_id in self._budget_chain_ids(reservation.budget_id)
            ),
            Decimal(0),
        )

    def _budget_chain_ids(self, budget_id: str) -> tuple[str, ...]:
        chain: list[str] = []
        current_id: str | None = budget_id
        while current_id is not None:
            if current_id in chain:
                raise ValueError("resource budget parent cycle detected")
            chain.append(current_id)
            current = self._require_budget(current_id)
            current_id = current.parent_budget_id
        return tuple(chain)

    def _reject_overlapping_hierarchy(self, budget_ids: tuple[str, ...]) -> None:
        selected = set(budget_ids)
        for budget_id in budget_ids:
            ancestors = set(self._budget_chain_ids(budget_id)[1:])
            if selected.intersection(ancestors):
                raise ValueError(
                    "action cannot reserve both a budget and its parent envelope"
                )

    def _require_budget(self, budget_id: str) -> ResourceBudget:
        try:
            return self._budgets[budget_id]
        except KeyError as exc:
            raise ValueError(f"unknown resource budget: {budget_id}") from exc
