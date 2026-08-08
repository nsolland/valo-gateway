from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from valo_gateway.contracts.models import canonical_digest, utcnow


_FORBIDDEN_AUTHORITY_KEYS = {
    "authoritative",
    "authority_effect",
    "authority_envelope_id",
    "authority_grant",
    "authorization",
    "clearance",
    "clearance_id",
    "decision",
    "decision_contract",
    "execution_permit",
    "permit",
    "permit_id",
    "reht_clearance",
    "reht_decision",
}


def _reject_authority_claims(value: Any, path: str = "entra") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_AUTHORITY_KEYS:
                raise ValueError(f"Entra context cannot carry authority field: {path}.{key}")
            _reject_authority_claims(nested, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _reject_authority_claims(nested, f"{path}[{index}]")


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

    @model_validator(mode="before")
    @classmethod
    def reject_authority_payload(cls, value: Any) -> Any:
        _reject_authority_claims(value)
        return value

    @field_validator(
        "tenant_id",
        "agent_identity_id",
        "blueprint_id",
        "blueprint_principal_id",
        "subject_id",
        "audience",
        "resource",
        "risk_level",
        "session_id",
        "revocation_ref",
    )
    @classmethod
    def reject_blank_refs(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Entra identity/access references must be non-empty")
        return value

    @field_validator(
        "delegated_scopes",
        "application_permissions",
        "entra_roles",
        "azure_roles",
        "access_package_refs",
        "owner_ids",
        "sponsor_ids",
        "evidence_refs",
    )
    @classmethod
    def reject_blank_list_values(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("Entra list values must be non-empty")
        return normalized

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
        serialized = self.model_dump(mode="json")
        return {
            "provider": "microsoft_entra_agent_id",
            "authoritative": False,
            "identity": {
                "tenant_id": serialized["tenant_id"],
                "agent_identity_id": serialized["agent_identity_id"],
                "blueprint_id": serialized["blueprint_id"],
                "blueprint_principal_id": serialized["blueprint_principal_id"],
                "access_mode": serialized["access_mode"],
                "subject_id": serialized["subject_id"],
                "owner_ids": serialized["owner_ids"],
                "sponsor_ids": serialized["sponsor_ids"],
            },
            "access": {
                "audience": serialized["audience"],
                "resource": serialized["resource"],
                "delegated_scopes": serialized["delegated_scopes"],
                "application_permissions": serialized["application_permissions"],
                "entra_roles": serialized["entra_roles"],
                "azure_roles": serialized["azure_roles"],
                "access_package_refs": serialized["access_package_refs"],
            },
            "runtime_state": {
                "conditional_access": serialized["conditional_access"],
                "risk_level": serialized["risk_level"],
                "token_issued_at": serialized["token_issued_at"],
                "token_expires_at": serialized["token_expires_at"],
                "session_id": serialized["session_id"],
                "disabled": serialized["disabled"],
                "revoked_at": serialized["revoked_at"],
                "revocation_ref": serialized["revocation_ref"],
            },
            "evidence_refs": serialized["evidence_refs"],
            "metadata": serialized["metadata"],
            "binding_digest": self.binding_digest,
        }
