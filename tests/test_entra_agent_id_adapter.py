from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from valo_gateway.identity_adapters import (
    ConditionalAccessDecision,
    EntraAgentAccessMode,
    EntraAgentIdContext,
)


def _context(**overrides):
    issued = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    values = {
        "tenant_id": "tenant-1",
        "agent_identity_id": "agent-123",
        "blueprint_id": "blueprint-456",
        "access_mode": EntraAgentAccessMode.AUTONOMOUS,
        "audience": "https://graph.microsoft.com",
        "application_permissions": ["User.Read.All"],
        "entra_roles": ["Directory Readers"],
        "sponsor_ids": ["sponsor-1"],
        "conditional_access": ConditionalAccessDecision.ALLOW,
        "risk_level": "low",
        "token_issued_at": issued,
        "token_expires_at": issued + timedelta(hours=1),
        "evidence_refs": ["entra-signin:abc"],
    }
    values.update(overrides)
    return EntraAgentIdContext(**values)


def test_on_behalf_of_requires_subject_identity():
    with pytest.raises(ValidationError, match="subject_id is required"):
        _context(access_mode=EntraAgentAccessMode.ON_BEHALF_OF)


def test_on_behalf_of_binds_user_and_agent():
    context = _context(
        access_mode=EntraAgentAccessMode.ON_BEHALF_OF,
        subject_id="user-789",
        delegated_scopes=["Mail.Read"],
        application_permissions=[],
    )

    evidence = context.to_reht_evidence()

    assert evidence["identity"]["agent_identity_id"] == "agent-123"
    assert evidence["identity"]["subject_id"] == "user-789"
    assert evidence["identity"]["access_mode"] == "on_behalf_of"


def test_provider_access_never_becomes_execution_authority():
    evidence = _context().to_reht_evidence()

    assert evidence["provider"] == "microsoft_entra_agent_id"
    assert evidence["authoritative"] is False
    assert "decision" not in evidence
    assert "clearance" not in evidence
    assert "permit" not in evidence


def test_conditional_access_block_fails_current_access():
    context = _context(conditional_access=ConditionalAccessDecision.BLOCK)

    assert context.is_current_access(datetime(2026, 8, 8, 12, 30, tzinfo=UTC)) is False


def test_disabled_or_revoked_identity_fails_current_access():
    assert _context(disabled=True).is_current_access(datetime(2026, 8, 8, 12, 30, tzinfo=UTC)) is False
    revoked = _context(
        revoked_at=datetime(2026, 8, 8, 12, 15, tzinfo=UTC),
        revocation_ref="entra:disable:agent-123",
    )
    assert revoked.is_current_access(datetime(2026, 8, 8, 12, 30, tzinfo=UTC)) is False


def test_expired_token_fails_current_access():
    context = _context()

    assert context.is_current_access(datetime(2026, 8, 8, 13, 0, tzinfo=UTC)) is False


def test_binding_digest_changes_when_scope_changes():
    first = _context(application_permissions=["User.Read.All"])
    second = _context(application_permissions=["Files.Read.All"])

    assert first.binding_digest != second.binding_digest


def test_partial_token_lifecycle_is_rejected():
    with pytest.raises(ValidationError, match="must be supplied together"):
        _context(token_expires_at=None)


def test_revocation_requires_evidence_reference():
    with pytest.raises(ValidationError, match="revocation_ref is required"):
        _context(revoked_at=datetime(2026, 8, 8, 12, 15, tzinfo=UTC))
