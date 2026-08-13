from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from threading import RLock
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import canonical_digest
from .contracts.models import utcnow


class MessageSigner(Protocol):
    key_id: str
    algorithm: str

    def sign_digest(self, digest: str) -> str: ...


class MessageSignatureVerifier(Protocol):
    key_id: str
    algorithm: str

    def verify_digest(self, digest: str, signature: str) -> bool: ...


class ReplayStore(Protocol):
    def claim_once(self, replay_key: str, expires_at: datetime) -> bool: ...


class HMACSHA256Authenticator:
    algorithm = "HMAC-SHA256"

    def __init__(self, *, key_id: str, key: bytes) -> None:
        if not key_id:
            raise ValueError("key_id is required")
        if len(key) < 32:
            raise ValueError("HMAC key must be at least 32 bytes")
        self.key_id = key_id
        self._key = bytes(key)

    def sign_digest(self, digest: str) -> str:
        return hmac.new(self._key, digest.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify_digest(self, digest: str, signature: str) -> bool:
        return hmac.compare_digest(self.sign_digest(digest), signature)


class InMemoryReplayStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._claims: dict[str, datetime] = {}

    def claim_once(self, replay_key: str, expires_at: datetime) -> bool:
        now = utcnow()
        with self._lock:
            for key, expiry in tuple(self._claims.items()):
                if expiry < now:
                    self._claims.pop(key, None)
            if replay_key in self._claims:
                return False
            self._claims[replay_key] = expires_at
            return True


class GovernedMessageEnvelopeV1(BaseModel):
    schema_id: Literal["valo.gateway.governed-message-envelope.v1"] = (
        "valo.gateway.governed-message-envelope.v1"
    )
    message_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1)
    workflow_id: str = Field(min_length=1)
    parent_message_id: str | None = None
    parent_message_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    sender_principal_id: str = Field(min_length=1)
    sender_actor_id: str = Field(min_length=1)
    recipient_id: str = Field(min_length=1)
    purpose_id: str = Field(min_length=1)
    scope: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    nonce: str = Field(min_length=16)
    payload_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    originating_authority_envelope_ref: str = Field(min_length=1)
    originating_authority_envelope_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    delegation_chain_ref: str = Field(min_length=1)
    delegation_chain_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    provenance_ref: str | None = None
    key_id: str = Field(min_length=1)
    signature_algorithm: str = Field(min_length=1)
    signature: str = Field(pattern=r"^[a-f0-9]{64}$")
    replay_guard: Literal["message_id_nonce_once"] = "message_id_nonce_once"
    grants_authority: Literal[False] = False
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_envelope(self) -> GovernedMessageEnvelopeV1:
        if self.issued_at.utcoffset() is None or self.expires_at.utcoffset() is None:
            raise ValueError("message timestamps must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValueError("message expires_at must be later than issued_at")
        if not self.scope or "*" in self.scope or len(self.scope) != len(set(self.scope)):
            raise ValueError("message scope must be explicit and unique")
        if (self.parent_message_id is None) != (self.parent_message_digest is None):
            raise ValueError("parent message id and digest must be supplied together")
        return self

    @property
    def signing_digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json", exclude={"signature"}))

    @property
    def envelope_digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))

    def payload_matches(self, payload: Any) -> bool:
        return canonical_digest(payload) == self.payload_digest

    @classmethod
    def sign(
        cls,
        *,
        payload: Any,
        workflow_id: str,
        sender_principal_id: str,
        sender_actor_id: str,
        recipient_id: str,
        purpose_id: str,
        scope: tuple[str, ...],
        issued_at: datetime,
        expires_at: datetime,
        nonce: str,
        originating_authority_envelope_ref: str,
        originating_authority_envelope_digest: str,
        delegation_chain_ref: str,
        delegation_chain_digest: str,
        signer: MessageSigner,
        message_id: str | None = None,
        parent_message_id: str | None = None,
        parent_message_digest: str | None = None,
        provenance_ref: str | None = None,
    ) -> GovernedMessageEnvelopeV1:
        candidate = cls(
            message_id=message_id or str(uuid4()),
            workflow_id=workflow_id,
            parent_message_id=parent_message_id,
            parent_message_digest=parent_message_digest,
            sender_principal_id=sender_principal_id,
            sender_actor_id=sender_actor_id,
            recipient_id=recipient_id,
            purpose_id=purpose_id,
            scope=scope,
            issued_at=issued_at,
            expires_at=expires_at,
            nonce=nonce,
            payload_digest=canonical_digest(payload),
            originating_authority_envelope_ref=originating_authority_envelope_ref,
            originating_authority_envelope_digest=originating_authority_envelope_digest,
            delegation_chain_ref=delegation_chain_ref,
            delegation_chain_digest=delegation_chain_digest,
            provenance_ref=provenance_ref,
            key_id=signer.key_id,
            signature_algorithm=signer.algorithm,
            signature="0" * 64,
        )
        values = candidate.model_dump()
        values["signature"] = signer.sign_digest(candidate.signing_digest)
        return cls(**values)


