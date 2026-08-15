from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import (
    ActionEnvelope,
    AuthorityEnvelope,
    Clearance,
    Decision,
    ExecutionPermit,
    canonical_digest,
)


class GovernanceBasisState(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    STALE = "STALE"
    REVOKED = "REVOKED"
    SUSPENDED = "SUSPENDED"
    UNRESOLVED = "UNRESOLVED"


class BoundaryReplayOutcome(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class BoundaryReplayInput(BaseModel):
    schema_version: Literal["effect_boundary_replay.v1"] = "effect_boundary_replay.v1"
    action_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    clearance_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    permit_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Decision
    governance_basis_state: GovernanceBasisState
    evaluated_at: datetime
    input_digest: str = ""

    model_config = ConfigDict(extra="forbid", frozen=True)

    def canonical_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"input_digest"})

    @property
    def computed_digest(self) -> str:
        return canonical_digest(self.canonical_payload())

    @model_validator(mode="after")
    def validate_replay_input(self) -> BoundaryReplayInput:
        if self.evaluated_at.utcoffset() is None:
            raise ValueError("boundary replay time must be timezone-aware")
        if self.input_digest and self.input_digest != self.computed_digest:
            raise ValueError("boundary replay input digest mismatch")
        return self

    @classmethod
    def capture(
        cls,
        *,
        authority: AuthorityEnvelope,
        clearance: Clearance,
        permit: ExecutionPermit,
        action: ActionEnvelope,
        governance_basis_state: GovernanceBasisState,
        evaluated_at: datetime,
    ) -> BoundaryReplayInput:
        contract_payload = {
            "policy_digest": action.policy_digest,
            "decision_contract": clearance.decision_contract.model_dump(mode="json"),
        }
        state_payload = {
            "context_digest": action.context_digest,
            "workspace_binding": (
                action.workspace_binding.model_dump(mode="json")
                if action.workspace_binding is not None
                else None
            ),
        }
        values = {
            "action_digest": action.digest,
            "contract_digest": canonical_digest(contract_payload),
            "state_digest": canonical_digest(state_payload),
            "authority_digest": canonical_digest(authority.model_dump(mode="json")),
            "evidence_digest": canonical_digest(sorted(clearance.evidence_refs)),
            "decision_digest": canonical_digest(
                clearance.decision_contract.model_dump(mode="json")
            ),
            "clearance_digest": canonical_digest(clearance.model_dump(mode="json")),
            "permit_digest": canonical_digest(permit.model_dump(mode="json")),
            "decision": clearance.decision_contract.decision,
            "governance_basis_state": governance_basis_state,
            "evaluated_at": evaluated_at,
        }
        provisional = cls(**values)
        return provisional.model_copy(
            update={"input_digest": provisional.computed_digest}
        )


class BoundaryReplayResult(BaseModel):
    schema_version: Literal["effect_boundary_replay_result.v1"] = (
        "effect_boundary_replay_result.v1"
    )
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: BoundaryReplayOutcome
    reason: str
    effect_allowed: bool
    result_digest: str = ""

    model_config = ConfigDict(extra="forbid", frozen=True)

    def canonical_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"result_digest"})

    @property
    def computed_digest(self) -> str:
        return canonical_digest(self.canonical_payload())

    @model_validator(mode="after")
    def validate_replay_result(self) -> BoundaryReplayResult:
        if self.effect_allowed != (self.outcome is BoundaryReplayOutcome.READY):
            raise ValueError("boundary replay outcome/effect mismatch")
        if self.result_digest and self.result_digest != self.computed_digest:
            raise ValueError("boundary replay result digest mismatch")
        return self


def _result(
    replay_input: BoundaryReplayInput,
    *,
    outcome: BoundaryReplayOutcome,
    reason: str,
) -> BoundaryReplayResult:
    provisional = BoundaryReplayResult(
        input_digest=replay_input.input_digest or replay_input.computed_digest,
        outcome=outcome,
        reason=reason,
        effect_allowed=outcome is BoundaryReplayOutcome.READY,
    )
    return provisional.model_copy(update={"result_digest": provisional.computed_digest})


def replay_effect_boundary(
    replay_input: BoundaryReplayInput,
    *,
    authority: AuthorityEnvelope,
    clearance: Clearance,
    permit: ExecutionPermit,
    action: ActionEnvelope,
) -> BoundaryReplayResult:
    if replay_input.input_digest != replay_input.computed_digest:
        return _result(
            replay_input,
            outcome=BoundaryReplayOutcome.BLOCKED,
            reason="BOUNDARY_INPUT_UNSEALED",
        )

    expected = BoundaryReplayInput.capture(
        authority=authority,
        clearance=clearance,
        permit=permit,
        action=action,
        governance_basis_state=replay_input.governance_basis_state,
        evaluated_at=replay_input.evaluated_at,
    )
    pinned_fields = (
        "action_digest",
        "contract_digest",
        "state_digest",
        "authority_digest",
        "evidence_digest",
        "decision_digest",
        "clearance_digest",
        "permit_digest",
        "decision",
    )
    mismatches = tuple(
        field
        for field in pinned_fields
        if getattr(replay_input, field) != getattr(expected, field)
    )
    if mismatches:
        return _result(
            replay_input,
            outcome=BoundaryReplayOutcome.BLOCKED,
            reason="PINNED_INPUT_MISMATCH:" + ",".join(mismatches),
        )

    if replay_input.governance_basis_state is not GovernanceBasisState.VALID:
        return _result(
            replay_input,
            outcome=BoundaryReplayOutcome.BLOCKED,
            reason=f"GOVERNANCE_BASIS_{replay_input.governance_basis_state.value}",
        )

    if replay_input.decision not in {Decision.ALLOW, Decision.MODIFY}:
        return _result(
            replay_input,
            outcome=BoundaryReplayOutcome.BLOCKED,
            reason="NULL_EFFECT_ON_DENY",
        )

    moment = replay_input.evaluated_at
    if not authority.is_active(moment):
        return _result(
            replay_input,
            outcome=BoundaryReplayOutcome.BLOCKED,
            reason="AUTHORITY_NOT_CURRENT",
        )
    if not clearance.authorizes_permit(moment):
        return _result(
            replay_input,
            outcome=BoundaryReplayOutcome.BLOCKED,
            reason="CLEARANCE_NOT_CURRENT",
        )
    if not permit.is_usable(moment):
        return _result(
            replay_input,
            outcome=BoundaryReplayOutcome.BLOCKED,
            reason="PERMIT_NOT_CURRENT",
        )

    return _result(
        replay_input,
        outcome=BoundaryReplayOutcome.READY,
        reason="GOVERNED_BOUNDARY_READY",
    )
