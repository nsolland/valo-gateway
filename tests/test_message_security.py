from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from valo_gateway import (
    GovernedMessageEnvelopeV1,
    GovernedMessageVerifier,
    HMACSHA256Authenticator,
    InMemoryReplayStore,
)


def _auth() -> HMACSHA256Authenticator:
    return HMACSHA256Authenticator(key_id="key:agents:v1", key=b"k" * 32)


def _sign(
    payload=None,
    *,
    now: datetime | None = None,
    scope: tuple[str, ...] = ("document:doc:1",),
    parent: GovernedMessageEnvelopeV1 | None = None,
):
    now = now or datetime.now(UTC)
    payload = payload or {"task": "summarize", "document": "doc:1"}
    return payload, GovernedMessageEnvelopeV1.sign(
        payload=payload,
        workflow_id="workflow:brief:1",
        sender_principal_id="principal:research",
        sender_actor_id="agent:research",
        recipient_id="agent:writer",
        purpose_id="prepare_brief",
        scope=scope,
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
        nonce=f"nonce-stage3-{scope[0]}-0001",
        originating_authority_envelope_ref="urn:valo:authority:ctx:1",
        originating_authority_envelope_digest="a" * 64,
        delegation_chain_ref="urn:valo:delegation:chain:1",
        delegation_chain_digest="b" * 64,
        signer=_auth(),
        parent_message_id=parent.message_id if parent else None,
        parent_message_digest=parent.envelope_digest if parent else None,
        provenance_ref="urn:valo:provenance:message:1",
    )


def test_signed_message_accepts_once_with_exact_bindings() -> None:
    now = datetime.now(UTC)
    payload, envelope = _sign(now=now)
    receipt = GovernedMessageVerifier(replay_store=InMemoryReplayStore()).accept(
        envelope=envelope,
        payload=payload,
        verifier=_auth(),
        expected_recipient_id="agent:writer",
        expected_sender_principal_id="principal:research",
        expected_sender_actor_id="agent:research",
        expected_purpose_id="prepare_brief",
        expected_workflow_id="workflow:brief:1",
        expected_authority_envelope_ref="urn:valo:authority:ctx:1",
        expected_delegation_chain_digest="b" * 64,
        allowed_scope=("document:doc:1", "document:doc:2"),
        now=now + timedelta(seconds=1),
    )
    assert receipt.message_id == envelope.message_id
    assert receipt.grants_authority is False
    assert receipt.digest


def test_replay_is_rejected() -> None:
    now = datetime.now(UTC)
    payload, envelope = _sign(now=now)
    verifier = GovernedMessageVerifier(replay_store=InMemoryReplayStore())
    kwargs = {
        "envelope": envelope,
        "payload": payload,
        "verifier": _auth(),
        "expected_recipient_id": "agent:writer",
        "now": now + timedelta(seconds=1),
    }
    verifier.accept(**kwargs)
    with pytest.raises(ValueError, match="replay detected"):
        verifier.accept(**kwargs)


def test_payload_and_signature_tampering_are_rejected() -> None:
    now = datetime.now(UTC)
    payload, envelope = _sign(now=now)
    verifier = GovernedMessageVerifier(replay_store=InMemoryReplayStore())
    with pytest.raises(ValueError, match="payload digest mismatch"):
        verifier.accept(
            envelope=envelope,
            payload={"task": "delete", "document": "doc:1"},
            verifier=_auth(),
            expected_recipient_id="agent:writer",
            now=now + timedelta(seconds=1),
        )
    tampered = envelope.model_copy(update={"signature": "f" * 64})
    with pytest.raises(ValueError, match="signature verification failed"):
        verifier.accept(
            envelope=tampered,
            payload=payload,
            verifier=_auth(),
            expected_recipient_id="agent:writer",
            now=now + timedelta(seconds=1),
        )


