from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from valo_gateway.protocols import (
    ChannelEventEvidence,
    ChannelEvidenceNormalizer,
    ChannelInteraction,
    ChannelKind,
)


def channel_payload(**overrides):
    payload = {
        "provider_id": "channels:provider-1",
        "channel": "slack",
        "workspace_id": "workspace-1",
        "conversation_id": "channel-7",
        "event_id": "event-42",
        "actor_id": "user-9",
        "interaction": "approval",
        "observed_at": datetime(2026, 8, 7, 16, 0, tzinfo=UTC),
        "thread_id": "thread-11",
        "correlation_ref": "action-proposal:abc",
        "payload": {"approved": True, "action_digest": "sha256:proposal"},
    }
    payload.update(overrides)
    return payload


def test_channel_approval_is_evidence_not_authority():
    event = ChannelEvidenceNormalizer().normalize(channel_payload())

    assert event.channel is ChannelKind.SLACK
    assert event.interaction is ChannelInteraction.APPROVAL
    assert event.authority_effect == "none"
    assert event.payload["approved"] is True
    assert event.thread_id == "thread-11"


@pytest.mark.parametrize(
    ("channel", "interaction"),
    [
        ("email", "message"),
        ("sms", "message"),
        ("mms", "message"),
        ("voice", "call"),
        ("imessage", "message"),
    ],
)
def test_identity_channel_substrate_is_verified_evidence_not_authority(
    channel, interaction
):
    event = ChannelEvidenceNormalizer().normalize(
        channel_payload(
            provider_id="inkbox",
            channel=channel,
            interaction=interaction,
            workspace_id="inkbox:org-1",
            conversation_id=f"inkbox:{channel}:conversation-1",
            event_id=f"inkbox:{channel}:event-1",
            actor_id="external:contact-1",
            agent_identity_id="inkbox:agent:hermes-1",
            transport_verified=True,
            payload={"request_id": "req-1", "signature_scheme": "hmac-sha256"},
        )
    )

    assert event.provider_id == "inkbox"
    assert event.channel is ChannelKind(channel)
    assert event.interaction is ChannelInteraction(interaction)
    assert event.agent_identity_id == "inkbox:agent:hermes-1"
    assert event.transport_verified is True
    assert event.authority_effect == "none"
    assert not hasattr(event, "authorize")
    assert not hasattr(event, "to_execution_permit")


def test_verified_transport_cannot_smuggle_authority():
    with pytest.raises(ValidationError, match="cannot carry authority field"):
        ChannelEventEvidence(
            **channel_payload(
                provider_id="inkbox",
                channel="email",
                interaction="message",
                agent_identity_id="inkbox:agent:hermes-1",
                transport_verified=True,
                payload={"signature_verified": True, "reht_clearance": "forged"},
            )
        )


def test_agent_identity_must_be_non_empty_when_present():
    with pytest.raises(ValidationError, match="agent identity must be non-empty"):
        ChannelEventEvidence(**channel_payload(agent_identity_id=" "))


def test_channel_evidence_digest_is_deterministic():
    left = ChannelEventEvidence(**channel_payload())
    right = ChannelEventEvidence(**channel_payload())

    assert left.digest == right.digest
    assert len(left.digest) == 64


@pytest.mark.parametrize(
    "authority_field",
    [
        "authority_envelope_id",
        "authority_grant",
        "clearance_id",
        "execution_permit",
        "permit_id",
        "reht_clearance",
        "reht_decision",
    ],
)
def test_channel_payload_rejects_embedded_authority_claims(authority_field):
    with pytest.raises(ValidationError, match="cannot carry authority field"):
        ChannelEventEvidence(
            **channel_payload(payload={"nested": {authority_field: "forged"}})
        )


def test_channel_contract_rejects_extra_authority_shaped_top_level_field():
    with pytest.raises(ValidationError):
        ChannelEventEvidence(**channel_payload(clearance_id="clearance:forged"))


def test_channel_contract_has_no_execution_conversion():
    event = ChannelEventEvidence(**channel_payload())

    assert not hasattr(event, "execute")
    assert not hasattr(event, "authorize")
    assert not hasattr(event, "to_execution_permit")