class AcceptedMessageReceipt(BaseModel):
    message_id: str
    workflow_id: str
    sender_principal_id: str
    sender_actor_id: str
    recipient_id: str
    purpose_id: str
    scope: tuple[str, ...]
    originating_authority_envelope_ref: str
    delegation_chain_ref: str
    envelope_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    accepted_at: datetime
    grants_authority: Literal[False] = False
    model_config = ConfigDict(extra="forbid", frozen=True)

    @property
    def digest(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class GovernedMessageVerifier:
    def __init__(self, *, replay_store: ReplayStore) -> None:
        self._replay_store = replay_store

    def accept(
        self,
        *,
        envelope: GovernedMessageEnvelopeV1,
        payload: Any,
        verifier: MessageSignatureVerifier,
        expected_recipient_id: str,
        expected_sender_principal_id: str | None = None,
        expected_sender_actor_id: str | None = None,
        expected_purpose_id: str | None = None,
        expected_workflow_id: str | None = None,
        expected_authority_envelope_ref: str | None = None,
        expected_delegation_chain_digest: str | None = None,
        allowed_scope: tuple[str, ...] | None = None,
        parent_envelope: GovernedMessageEnvelopeV1 | None = None,
        now: datetime | None = None,
    ) -> AcceptedMessageReceipt:
        now = now or utcnow()
        if now.utcoffset() is None:
            raise ValueError("verification time must be timezone-aware")
        if now < envelope.issued_at:
            raise ValueError("message is not yet valid")
        if now >= envelope.expires_at:
            raise ValueError("message is expired")
        if envelope.recipient_id != expected_recipient_id:
            raise ValueError("message recipient binding mismatch")
        if expected_sender_principal_id is not None and envelope.sender_principal_id != expected_sender_principal_id:
            raise ValueError("message sender principal binding mismatch")
        if expected_sender_actor_id is not None and envelope.sender_actor_id != expected_sender_actor_id:
            raise ValueError("message sender actor binding mismatch")
        if expected_purpose_id is not None and envelope.purpose_id != expected_purpose_id:
            raise ValueError("message purpose binding mismatch")
        if expected_workflow_id is not None and envelope.workflow_id != expected_workflow_id:
            raise ValueError("message workflow binding mismatch")
        if expected_authority_envelope_ref is not None and envelope.originating_authority_envelope_ref != expected_authority_envelope_ref:
            raise ValueError("message originating authority binding mismatch")
        if expected_delegation_chain_digest is not None and envelope.delegation_chain_digest != expected_delegation_chain_digest:
            raise ValueError("message delegation-chain binding mismatch")
        if allowed_scope is not None and not set(envelope.scope).issubset(allowed_scope):
            raise ValueError("message scope exceeds accepted scope")
        self._verify_parent(envelope, parent_envelope)
        if envelope.key_id != verifier.key_id:
            raise ValueError("message key binding mismatch")
        if envelope.signature_algorithm != verifier.algorithm:
            raise ValueError("message signature algorithm mismatch")
        if not envelope.payload_matches(payload):
            raise ValueError("message payload digest mismatch")
        if not verifier.verify_digest(envelope.signing_digest, envelope.signature):
            raise ValueError("message signature verification failed")
        replay_key = canonical_digest(
            {
                "message_id": envelope.message_id,
                "workflow_id": envelope.workflow_id,
                "sender_principal_id": envelope.sender_principal_id,
                "sender_actor_id": envelope.sender_actor_id,
                "recipient_id": envelope.recipient_id,
                "nonce": envelope.nonce,
                "envelope_digest": envelope.envelope_digest,
            }
        )
        if not self._replay_store.claim_once(replay_key, envelope.expires_at):
            raise ValueError("message replay detected")
        return AcceptedMessageReceipt(
            message_id=envelope.message_id,
            workflow_id=envelope.workflow_id,
            sender_principal_id=envelope.sender_principal_id,
            sender_actor_id=envelope.sender_actor_id,
            recipient_id=envelope.recipient_id,
            purpose_id=envelope.purpose_id,
            scope=envelope.scope,
            originating_authority_envelope_ref=envelope.originating_authority_envelope_ref,
            delegation_chain_ref=envelope.delegation_chain_ref,
            envelope_digest=envelope.envelope_digest,
            accepted_at=now,
        )

    @staticmethod
    def _verify_parent(
        envelope: GovernedMessageEnvelopeV1,
        parent: GovernedMessageEnvelopeV1 | None,
    ) -> None:
        if envelope.parent_message_id is None:
            if parent is not None:
                raise ValueError("unexpected parent envelope")
            return
        if parent is None:
            raise ValueError("parent envelope is required")
        if envelope.parent_message_id != parent.message_id:
            raise ValueError("parent message id mismatch")
        if envelope.parent_message_digest != parent.envelope_digest:
            raise ValueError("parent message digest mismatch")
        if envelope.workflow_id != parent.workflow_id:
            raise ValueError("child message changed workflow")
        if (
            envelope.originating_authority_envelope_ref
            != parent.originating_authority_envelope_ref
            or envelope.originating_authority_envelope_digest
            != parent.originating_authority_envelope_digest
        ):
            raise ValueError("child message changed originating authority")
        if not set(envelope.scope).issubset(parent.scope):
            raise ValueError("child message expands scope across hop")