def test_sender_recipient_purpose_workflow_and_scope_fail_closed() -> None:
    now = datetime.now(UTC)
    payload, envelope = _sign(now=now)
    verifier = GovernedMessageVerifier(replay_store=InMemoryReplayStore())
    checks = (
        ({"expected_recipient_id": "agent:finance"}, "recipient binding mismatch"),
        ({"expected_recipient_id": "agent:writer", "expected_sender_principal_id": "principal:spoofed"}, "sender principal binding mismatch"),
        ({"expected_recipient_id": "agent:writer", "expected_sender_actor_id": "agent:spoofed"}, "sender actor binding mismatch"),
        ({"expected_recipient_id": "agent:writer", "expected_purpose_id": "approve_payment"}, "purpose binding mismatch"),
        ({"expected_recipient_id": "agent:writer", "expected_workflow_id": "workflow:other"}, "workflow binding mismatch"),
        ({"expected_recipient_id": "agent:writer", "allowed_scope": ("document:doc:2",)}, "scope exceeds accepted scope"),
    )
    for extra, match in checks:
        with pytest.raises(ValueError, match=match):
            verifier.accept(
                envelope=envelope,
                payload=payload,
                verifier=_auth(),
                now=now + timedelta(seconds=1),
                **extra,
            )


def test_expired_message_is_rejected() -> None:
    now = datetime.now(UTC)
    payload, envelope = _sign(now=now)
    with pytest.raises(ValueError, match="message is expired"):
        GovernedMessageVerifier(replay_store=InMemoryReplayStore()).accept(
            envelope=envelope,
            payload=payload,
            verifier=_auth(),
            expected_recipient_id="agent:writer",
            now=now + timedelta(minutes=6),
        )


def test_child_message_can_only_narrow_parent_scope() -> None:
    now = datetime.now(UTC)
    parent_payload, parent = _sign(
        now=now,
        scope=("document:doc:1", "document:doc:2"),
    )
    GovernedMessageVerifier(replay_store=InMemoryReplayStore()).accept(
        envelope=parent,
        payload=parent_payload,
        verifier=_auth(),
        expected_recipient_id="agent:writer",
        now=now + timedelta(seconds=1),
    )
    child_payload, child = _sign(
        {"task": "summarize", "document": "doc:1"},
        now=now + timedelta(seconds=2),
        scope=("document:doc:1",),
        parent=parent,
    )
    receipt = GovernedMessageVerifier(replay_store=InMemoryReplayStore()).accept(
        envelope=child,
        payload=child_payload,
        verifier=_auth(),
        expected_recipient_id="agent:writer",
        parent_envelope=parent,
        now=now + timedelta(seconds=3),
    )
    assert receipt.scope == ("document:doc:1",)

    expanded_payload = {"task": "summarize", "document": "doc:3"}
    _, expanded = _sign(
        expanded_payload,
        now=now + timedelta(seconds=2),
        scope=("document:doc:1", "document:doc:3"),
        parent=parent,
    )
    with pytest.raises(ValueError, match="expands scope across hop"):
        GovernedMessageVerifier(replay_store=InMemoryReplayStore()).accept(
            envelope=expanded,
            payload=expanded_payload,
            verifier=_auth(),
            expected_recipient_id="agent:writer",
            parent_envelope=parent,
            now=now + timedelta(seconds=3),
        )


def test_parent_reference_requires_parent_envelope_for_verification() -> None:
    now = datetime.now(UTC)
    _, parent = _sign(now=now)
    payload, child = _sign(now=now + timedelta(seconds=1), parent=parent)
    with pytest.raises(ValueError, match="parent envelope is required"):
        GovernedMessageVerifier(replay_store=InMemoryReplayStore()).accept(
            envelope=child,
            payload=payload,
            verifier=_auth(),
            expected_recipient_id="agent:writer",
            now=now + timedelta(seconds=2),
        )


def test_extra_authority_fields_and_wildcard_scope_are_rejected() -> None:
    now = datetime.now(UTC)
    payload, envelope = _sign(now=now)
    values = envelope.model_dump()
    values["authority"] = "ALLOW"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        GovernedMessageEnvelopeV1(**values)
    with pytest.raises(ValidationError, match="message scope must be explicit"):
        GovernedMessageEnvelopeV1.sign(
            payload=payload,
            workflow_id="workflow:brief:1",
            sender_principal_id="principal:research",
            sender_actor_id="agent:research",
            recipient_id="agent:writer",
            purpose_id="prepare_brief",
            scope=("*",),
            issued_at=now,
            expires_at=now + timedelta(minutes=1),
            nonce="nonce-stage3-wildcard-0001",
            originating_authority_envelope_ref="urn:valo:authority:ctx:1",
            originating_authority_envelope_digest="a" * 64,
            delegation_chain_ref="urn:valo:delegation:chain:1",
            delegation_chain_digest="b" * 64,
            signer=_auth(),
        )


def test_short_hmac_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        HMACSHA256Authenticator(key_id="short", key=b"short")
