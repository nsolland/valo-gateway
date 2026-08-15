from __future__ import annotations

from typing import Any

from valo_gateway.contracts import (
    ActionEnvelope,
    AuthorityEnvelope,
    Clearance,
    canonical_digest,
)
from valo_gateway.gateway.core import ToolExecutionResult

_SCHEMA = "valo.gateway.execution-observation.v1"


def build_veritas_execution_observation(
    *,
    authority: AuthorityEnvelope,
    clearance: Clearance,
    action: ActionEnvelope,
    result: ToolExecutionResult,
) -> dict[str, Any]:
    """Build the deterministic Gateway -> Veritas execution observation.

    This handoff carries observed execution facts only. It grants no authority
    and does not reinterpret REHT's decision.
    """
    receipt = result.receipt
    consumed = result.consumed_permit
    if consumed.consumed_at is None:
        raise ValueError("Veritas handoff requires a consumed execution permit")
    if receipt.permit_id != consumed.permit_id:
        raise ValueError("receipt permit binding mismatch")
    if receipt.clearance_id != clearance.clearance_id:
        raise ValueError("receipt clearance binding mismatch")
    if receipt.action_digest != action.digest:
        raise ValueError("receipt action binding mismatch")
    if consumed.authority_envelope_id != authority.envelope_id:
        raise ValueError("consumed permit authority binding mismatch")
    if consumed.action_digest != action.digest:
        raise ValueError("consumed permit action binding mismatch")
    if consumed.clearance_id != clearance.clearance_id:
        raise ValueError("consumed permit clearance binding mismatch")
    if clearance.workspace_binding_pair != action.workspace_binding_pair:
        raise ValueError("clearance workspace binding mismatch")
    if consumed.workspace_binding_pair != action.workspace_binding_pair:
        raise ValueError("consumed permit workspace binding mismatch")
    if (
        receipt.workspace_binding_digest,
        receipt.kernel_context_digest,
    ) != (consumed.workspace_binding_digest, consumed.kernel_context_digest):
        raise ValueError("receipt workspace binding mismatch")
    if clearance.execution_substrate_digest != action.execution_substrate_digest:
        raise ValueError("clearance execution substrate binding mismatch")
    if consumed.execution_substrate_digest != action.execution_substrate_digest:
        raise ValueError("consumed permit execution substrate binding mismatch")
    if receipt.execution_substrate_digest != action.execution_substrate_digest:
        raise ValueError("receipt execution substrate binding mismatch")
    expected_clearance_digest = None
    if action.workspace_binding is not None:
        expected_clearance_digest = canonical_digest(clearance.model_dump(mode="json"))
    if consumed.clearance_digest != expected_clearance_digest:
        raise ValueError("consumed permit clearance digest mismatch")
    if receipt.clearance_digest != expected_clearance_digest:
        raise ValueError("receipt clearance digest mismatch")

    payload: dict[str, Any] = {
        "schema": _SCHEMA,
        "execution_id": receipt.execution_id,
        "permit_id": receipt.permit_id,
        "execution_nonce": consumed.execution_nonce,
        "permit_consumed_at": consumed.consumed_at.isoformat(),
        "clearance_id": receipt.clearance_id,
        "clearance_digest": canonical_digest(clearance.model_dump(mode="json")),
        "authority_envelope_id": authority.envelope_id,
        "authority_digest": canonical_digest(authority.model_dump(mode="json")),
        "action_digest": receipt.action_digest,
        "executor_id": receipt.executor_id,
        "started_at": receipt.started_at.isoformat(),
        "completed_at": receipt.completed_at.isoformat(),
        "status": receipt.status.value,
        "response_digest": receipt.response_digest,
        "receipt_hash": receipt.receipt_hash,
        "previous_receipt_hash": receipt.previous_receipt_hash,
        "skill_binding_digest": receipt.skill_binding_digest,
        "authority_granted": False,
    }
    if action.workspace_binding is not None:
        payload.update(
            {
                "workspace_binding": action.workspace_binding.model_dump(mode="json"),
                "workspace_binding_digest": consumed.workspace_binding_digest,
                "kernel_context_digest": consumed.kernel_context_digest,
            }
        )
        substrate = action.workspace_binding.execution_substrate_binding
        if substrate is not None:
            payload.update(
                {
                    "execution_substrate_binding": substrate.model_dump(mode="json"),
                    "execution_substrate_digest": consumed.execution_substrate_digest,
                }
            )
    payload["observation_digest"] = "sha256:" + canonical_digest(payload)
    return payload
