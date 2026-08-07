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
