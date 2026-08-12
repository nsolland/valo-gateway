from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()
    return sha256(raw).hexdigest()


class Decision(str, Enum):
    ALLOW = "ALLOW"
    MODIFY = "MODIFY"
    DEFER = "DEFER"
    DENY = "DENY"
    STEP_UP = "STEP_UP"
    HALT = "HALT"


class AuthoritySource(str, Enum):
    INTERNAL = "internal"
    AAP = "aap"
    AGENT_PASSPORT = "agent_passport"
    OAUTH = "oauth"
    OIDC = "oidc"
    SPIFFE = "spiffe"
    MCP = "mcp"
    HUMAN_ATTESTATION = "human_attestation"


class AuthorityEnvelope(BaseModel):
    envelope_id: str = Field(default_factory=lambda: str(uuid4()))
    principal_id: str
    actor_id: str
    source: AuthoritySource
    issuer: str
    capability_grants: list[str] = Field(default_factory=list)
    resource_scope: list[str] = Field(default_factory=list)
    purpose_scope: list[str] = Field(default_factory=list)
    issued_at: datetime = Field(default_factory=utcnow)
    valid_until: datetime
    revoked_at: datetime | None = None
    revocation_ref: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    signature_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> AuthorityEnvelope:
        if self.valid_until <= self.issued_at:
            raise ValueError("valid_until must be later than issued_at")
        if self.revoked_at is not None and not self.revocation_ref:
            raise ValueError("revocation_ref is required when revoked_at is set")
        return self

    def is_active(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return self.revoked_at is None and self.issued_at <= now < self.valid_until


class AgentSkillContext(BaseModel):
    skill_id: str
    skill_version: str
    skill_source: str
    skill_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    skill_provenance: dict[str, str] = Field(default_factory=dict)
    skill_requested_capabilities: list[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid", frozen=True)

    @property
    def binding_digest(self) -> str:
        return "sha256:" + canonical_digest(self.model_dump(mode="json"))


class GovernedWorkspaceLineage(BaseModel):
    tenant_id: str = Field(min_length=1)
    work_unit_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    workspace_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    workspace_expires_at: datetime
    program_ref: str = Field(min_length=1)
    program_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    invocation_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    candidate_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    proposed_action_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    conformance_report_id: str = Field(min_length=1)
    conformance_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_state_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    conformed_state_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source_event_position: int = Field(ge=0)
    conformed_at: datetime
    dependency_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    workspace_binding_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    kernel_context_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_times(self) -> GovernedWorkspaceLineage:
        if self.workspace_expires_at.utcoffset() is None:
            raise ValueError("workspace_expires_at must be timezone-aware")
        if self.conformed_at.utcoffset() is None:
            raise ValueError("conformed_at must be timezone-aware")
        return self

    def is_active(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return now < self.workspace_expires_at

    @property
    def binding_pair(self) -> tuple[str, str]:
        return self.workspace_binding_digest, self.kernel_context_digest


class ActionEnvelope(BaseModel):
    action_type: str
    target: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    context_digest: str
    policy_digest: str
    authority_envelope_id: str
    skill_context: AgentSkillContext | None = None
    workspace_binding: GovernedWorkspaceLineage | None = None
    nonce: str = Field(default_factory=lambda: str(uuid4()))
    model_config = ConfigDict(extra="forbid", frozen=True)

    @property
    def digest(self) -> str:
        payload = self.model_dump(mode="json")
        if payload["skill_context"] is None:
            payload.pop("skill_context")
        if payload["workspace_binding"] is None:
            payload.pop("workspace_binding")
        return canonical_digest(payload)

    @property
    def skill_binding_digest(self) -> str | None:
        return self.skill_context.binding_digest if self.skill_context is not None else None

    @property
    def workspace_binding_pair(self) -> tuple[str, str] | None:
        if self.workspace_binding is None:
            return None
        return self.workspace_binding.binding_pair


class DecisionContract(BaseModel):
    decision: Decision
    principal_id: str
    actor_id: str
    action_type: str
    target: str
    constraints: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid", frozen=True)


class Clearance(BaseModel):
    clearance_id: str = Field(default_factory=lambda: str(uuid4()))
    action_digest: str
    authority_envelope_id: str
    decision_contract: DecisionContract
    decided_at: datetime = Field(default_factory=utcnow)
    valid_until: datetime
    reht_ref: str
    skill_binding_digest: str | None = None
    workspace_binding_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    kernel_context_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    evidence_refs: list[str] = Field(default_factory=list)
    policy_refs: list[str] = Field(default_factory=list)
    receipt_chain_hash: str | None = None
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_workspace_binding(self) -> Clearance:
        if (self.workspace_binding_digest is None) != (
            self.kernel_context_digest is None
        ):
            raise ValueError(
                "workspace_binding_digest and kernel_context_digest must be bound together"
            )
        return self

    def authorizes_permit(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return self.decision_contract.decision in {Decision.ALLOW, Decision.MODIFY} and now < self.valid_until

    @property
    def workspace_binding_pair(self) -> tuple[str, str] | None:
        kernel_context_digest = self.kernel_context_digest
        if self.workspace_binding_digest is None or kernel_context_digest is None:
            return None
        return self.workspace_binding_digest, kernel_context_digest


class ExecutionPermit(BaseModel):
    permit_id: str = Field(default_factory=lambda: str(uuid4()))
    clearance_id: str
    action_digest: str
    authority_envelope_id: str
    skill_binding_digest: str | None = None
    workspace_binding_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    kernel_context_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    clearance_digest: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    issued_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    consumed_at: datetime | None = None
    execution_nonce: str = Field(default_factory=lambda: str(uuid4()))
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> ExecutionPermit:
        if self.expires_at <= self.issued_at:
            raise ValueError("expires_at must be later than issued_at")
        if (self.workspace_binding_digest is None) != (
            self.kernel_context_digest is None
        ):
            raise ValueError(
                "workspace_binding_digest and kernel_context_digest must be bound together"
            )
        if self.workspace_binding_digest is not None and self.clearance_digest is None:
            raise ValueError("governed workspace permit requires clearance_digest")
        return self

    @property
    def workspace_binding_pair(self) -> tuple[str, str] | None:
        kernel_context_digest = self.kernel_context_digest
        if self.workspace_binding_digest is None or kernel_context_digest is None:
            return None
        return self.workspace_binding_digest, kernel_context_digest

    def is_usable(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return self.consumed_at is None and self.issued_at <= now < self.expires_at

    def consume(self, now: datetime | None = None) -> ExecutionPermit:
        now = now or utcnow()
        if not self.is_usable(now):
            raise ValueError("execution permit is expired, not yet active, or already consumed")
        return self.model_copy(update={"consumed_at": now})


class ExecutionStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class ExecutionReceipt(BaseModel):
    execution_id: str = Field(default_factory=lambda: str(uuid4()))
    permit_id: str
    clearance_id: str
    action_digest: str
    executor_id: str
    started_at: datetime
    completed_at: datetime
    status: ExecutionStatus
    response_digest: str | None = None
    previous_receipt_hash: str | None = None
    skill_binding_digest: str | None = None
    workspace_binding_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    kernel_context_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    clearance_digest: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_workspace_binding(self) -> ExecutionReceipt:
        if (self.workspace_binding_digest is None) != (
            self.kernel_context_digest is None
        ):
            raise ValueError(
                "workspace_binding_digest and kernel_context_digest must be bound together"
            )
        if self.workspace_binding_digest is not None and self.clearance_digest is None:
            raise ValueError("governed workspace receipt requires clearance_digest")
        return self

    @property
    def receipt_hash(self) -> str:
        payload = self.model_dump(mode="json")
        if payload["skill_binding_digest"] is None:
            payload.pop("skill_binding_digest")
        for optional_binding in (
            "workspace_binding_digest",
            "kernel_context_digest",
            "clearance_digest",
        ):
            if payload[optional_binding] is None:
                payload.pop(optional_binding)
        return canonical_digest(payload)


def issue_execution_permit(*, clearance: Clearance, authority: AuthorityEnvelope,
                           action: ActionEnvelope, expires_at: datetime,
                           now: datetime | None = None) -> ExecutionPermit:
    now = now or utcnow()
    if not authority.is_active(now):
        raise ValueError("authority envelope is inactive or revoked")
    if clearance.authority_envelope_id != authority.envelope_id:
        raise ValueError("clearance authority binding mismatch")
    if action.authority_envelope_id != authority.envelope_id:
        raise ValueError("action authority binding mismatch")
    if clearance.action_digest != action.digest:
        raise ValueError("clearance action binding mismatch")
    if clearance.skill_binding_digest != action.skill_binding_digest:
        raise ValueError("clearance skill binding mismatch")
    if clearance.workspace_binding_pair != action.workspace_binding_pair:
        raise ValueError("clearance workspace binding mismatch")
    if action.workspace_binding is not None and not action.workspace_binding.is_active(now):
        raise ValueError("governed workspace is expired at permit issuance")
    contract = clearance.decision_contract
    if contract.principal_id != authority.principal_id or contract.actor_id != authority.actor_id:
        raise ValueError("decision contract identity binding mismatch")
    if contract.action_type != action.action_type or contract.target != action.target:
        raise ValueError("decision contract action binding mismatch")
    if not clearance.authorizes_permit(now):
        raise ValueError("clearance decision cannot issue an execution permit")
    if expires_at > clearance.valid_until or expires_at > authority.valid_until:
        raise ValueError("permit cannot outlive clearance or authority")
    if (
        action.workspace_binding is not None
        and expires_at > action.workspace_binding.workspace_expires_at
    ):
        raise ValueError("permit cannot outlive governed workspace")
    clearance_digest = None
    if action.workspace_binding is not None:
        clearance_digest = canonical_digest(clearance.model_dump(mode="json"))
    return ExecutionPermit(
        clearance_id=clearance.clearance_id,
        action_digest=action.digest,
        authority_envelope_id=authority.envelope_id,
        skill_binding_digest=action.skill_binding_digest,
        workspace_binding_digest=(
            action.workspace_binding.workspace_binding_digest
            if action.workspace_binding is not None
            else None
        ),
        kernel_context_digest=(
            action.workspace_binding.kernel_context_digest
            if action.workspace_binding is not None
            else None
        ),
        clearance_digest=clearance_digest,
        issued_at=now,
        expires_at=expires_at,
    )
