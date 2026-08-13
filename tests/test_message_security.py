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


def _envelope(payload=None, *, now: datetime | None = None):
    now = now or datetime.now(UTC)
    payload = payload or {"task": "summarize", "document": "doc:1"}
    return payload, GovernedMessageEnvelopeV1.sign(
        payload=payload,
        sender_id="agent:research",
        recipient_id="agent:writer",
        purpose_id="prepare_brief",
        scope=("document:doc:1",),
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
        nonce="nonce-stage3-0001",
        signer=_auth(),
        authority_context_ref="urn:valo:authority:ctx:1",
        authority_context_digest="a" * 64,
    )


def test_signed_message_accepts_once_with_exact_bindings() -> None:
    now = datetime.now(UTC)
    payload, envelope = _envelope(now=now)
    receipt = GovernedMessageVerifier(replay_store=InMemoryReplayStore()).accept(
        envelope=envelope,
        payload=payload,
        verifier=_auth(),
        expected_recipient_id="agent:writer",
        expected_sender_id="agent:research",
        expected_purpose_id="prepare_brief",
        allowed_scope=("document:doc:1", "document:doc:2"),
        now=now + timedelta(seconds=1),
    )
    assert receipt.message_id == envelope.message_id
    assert receipt.envelope_digest == envelope.envelope_digest
    assert receipt.grants_authority is False
    assert receipt.digest


def test_replay_is_rejected() -> None:
    now = datetime.now(UTC)
    payload, envelope = _envelope(now=now)
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


def test_payload_tamper_is_rejected() -> None:
    now = datetime.now(UTC)
    _, envelope = _envelope(now=now)
    with pytest.raises(ValueError, match="payload digest mismatch"):
        GovernedMessageVerifier(replay_store=InMemoryReplayStore()).accept(
            envelope=envelope,
            payload={"task": "delete", "document": "doc:1"},
            verifier=_auth(),
            expected_recipient_id="agent:writer",
            now=now + timedelta(seconds=1),
        )


def test_signature_tamper_is_rejected() -> None:
    now = datetime.now(UTC)
    payload, envelope = _envelope(now=now)
    tampered = envelope.model_copy(update={"signature": "f" * 64})
    with pytest.raises(ValueError, match="signature verification failed"):
        GovernedMessageVerifier(replay_store=InMemoryReplayStore()).accept(
            envelope=tampered,
            payload=payload,
            verifier=_auth(),
            expected_recipient_id="agent:writer",
            now=now + timedelta(seconds=1),
        )


def test_wrong_recipient_purpose_and_scope_fail_closed() -> None:
    now = datetime.now(UTC)
    payload, envelope = _envelope(now=now)
    verifier = GovernedMessageVerifier(replay_store=InMemoryReplayStore())
    with pytest.raises(ValueError, match="recipient binding mismatch"):
        verifier.accept(
            envelope=envelope,
            payload=payload,
            verifier=_auth(),
            expected_recipient_id="agent:finance",
            now=now + timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="purpose binding mismatch"):
        verifier.accept(
            envelope=envelope,
            payload=payload,
            verifier=_auth(),
            expected_recipient_id="agent:writer",
            expected_purpose_id="approve_payment",
            now=now + timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="scope exceeds accepted scope"):
        verifier.accept(
            envelope=envelope,
            payload=payload,
            verifier=_auth(),
            expected_recipient_id="agent:writer",
            allowed_scope=("document:doc:2",),
            now=now + timedelta(seconds=1),
        )


def test_expired_message_is_rejected() -> None:
    now = datetime.now(UTC)
    payload, envelope = _envelope(now=now)
    with pytest.raises(ValueError, match="message is expired"):
        GovernedMessageVerifier(replay_store=InMemoryReplayStore()).accept(
            envelope=envelope,
            payload=payload,
            verifier=_auth(),
            expected_recipient_id="agent:writer",
            now=now + timedelta(minutes=6),
        )


def test_authority_reference_requires_digest_and_never_grants_authority() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="authority context reference and digest"):
        GovernedMessageEnvelopeV1(
            sender_id="agent:a",
            recipient_id="agent:b",
            purpose_id="handoff",
            scope=("task:1",),
            issued_at=now,
            expires_at=now + timedelta(minutes=1),
            nonce="nonce-stage3-0002",
            payload_digest="a" * 64,
            authority_context_ref="urn:valo:authority:ctx:1",
            key_id="key:agents:v1",
            signature_algorithm="HMAC-SHA256",
            signature="b" * 64,
        )


def test_short_hmac_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        HMACSHA256Authenticator(key_id="short", key=b"short")
