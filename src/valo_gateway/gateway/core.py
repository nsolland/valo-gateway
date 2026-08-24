from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from valo_gateway.contracts import (
    ActionEnvelope,
    AuthorityEnvelope,
    BoundaryReplayInput,
    BoundaryReplayResult,
    Clearance,
    ExecutionPermit,
    ExecutionReceipt,
    ExecutionStatus,
    GovernanceBasisState,
    canonical_digest,
    replay_effect_boundary,
)
from valo_gateway.contracts.models import utcnow
from valo_gateway.resource_budget import (
    ConsumedResourceReservation,
    ResourceBudgetLedger,
    ResourceReservation,
    required_resource_budget_ids,
)
from valo_gateway.tool_adapters import EffectorHandle, ToolRegistry
from valo_gateway.tool_adapters.base import _invoke_tool_from_boundary

from .control import RuntimeControlPlane
from .permit_consumption import PermitConsumptionStore, SQLitePermitConsumptionStore


class ExecutableTool(Protocol):
    def invoke(self, arguments: dict[str, Any]) -> Any: ...


class ToolExecutionResult(BaseModel):
    consumed_permit: ExecutionPermit
    receipt: ExecutionReceipt
    boundary_replay: BoundaryReplayResult
    consumed_resources: tuple[ConsumedResourceReservation, ...] = ()
    response: Any | None = None
    error: str | None = None
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


class ValoGateway:
    def __init__(
        self,
        control_plane: RuntimeControlPlane | None = None,
        permit_store: PermitConsumptionStore | None = None,
    ) -> None:
        self._control_plane = control_plane
        self._permit_store = permit_store or SQLitePermitConsumptionStore.default()

    def execute(
        self,
        *,
        authority: AuthorityEnvelope,
        clearance: Clearance,
        permit: ExecutionPermit,
        action: ActionEnvelope,
        executor_id: str,
        tool: ExecutableTool | None = None,
        effector_registry: ToolRegistry | None = None,
        effector_handle: EffectorHandle | None = None,
        arguments: dict[str, Any] | None = None,
        now: datetime | None = None,
        boundary_replay: BoundaryReplayInput | None = None,
        previous_receipt_hash: str | None = None,
        control_plane: RuntimeControlPlane | None = None,
        control_scopes: list[str] | None = None,
        resource_ledger: ResourceBudgetLedger | None = None,
        resource_reservations: tuple[ResourceReservation, ...] = (),
    ) -> ToolExecutionResult:
        now = now or utcnow()
        registry_path = effector_registry is not None or effector_handle is not None
        if tool is None and not registry_path:
            raise ValueError("governed execution requires one effector path")
        if tool is not None and registry_path:
            raise ValueError("governed execution permits exactly one effector path")
        if registry_path and (
            effector_registry is None or effector_handle is None
        ):
            raise ValueError("effector registry and handle must be bound together")
        if tool is not None and not callable(
            getattr(tool, "_invoke_from_boundary", None)
        ):
            raise PermissionError(
                "NO_DIRECT_EFFECT_PATH: effector lacks boundary-only dispatch"
            )
        self._validate_binding(authority, clearance, permit, action, now)
        replay_input = boundary_replay or BoundaryReplayInput.capture(
            authority=authority,
            clearance=clearance,
            permit=permit,
            action=action,
            governance_basis_state=GovernanceBasisState.VALID,
            evaluated_at=now,
        )
        replay_result = replay_effect_boundary(
            replay_input,
            authority=authority,
            clearance=clearance,
            permit=permit,
            action=action,
        )
        if not replay_result.effect_allowed:
            raise ValueError(
                "structural coupling blocked effect: " + replay_result.reason
            )
        if effector_registry is not None and effector_handle is not None:
            effector_registry.assert_effect_binding(
                effector_handle,
                action_type=action.action_type,
                target=action.target,
            )
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

        if not self._permit_store.consume_once(permit.permit_id, now):
            raise ValueError("execution permit is already consumed")

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
        try:
            if effector_registry is not None and effector_handle is not None:
                response = effector_registry._invoke_from_boundary(
                    effector_handle,
                    arguments or {},
                    replay_result,
                    action_type=action.action_type,
                    target=action.target,
                )
            else:
                response = _invoke_tool_from_boundary(
                    tool,
                    arguments or {},
                    replay_result,
                )
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
                boundary_replay_digest=replay_result.result_digest,
            )
            return ToolExecutionResult(
                consumed_permit=consumed,
                receipt=receipt,
                boundary_replay=replay_result,
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
                boundary_replay_digest=replay_result.result_digest,
            )
            return ToolExecutionResult(
                consumed_permit=consumed,
                receipt=receipt,
                boundary_replay=replay_result,
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
        if action.action_type not in authority.capability_grants:
            raise ValueError("action capability is outside authority grant")
        if action.target not in authority.resource_scope:
            raise ValueError("action target is outside authority scope")
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
