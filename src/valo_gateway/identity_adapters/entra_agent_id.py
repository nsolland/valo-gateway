from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from valo_gateway.contracts.models import canonical_digest, utcnow


class EntraAgentAccessMode(str, Enum):
    AUTONOMOUS = "autonomous"
    ON_BEHALF_OF = "on_behalf_of"


class ConditionalAccessDecision(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    ALLOW = "allow"
    BLOCK = "block"
    REPORT_ONLY = "report_only"
    UNKNOWN = "unknown"


class EntraAgentIdContext(BaseModel):
    tenant_id: str
    agent_identity_id: str
    blueprint_id: str | None = None
    blueprint_principal_id: str | None = None
    access_mode: EntraAgentAccessMode
    subject_id: str | None = None
    audience: str
    resource: str | None = None
    delegated_scopes: list[str] = Field(default_factory=list)
    application_permissions: list[str] = Field(default_factory=list)
    entra_roles: list[str] = Field(default_factory=list)
    azure_roles: list[str] = Field(default_factory=list)
    access_package_refs: list[str] = Field(default_factory=list)
    owner_ids: list[str] = Field(default_factory=list)
    sponsor_ids: list[str] = Field(default_factory=list)
    conditional_access: ConditionalAccessDecision = ConditionalAccessDecision.NOT_EVALUATED
    risk_level: str | None = None
    token_issued_at: datetime | None = None
    token_expires_at: datetime | None = None
    session_id: str | None = None
    disabled: bool = False
    revoked_at: datetime | None = None
    revocation_ref: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_context(self) -> EntraAgentIdContext:
        if self.access_mode is EntraAgentAccessMode.ON_BEHALF_OF and not self.subject_id:
            raise ValueError("subject_id is required for on-behalf-of agent access")
        if (self.token_issued_at is None) != (self.token_expires_at is None):
            raise ValueError("token_issued_at and token_expires_at must be supplied together")
        if self.token_issued_at is not None and self.token_expires_at <= self.token_issued_at:
            raise ValueError("token_expires_at must be later than token_issued_at")
        if self.revoked_at is not None and not self.revocation_ref:
            raise ValueError("revocation_ref is required when revoked_at is set")
        return self

    @property
    def binding_digest(self) -> str:
        return "sha256:" + canonical_digest(self.model_dump(mode="json"))

    def is_current_access(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        if self.disabled or self.revoked_at is not None:
            return False
        if self.conditional_access is ConditionalAccessDecision.BLOCK:
            return False
        if self.token_issued_at is not None:
            return self.token_issued_at <= now < self.token_expires_at
        return True

    def to_reht_evidence(self) -> dict[str, Any]:
        return {
            "provider": "microsoft_entra_agent_id",
            "authoritative": False,
            "identity": {
                "tenant_id": self.tenant_id,
                "agent_identity_id": self.agent_identity_id,
                "blueprint_id": self.blueprint_id,
                "blueprint_principal_id": self.blueprint_principal_id,
                "access_mode": self.access_mode.value,
                "subject_id": self.subject_id,
                "owner_ids": self.owner_ids,
                "sponsor_ids": self.sponsor_ids,
            },
            "access": {
                "audience": self.audience,
                "resource": self.resource,
                "delegated_scopes": self.delegated_scopes,
                "application_permissions": self.application_permissions,
                "entra_roles": self.entra_roles,
                "azure_roles": self.azure_roles,
                "access_package_refs": self.access_package_refs,
            },
            "runtime_state": {
                "conditional_access": self.conditional_access.value,
                "risk_level": self.risk_level,
                "token_issued_at": self.token_issued_at,
                "token_expires_at": self.token_expires_at,
                "session_id": self.session_id,
                "disabled": self.disabled,
                "revoked_at": self.revoked_at,
                "revocation_ref": self.revocation_ref,
            },
            "evidence_refs": self.evidence_refs,
            "metadata": self.metadata,
            "binding_digest": self.binding_digest,
        }
