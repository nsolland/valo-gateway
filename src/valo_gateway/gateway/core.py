from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from valo_gateway.contracts import (
    ActionEnvelope,
    AuthorityEnvelope,
    Clearance,
    ExecutionPermit,
    ExecutionReceipt,
    ExecutionStatus,
    canonical_digest,
)
from valo_gateway.contracts.models import utcnow
from valo_gateway.resource_budget import (
    ConsumedResourceReservation,
    ResourceBudgetLedger,
    ResourceReservation,
    required_resource_budget_ids,
)

from .control import RuntimeControlPlane


class ExecutableTool(Protocol):
    def invoke(self, arguments: dict[str, Any]) -> Any: ...


class ToolExecutionResult(BaseModel):
    consumed_permit: ExecutionPermit
    receipt: ExecutionReceipt
    consumed_resources: tuple[ConsumedResourceReservation, ...] = ()
    response: Any | None = None
    error: str | None = None
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


class ValoGateway:
    def __init__(self, control_plane: RuntimeControlPlane | None = None) -> None:
        self._control_plane = control_plane
        self._consumed_permits: set[str] = set()

    def execute(
        self,
        *,
        authority: AuthorityEnvelope,
        clearance: Clearance,
        permit: ExecutionPermit,
        action: ActionEnvelope,
        executor_id: str,
        tool: ExecutableTool,
        arguments: dict[str, Any] | None = None,
        now: datetime | None = None,
        previous_receipt_hash: str | None = None,
        control_plane: RuntimeControlPlane | None = None,
        control_scopes: list[str] | None = None,
        resource_ledger: ResourceBudgetLedger | None = None,
        resource_reservations: tuple[ResourceReservation, ...] = (),
    ) -> ToolExecutionResult:
        now = now or utcnow()
        if permit.permit_id in self._consumed_permits:
            raise ValueError("execution permit is already consumed")
        self._validate_binding(authority, clearance, permit, action, now)
        active = control_plane or self._control_plane
        if active:
            active.assert_execution_allowed(
                authority_envelope_id=authority.envelope_id,
                principal_id=authority.principal_id,
                actor_id=authority.actor_id,
                scopes=(
                    control_scopes
                    if control_scopes is not None
                    else authority.resource_scope
                ),
            )

        required_budget_ids = required_resource_budget_ids(action)
        consumed_resources: tuple[ConsumedResourceReservation, ...] = ()
        if required_budget_ids:
            if resource_ledger is None:
                raise ValueError("resource ledger is required by the exact action")
            consumed_resources = resource_ledger.consume_many(
                reservations=resource_reservations,
                expected_budget_ids=required_budget_ids,
                action_digest=action.digest,
                clearance_id=clearance.clearance_id,
                permit_id=permit.permit_id,
                now=now,
            )
        elif resource_reservations:
            raise ValueError("action does not authorize resource reservations")

        consumed = permit.consume(now)
        self._consumed_permits.add(permit.permit_id)
        try:
            response = tool.invoke(arguments or {})
            receipt = ExecutionReceipt(
                permit_id=consumed.permit_id,
                clearance_id=clearance.clearance_id,
                action_digest=action.digest,
                executor_id=executor_id,
                started_at=now,
                completed_at=utcnow(),
                status=ExecutionStatus.SUCCEEDED,
                response_digest=canonical_digest(response),
                previous_receipt_hash=previous_receipt_hash,
                skill_binding_digest=consumed.skill_binding_digest,
                workspace_binding_digest=consumed.workspace_binding_digest,
                kernel_context_digest=consumed.kernel_context_digest,
                execution_substrate_digest=consumed.execution_substrate_digest,
                clearance_digest=consumed.clearance_digest,
            )
            return ToolExecutionResult(
                consumed_permit=consumed,
                receipt=receipt,
                consumed_resources=consumed_resources,
                response=response,
            )
        except Exception as exc:
            receipt = ExecutionReceipt(
                permit_id=consumed.permit_id,
                clearance_id=clearance.clearance_id,
                action_digest=action.digest,
                executor_id=executor_id,
                started_at=now,
                completed_at=utcnow(),
                status=ExecutionStatus.FAILED,
                response_digest=canonical_digest(
                    {"error_type": type(exc).__name__, "error": str(exc)}
                ),
                previous_receipt_hash=previous_receipt_hash,
                skill_binding_digest=consumed.skill_binding_digest,
                workspace_binding_digest=consumed.workspace_binding_digest,
                kernel_context_digest=consumed.kernel_context_digest,
                execution_substrate_digest=consumed.execution_substrate_digest,
                clearance_digest=consumed.clearance_digest,
            )
            return ToolExecutionResult(
                consumed_permit=consumed,
                receipt=receipt,
                consumed_resources=consumed_resources,
                error=f"{type(exc).__name__}: {exc}",
            )

    @staticmethod
    def _validate_binding(
        authority: AuthorityEnvelope,
        clearance: Clearance,
        permit: ExecutionPermit,
        action: ActionEnvelope,
        now: datetime,
    ) -> None:
        if not authority.is_active(now):
            raise ValueError(
                "authority envelope is inactive or revoked at execution time"
            )
        if not clearance.authorizes_permit(now):
            raise ValueError("clearance is no longer valid at execution time")
        if (
            action.workspace_binding is not None
            and not action.workspace_binding.is_active(now)
        ):
            raise ValueError("governed workspace is expired at execution time")
        substrate = (
            action.workspace_binding.execution_substrate_binding
            if action.workspace_binding is not None
            else None
        )
        if substrate is not None and not substrate.is_fresh(now):
            raise ValueError(
                "confidential execution substrate is stale, expired, or unverified "
                "at execution time"
            )
        if not permit.is_usable(now):
            raise ValueError(
                "execution permit is expired, not yet active, or already consumed"
            )
        if action.authority_envelope_id != authority.envelope_id:
            raise ValueError("action authority binding mismatch")
        if clearance.authority_envelope_id != authority.envelope_id:
            raise ValueError("clearance authority binding mismatch")
        if permit.authority_envelope_id != authority.envelope_id:
            raise ValueError("permit authority binding mismatch")
        if clearance.action_digest != action.digest:
            raise ValueError("clearance action binding mismatch")
        if permit.action_digest != action.digest:
            raise ValueError("permit action binding mismatch")
        if permit.clearance_id != clearance.clearance_id:
            raise ValueError("permit clearance binding mismatch")
        if clearance.skill_binding_digest != action.skill_binding_digest:
            raise ValueError("clearance skill binding mismatch")
        if permit.skill_binding_digest != action.skill_binding_digest:
            raise ValueError("permit skill binding mismatch")
        if clearance.workspace_binding_pair != action.workspace_binding_pair:
            raise ValueError("clearance workspace binding mismatch")
        if permit.workspace_binding_pair != action.workspace_binding_pair:
            raise ValueError("permit workspace binding mismatch")
        if clearance.execution_substrate_digest != action.execution_substrate_digest:
            raise ValueError("clearance execution substrate binding mismatch")
        if permit.execution_substrate_digest != action.execution_substrate_digest:
            raise ValueError("permit execution substrate binding mismatch")
        expected_clearance_digest = None
        if action.workspace_binding is not None:
            expected_clearance_digest = canonical_digest(
                clearance.model_dump(mode="json")
            )
        if permit.clearance_digest != expected_clearance_digest:
            raise ValueError("permit clearance digest mismatch")
