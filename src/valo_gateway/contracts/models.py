from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from enum import Enum
from hashlib import sha256
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


def canonical_digest(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode()
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


class ConfidentialExecutionBinding(BaseModel):
    schema_version: Literal["confidential_execution_binding.v1"] = (
        "confidential_execution_binding.v1"
    )
    substrate_kind: Literal["TEE"] = "TEE"
    attested_workspace_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    substrate_attestation_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    attestation_evidence_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    substrate_id: str = Field(min_length=1)
    tee_type: str = Field(min_length=1)
    gpu_identity: str = Field(min_length=1)
    cc_mode: str = Field(min_length=1)
    measurement: str = Field(min_length=1)
    attestation_verifier: str = Field(min_length=1)
    attested_at: datetime
    valid_until: datetime
    max_attestation_age_seconds: int = Field(gt=0)
    model_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    workload_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    verification_status: Literal["VERIFIED"] = "VERIFIED"
    confidentiality_protected: Literal[True] = True
    integrity_protected: Literal[True] = True
    isolation_enforced: Literal[True] = True
    authority_effect: Literal["NO_AUTHORITY_CREATION"] = "NO_AUTHORITY_CREATION"
    can_issue_clearance: Literal[False] = False
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_lifecycle(self) -> ConfidentialExecutionBinding:
        if self.attested_at.utcoffset() is None or self.valid_until.utcoffset() is None:
            raise ValueError("attestation timestamps must be timezone-aware")
        if self.valid_until <= self.attested_at:
            raise ValueError("attestation valid_until must be after attested_at")
        return self

    @property
    def binding_digest(self) -> str:
        return "sha256:" + canonical_digest(self.model_dump(mode="json"))

    @property
    def fresh_until(self) -> datetime:
        age_limit = self.attested_at + timedelta(
            seconds=self.max_attestation_age_seconds
        )
        return min(self.valid_until, age_limit)

    def is_fresh(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return (
            self.verification_status == "VERIFIED"
            and self.confidentiality_protected is True
            and self.integrity_protected is True
            and self.isolation_enforced is True
            and self.attested_at <= now < self.fresh_until
        )


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
    execution_substrate_binding: ConfidentialExecutionBinding | None = None
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_times(self) -> GovernedWorkspaceLineage:
        if self.workspace_expires_at.utcoffset() is None:
            raise ValueError("workspace_expires_at must be timezone-aware")
        if self.conformed_at.utcoffset() is None:
            raise ValueError("conformed_at must be timezone-aware")
        substrate = self.execution_substrate_binding
        if substrate is not None and not substrate.is_fresh(self.conformed_at):
            raise ValueError(
                "confidential execution substrate must be verified and fresh at conformance"
            )
        return self

    def is_active(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return now < self.workspace_expires_at

    @property
    def binding_pair(self) -> tuple[str, str]:
        return self.workspace_binding_digest, self.kernel_context_digest

    @property
    def execution_substrate_digest(self) -> str | None:
        binding = self.execution_substrate_binding
        return binding.binding_digest if binding is not None else None


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
        return (
            self.skill_context.binding_digest if self.skill_context is not None else None
        )

    @property
    def workspace_binding_pair(self) -> tuple[str, str] | None:
        if self.workspace_binding is None:
            return None
        return self.workspace_binding.binding_pair

    @property
    def execution_substrate_digest(self) -> str | None:
        if self.workspace_binding is None:
            return None
        return self.workspace_binding.execution_substrate_digest


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
    execution_substrate_digest: str | None = Field(
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
        if (
            self.execution_substrate_digest is not None
            and self.workspace_binding_digest is None
        ):
            raise ValueError(
                "execution_substrate_digest requires governed workspace binding"
            )
        return self

    def authorizes_permit(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return (
            self.decision_contract.decision in {Decision.ALLOW, Decision.MODIFY}
            and now < self.valid_until
        )

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
    execution_substrate_digest: str | None = Field(
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
        if (
            self.execution_substrate_digest is not None
            and self.workspace_binding_digest is None
        ):
            raise ValueError(
                "execution_substrate_digest requires governed workspace binding"
            )
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
            raise ValueError(
                "execution permit is expired, not yet active, or already consumed"
            )
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
    execution_substrate_digest: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    clearance_digest: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    boundary_replay_digest: str | None = Field(
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
        if (
            self.execution_substrate_digest is not None
            and self.workspace_binding_digest is None
        ):
            raise ValueError(
                "execution_substrate_digest requires governed workspace binding"
            )
        return self

    @property
    def receipt_hash(self) -> str:
        payload = self.model_dump(mode="json")
        if payload["skill_binding_digest"] is None:
            payload.pop("skill_binding_digest")
        for optional_binding in (
            "workspace_binding_digest",
            "kernel_context_digest",
            "execution_substrate_digest",
            "clearance_digest",
            "boundary_replay_digest",
        ):
            if payload[optional_binding] is None:
                payload.pop(optional_binding)
        return canonical_digest(payload)


def issue_execution_permit(
    *,
    clearance: Clearance,
    authority: AuthorityEnvelope,
    action: ActionEnvelope,
    expires_at: datetime,
    now: datetime | None = None,
) -> ExecutionPermit:
    now = now or utcnow()
    if not authority.is_active(now):
        raise ValueError("authority envelope is inactive or revoked")
    if clearance.authority_envelope_id != authority.envelope_id:
        raise ValueError("clearance authority binding mismatch")
    if action.authority_envelope_id != authority.envelope_id:
        raise ValueError("action authority binding mismatch")
    if action.action_type not in authority.capability_grants:
        raise ValueError("action capability is outside authority grant")
    if action.target not in authority.resource_scope:
        raise ValueError("action target is outside authority scope")
    if clearance.action_digest != action.digest:
        raise ValueError("clearance action binding mismatch")
    if clearance.skill_binding_digest != action.skill_binding_digest:
        raise ValueError("clearance skill binding mismatch")
    if clearance.workspace_binding_pair != action.workspace_binding_pair:
        raise ValueError("clearance workspace binding mismatch")
    if clearance.execution_substrate_digest != action.execution_substrate_digest:
        raise ValueError("clearance execution substrate binding mismatch")
    if action.workspace_binding is not None and not action.workspace_binding.is_active(now):
        raise ValueError("governed workspace is expired at permit issuance")
    substrate = (
        action.workspace_binding.execution_substrate_binding
        if action.workspace_binding is not None
        else None
    )
    if substrate is not None and not substrate.is_fresh(now):
        raise ValueError(
            "confidential execution substrate is not verified and fresh at permit issuance"
        )
    contract = clearance.decision_contract
    if (
        contract.principal_id != authority.principal_id
        or contract.actor_id != authority.actor_id
    ):
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
    if substrate is not None and expires_at > substrate.fresh_until:
        raise ValueError("permit cannot outlive confidential execution freshness")
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
        execution_substrate_digest=action.execution_substrate_digest,
        clearance_digest=clearance_digest,
        issued_at=now,
        expires_at=expires_at,
    )
