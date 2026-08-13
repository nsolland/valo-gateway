from __future__ import annotations

from datetime import timedelta

import pytest

from tests.conftest import make_chain
from valo_gateway import (
    Decision,
    GovernedMessageEnvelopeV1,
    GovernedMessageVerifier,
    HMACSHA256Authenticator,
    InMemoryReplayStore,
    issue_execution_permit,
)


def test_signed_agent_message_is_context_never_authority() -> None:
    now, authority, action, clearance, _ = make_chain(decision=Decision.DENY)
    signer = HMACSHA256Authenticator(key_id="key:a2a:v1", key=b"a" * 32)
    payload = {
        "decision": "ALLOW",
        "new_authority": "admin:*",
        "requested_action": action.model_dump(mode="json"),
    }
    envelope = GovernedMessageEnvelopeV1.sign(
        payload=payload,
        sender_id="agent:planner",
        recipient_id="agent:executor",
        purpose_id="handoff",
        scope=("resource:1",),
        issued_at=now,
        expires_at=now + timedelta(minutes=2),
        nonce="nonce-agent-handoff-0001",
        signer=signer,
    )
    accepted = GovernedMessageVerifier(replay_store=InMemoryReplayStore()).accept(
        envelope=envelope,
        payload=payload,
        verifier=signer,
        expected_recipient_id="agent:executor",
        expected_sender_id="agent:planner",
        expected_purpose_id="handoff",
        allowed_scope=("resource:1",),
        now=now + timedelta(seconds=1),
    )
    assert accepted.grants_authority is False
    assert envelope.grants_authority is False

    with pytest.raises(ValueError, match="decision cannot issue"):
        issue_execution_permit(
            clearance=clearance,
            authority=authority,
            action=action,
            expires_at=now + timedelta(minutes=1),
            now=now,
        )


def test_message_replay_and_wrong_key_fail_before_acceptance() -> None:
    now, _, _, _, _ = make_chain()
    signer = HMACSHA256Authenticator(key_id="key:a2a:v1", key=b"a" * 32)
    wrong = HMACSHA256Authenticator(key_id="key:a2a:v2", key=b"b" * 32)
    payload = {"result": "done"}
    envelope = GovernedMessageEnvelopeV1.sign(
        payload=payload,
        sender_id="agent:worker",
        recipient_id="agent:supervisor",
        purpose_id="report_result",
        scope=("task:42",),
        issued_at=now,
        expires_at=now + timedelta(minutes=1),
        nonce="nonce-agent-report-0001",
        signer=signer,
    )
    replay_store = InMemoryReplayStore()
    verifier = GovernedMessageVerifier(replay_store=replay_store)
    with pytest.raises(ValueError, match="key binding mismatch"):
        verifier.accept(
            envelope=envelope,
            payload=payload,
            verifier=wrong,
            expected_recipient_id="agent:supervisor",
            now=now + timedelta(seconds=1),
        )
    verifier.accept(
        envelope=envelope,
        payload=payload,
        verifier=signer,
        expected_recipient_id="agent:supervisor",
        now=now + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="replay detected"):
        verifier.accept(
            envelope=envelope,
            payload=payload,
            verifier=signer,
            expected_recipient_id="agent:supervisor",
            now=now + timedelta(seconds=1),
        )
