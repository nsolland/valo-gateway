from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChannelKind(str, Enum):
    SLACK = "slack"
    TEAMS = "teams"
    GOOGLE_CHAT = "google_chat"
    DISCORD = "discord"
    EMAIL = "email"
    SMS = "sms"
    MMS = "mms"
    VOICE = "voice"
    IMESSAGE = "imessage"
    OTHER = "other"


class ChannelInteraction(str, Enum):
    MESSAGE = "message"
    COMMAND = "command"
    APPROVAL = "approval"
    FORM_SUBMISSION = "form_submission"
    CALL = "call"


_FORBIDDEN_AUTHORITY_KEYS = {
    "authority_envelope_id",
    "authority_grant",
    "clearance_id",
    "execution_permit",
    "permit_id",
    "reht_clearance",
    "reht_decision",
}


def _reject_authority_claims(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_AUTHORITY_KEYS:
                raise ValueError(f"channel payload cannot carry authority field: {path}.{key}")
            _reject_authority_claims(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_authority_claims(nested, f"{path}[{index}]")


class ChannelEventEvidence(BaseModel):
    provider_id: str
    channel: ChannelKind
    workspace_id: str
    conversation_id: str
    event_id: str
    actor_id: str
    interaction: ChannelInteraction
    observed_at: datetime
    agent_identity_id: str | None = None
    thread_id: str | None = None
    correlation_ref: str | None = None
    transport_verified: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)
    authority_effect: Literal["none"] = "none"
    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator(
        "provider_id",
        "workspace_id",
        "conversation_id",
        "event_id",
        "actor_id",
    )
    @classmethod
    def require_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("channel evidence identities must be non-empty")
        return value

    @field_validator("agent_identity_id")
    @classmethod
    def require_agent_identity(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("agent identity must be non-empty when present")
        return value

    @field_validator("payload")
    @classmethod
    def reject_embedded_authority(cls, value: dict[str, Any]) -> dict[str, Any]:
        _reject_authority_claims(value)
        return value

    @property
    def digest(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


class ChannelEvidenceNormalizer:
    """Normalize collaboration and communication events into non-authoritative evidence."""

    protocol = "channel-evidence"

    def normalize(self, payload: dict[str, Any]) -> ChannelEventEvidence:
        return ChannelEventEvidence(**payload)
